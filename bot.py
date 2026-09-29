import asyncio
import json
import logging
import os
import secrets
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv


# =========================================================
# НАСТРОЙКИ
# =========================================================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")


BASE_DIR = Path(__file__).resolve().parent

# Пока оставляем текущую demo-базу.
# PostgreSQL подключим отдельным следующим этапом.
DATABASE = BASE_DIR / "bot_demo_clean.db"

CARDS_FILE = BASE_DIR / "cards.json"


# =========================================================
# ЗАГРУЗКА 45 КАРТ
# =========================================================

if not CARDS_FILE.exists():
    raise FileNotFoundError(
        f"Не найден файл {CARDS_FILE}. "
        "Сначала создайте cards.json."
    )


with CARDS_FILE.open("r", encoding="utf-8") as file:
    raw_cards = json.load(file)


cards = {
    int(number): data
    for number, data in raw_cards.items()
}


if set(cards.keys()) != set(range(1, 46)):
    raise ValueError(
        "В cards.json должны находиться карты №1–45."
    )


# =========================================================
# ТАРИФЫ
# =========================================================

tariffs = {
    "1": {
        "cards": 1,
        "price": 50,
    },
    "3": {
        "cards": 3,
        "price": 120,
    },
    "5": {
        "cards": 5,
        "price": 180,
    },
}


# =========================================================
# КЛАВИАТУРЫ
# =========================================================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(
                text="🎴 Выбрать случайную карту"
            )
        ],
        [
            KeyboardButton(
                text="🔢 Выбрать карту по номеру"
            )
        ],
        [
            KeyboardButton(
                text="💰 Мой баланс"
            )
        ],
        [
            KeyboardButton(
                text="✨ Хочу больше карт"
            )
        ],
    ],
    resize_keyboard=True,
)


def get_tariffs_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1 карта — 50 ₽",
                    callback_data="tariff_1",
                )
            ],
            [
                InlineKeyboardButton(
                    text="3 карты — 120 ₽",
                    callback_data="tariff_3",
                )
            ],
            [
                InlineKeyboardButton(
                    text="5 карт — 180 ₽",
                    callback_data="tariff_5",
                )
            ],
        ]
    )


def get_buy_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✨ Хочу больше карт",
                    callback_data="show_tariffs",
                )
            ]
        ]
    )


def get_payment_keyboard(tariff_key: str):
    tariff = tariffs[tariff_key]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💳 Оплатить {tariff['price']} ₽",
                    callback_data=f"pay_{tariff_key}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Назад к тарифам",
                    callback_data="back_to_tariffs",
                )
            ],
        ]
    )


# =========================================================
# БАЗА ДАННЫХ
# =========================================================

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        await db.commit()


async def create_user(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (
                user_id,
                balance
            )
            VALUES (?, 1)
            """,
            (user_id,),
        )

        await db.commit()


async def get_balance(user_id: int) -> int:
    await create_user(user_id)

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            """
            SELECT balance
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        )

        row = await cursor.fetchone()

    if row is None:
        return 0

    return row[0]


async def add_cards(
    user_id: int,
    amount: int,
):
    await create_user(user_id)

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            """
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ?
            """,
            (
                amount,
                user_id,
            ),
        )

        await db.commit()


async def use_card(user_id: int) -> bool:
    """
    Списывает одну карту только при наличии баланса.

    UPDATE выполняется атомарно, поэтому баланс
    не должен уйти ниже нуля.
    """

    await create_user(user_id)

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            """
            UPDATE users
            SET balance = balance - 1
            WHERE user_id = ?
              AND balance > 0
            """,
            (user_id,),
        )

        await db.commit()

        return cursor.rowcount > 0


# =========================================================
# РАБОТА С ДЛИННЫМ ТЕКСТОМ
# =========================================================

def split_long_text(
    text: str,
    max_length: int = 3900,
):
    """
    Делит длинную расшифровку на сообщения.

    Сначала стараемся разделять по абзацам.
    Если отдельный абзац слишком большой,
    делим его дополнительно.
    """

    text = text.strip()

    if not text:
        return []

    if len(text) <= max_length:
        return [text]

    paragraphs = text.split("\n\n")

    parts = []
    current = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        candidate = (
            paragraph
            if not current
            else current + "\n\n" + paragraph
        )

        if len(candidate) <= max_length:
            current = candidate
            continue

        if current:
            parts.append(current)
            current = ""

        # Если сам абзац оказался слишком длинным
        while len(paragraph) > max_length:
            split_position = paragraph.rfind(
                " ",
                0,
                max_length,
            )

            if split_position <= 0:
                split_position = max_length

            parts.append(
                paragraph[:split_position].strip()
            )

            paragraph = paragraph[
                split_position:
            ].strip()

        current = paragraph

    if current:
        parts.append(current)

    return parts


# =========================================================
# ТАРИФЫ
# =========================================================

async def send_tariffs(message: Message):
    await message.answer(
        "✨ Хотите открыть ещё карты?\n\n"
        "Выберите подходящий вариант:",
        reply_markup=get_tariffs_keyboard(),
    )


# =========================================================
# ОТПРАВКА КАРТЫ
# =========================================================

async def send_card(
    message: Message,
    card_number: int,
):
    user_id = message.from_user.id

    success = await use_card(user_id)

    if not success:
        await message.answer(
            "У вас закончились доступные карты."
        )

        await send_tariffs(message)

        return

    card = cards[card_number]

    title = card["title"]
    description = card["description"]

    image_path = BASE_DIR / card["image"]

    if not image_path.exists():
        # Если изображения почему-то нет,
        # возвращаем пользователю списанную карту.
        await add_cards(user_id, 1)

        await message.answer(
            "Не удалось найти изображение этой карты.\n"
            "Карта не была списана с вашего баланса."
        )

        logging.error(
            "Не найден файл изображения: %s",
            image_path,
        )

        return

    photo = FSInputFile(image_path)

    # На фото оставляем только короткую подпись.
    await message.answer_photo(
        photo=photo,
        caption=(
            f"✨ Карта №{card_number}\n"
            f"«{title}»"
        ),
    )

    # Полную расшифровку отправляем отдельно.
    text_parts = split_long_text(description)

    for part in text_parts:
        await message.answer(part)

    balance = await get_balance(user_id)

    if balance > 0:
        await message.answer(
            f"💫 Осталось карт: {balance}"
        )

    else:
        await message.answer(
            "Это была ваша последняя доступная карта.\n\n"
            "Хотите открыть ещё?",
            reply_markup=get_buy_keyboard(),
        )


# =========================================================
# DISPATCHER
# =========================================================

dp = Dispatcher()


# =========================================================
# /START
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: Message):
    user_id = message.from_user.id

    await create_user(user_id)

    balance = await get_balance(user_id)

    await message.answer(
        "✨ Добро пожаловать в «Следы праматери».\n\n"
        "Вы можете довериться случаю и получить "
        "случайную карту или выбрать карту "
        "по номеру от 1 до 45.\n\n"
        f"💫 Доступно карт: {balance}",
        reply_markup=main_keyboard,
    )

    if balance == 0:
        await send_tariffs(message)


# =========================================================
# БАЛАНС
# =========================================================

@dp.message(F.text == "💰 Мой баланс")
async def balance_handler(message: Message):
    balance = await get_balance(
        message.from_user.id
    )

    await message.answer(
        f"💫 Ваш баланс: {balance} карт."
    )

    if balance == 0:
        await send_tariffs(message)


# =========================================================
# СЛУЧАЙНАЯ КАРТА
# =========================================================

@dp.message(
    F.text == "🎴 Выбрать случайную карту"
)
async def random_card_handler(message: Message):
    balance = await get_balance(
        message.from_user.id
    )

    if balance <= 0:
        await message.answer(
            "У вас закончились доступные карты."
        )

        await send_tariffs(message)

        return

    card_number = secrets.randbelow(45) + 1

    await send_card(
        message,
        card_number,
    )


# =========================================================
# ВЫБОР КАРТЫ ПО НОМЕРУ
# =========================================================

@dp.message(
    F.text == "🔢 Выбрать карту по номеру"
)
async def choose_card_handler(message: Message):
    balance = await get_balance(
        message.from_user.id
    )

    if balance <= 0:
        await message.answer(
            "У вас закончились доступные карты."
        )

        await send_tariffs(message)

        return

    await message.answer(
        "Введите номер карты от 1 до 45:"
    )


# =========================================================
# КНОПКА "ХОЧУ БОЛЬШЕ КАРТ"
# =========================================================

@dp.message(
    F.text == "✨ Хочу больше карт"
)
async def buy_more_handler(message: Message):
    await send_tariffs(message)


# =========================================================
# INLINE-КНОПКА ТАРИФОВ
# =========================================================

@dp.callback_query(
    F.data == "show_tariffs"
)
async def show_tariffs_callback(
    callback: CallbackQuery,
):
    await callback.answer()

    if callback.message:
        await send_tariffs(
            callback.message
        )


# =========================================================
# ВЫБОР ТАРИФА
# =========================================================

@dp.callback_query(
    F.data.startswith("tariff_")
)
async def tariff_callback(
    callback: CallbackQuery,
):
    await callback.answer()

    tariff_key = callback.data.replace(
        "tariff_",
        "",
        1,
    )

    if tariff_key not in tariffs:
        return

    tariff = tariffs[tariff_key]

    if not callback.message:
        return

    await callback.message.edit_text(
        "✨ Вы выбрали:\n\n"
        f"🎴 Карт: {tariff['cards']}\n"
        f"💳 Стоимость: {tariff['price']} ₽\n\n"
        "Сейчас используется тестовая "
        "демо-оплата.",
        reply_markup=get_payment_keyboard(
            tariff_key
        ),
    )


# =========================================================
# НАЗАД К ТАРИФАМ
# =========================================================

@dp.callback_query(
    F.data == "back_to_tariffs"
)
async def back_to_tariffs_callback(
    callback: CallbackQuery,
):
    await callback.answer()

    if not callback.message:
        return

    await callback.message.edit_text(
        "✨ Выберите подходящий вариант:",
        reply_markup=get_tariffs_keyboard(),
    )


# =========================================================
# ДЕМО-ОПЛАТА
# =========================================================

@dp.callback_query(
    F.data.startswith("pay_")
)
async def payment_callback(
    callback: CallbackQuery,
):
    tariff_key = callback.data.replace(
        "pay_",
        "",
        1,
    )

    if tariff_key not in tariffs:
        await callback.answer(
            "Неизвестный тариф.",
            show_alert=True,
        )

        return

    tariff = tariffs[tariff_key]

    user_id = callback.from_user.id

    await add_cards(
        user_id,
        tariff["cards"],
    )

    new_balance = await get_balance(
        user_id
    )

    await callback.answer(
        "Демо-оплата прошла успешно!"
    )

    if not callback.message:
        return

    await callback.message.edit_text(
        "✅ ДЕМО-ОПЛАТА УСПЕШНА\n\n"
        f"Начислено карт: {tariff['cards']}\n"
        f"💫 Новый баланс: {new_balance}\n\n"
        "Теперь можно открыть карту."
    )


# =========================================================
# ВВОД НОМЕРА 1–45
# =========================================================

@dp.message(F.text.regexp(r"^\d+$"))
async def number_handler(message: Message):
    try:
        card_number = int(message.text)
    except (TypeError, ValueError):
        return

    if not 1 <= card_number <= 45:
        await message.answer(
            "Введите номер карты от 1 до 45."
        )

        return

    balance = await get_balance(
        message.from_user.id
    )

    if balance <= 0:
        await message.answer(
            "У вас закончились доступные карты."
        )

        await send_tariffs(message)

        return

    await send_card(
        message,
        card_number,
    )


# =========================================================
# ОСТАЛЬНЫЕ СООБЩЕНИЯ
# =========================================================

@dp.message()
async def fallback_handler(message: Message):
    await message.answer(
        "Выберите действие с помощью кнопок ниже.",
        reply_markup=main_keyboard,
    )


# =========================================================
# ЗАПУСК
# =========================================================

async def main():
    logging.basicConfig(
        level=logging.INFO
    )

    await init_db()

    bot = Bot(token=TOKEN)

    bot_info = await bot.get_me()

    logging.info(
        "Бот запущен: @%s",
        bot_info.username,
    )

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())