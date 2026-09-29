import asyncio
import json
import logging
import os
import secrets
from pathlib import Path

import asyncpg
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

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден в переменных окружения")

CARDS_FILE = BASE_DIR / "cards.json"
WELCOME_VIDEO_1 = BASE_DIR / "media" / "welcome_video_1.mp4"
WELCOME_VIDEO_2 = BASE_DIR / "media" / "welcome_video_2.mp4"


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
                text="✨ Получить случайным образом"
            )
        ],
        [
            KeyboardButton(
                text="🔢 Выбрать карту самой"
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


def get_ready_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="✨ Готовы?",
                callback_data="welcome_ready",
            )
        ]]
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
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 1,
                intro_seen BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    finally:
        await conn.close()


async def create_user(user_id: int):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """
            INSERT INTO users (user_id, balance, intro_seen)
            VALUES ($1, 1, FALSE)
            ON CONFLICT (user_id) DO NOTHING
            """,
            user_id,
        )
    finally:
        await conn.close()


async def get_balance(user_id: int) -> int:
    await create_user(user_id)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        balance = await conn.fetchval(
            """
            SELECT balance
            FROM users
            WHERE user_id = $1
            """,
            user_id,
        )
    finally:
        await conn.close()

    return int(balance or 0)


async def add_cards(user_id: int, amount: int):
    await create_user(user_id)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """
            UPDATE users
            SET balance = balance + $1
            WHERE user_id = $2
            """,
            amount,
            user_id,
        )
    finally:
        await conn.close()


async def use_card(user_id: int) -> bool:
    """
    Атомарно списывает одну карту,
    только если баланс больше нуля.
    """
    await create_user(user_id)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        result = await conn.execute(
            """
            UPDATE users
            SET balance = balance - 1
            WHERE user_id = $1
              AND balance > 0
            """,
            user_id,
        )
    finally:
        await conn.close()

    return result == "UPDATE 1"


async def has_seen_intro(user_id: int) -> bool:
    await create_user(user_id)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        value = await conn.fetchval(
            """
            SELECT intro_seen
            FROM users
            WHERE user_id = $1
            """,
            user_id,
        )
    finally:
        await conn.close()

    return bool(value)


async def mark_intro_seen(user_id: int):
    await create_user(user_id)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """
            UPDATE users
            SET intro_seen = TRUE
            WHERE user_id = $1
            """,
            user_id,
        )
    finally:
        await conn.close()


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

    if await has_seen_intro(user_id):
        balance = await get_balance(user_id)
        await message.answer(
            "✨ С возвращением в «Следы праматери».\n\n"
            f"💫 Доступно карт: {balance}",
            reply_markup=main_keyboard,
        )
        if balance == 0:
            await send_tariffs(message)
        return

    if not WELCOME_VIDEO_1.exists() or not WELCOME_VIDEO_2.exists():
        logging.error("Не найдены приветственные видео в папке media")
        await message.answer(
            "Не удалось загрузить приветственное видео. Попробуйте чуть позже."
        )
        return

    await message.answer_video(video=FSInputFile(WELCOME_VIDEO_1))

    await message.answer(
        "🦋Привет,моя дорогая!\n"
        "Ты здесь совершенно неслучайно 💫\n\n"
        "У тебя есть уникальная возможность почувствовать и узнать, "
        "как звучит магия ✨ (из описания карт, надеюсь вы тоже "
        "почувствуете, какое это таинство)"
    )

    await message.answer(
        "Давным-давно, когда мир был моложе, чем теперь, люди вырезали "
        "из дерева и костей фигурки Великой Матери. Они чтили её как ту, "
        "что всегда заботится о своих детях, дающую жизнь, повелевающую "
        "миром людей и миром духов.\n"
        "У этих фигурок не было лиц, потому что люди знали - лик Матери "
        "непостижим. Его хранит в себе каждое женское лицо из всех "
        "существовавших и существующих. Она - первозданная сила и жизнь, "
        "она - проводник в мир тайн, она - дарующая урожай.\n\n"
        "Эта колода создана для женщин, которые находятся в печали, "
        "в сомнении, в поиске, в периоде трансформации, нуждаются в совете "
        "от самой Мудрой, в её помощи и заботе."
    )

    await message.answer(
        "Карты могут работать как оракул, но в первую очередь, "
        "«Следы Праматери» - колода, исцеляющая женское сердце. "
        "Старшая подруга, мать, бабушка, сестра, которая выслушает, "
        "даст хороший совет, поддержит. Где-то покажет то, что сейчас "
        "вы не хотите видеть или отрицаете, где-то подсветит иллюзии "
        "и поможет от них отказаться."
    )

    await message.answer(
        "Ей ведома земля и небо, звезды и моря, животные и птицы, "
        "растения и рыбы. Всем этим она повелевает, и все это готова вам "
        "подарить. Колода состоит из 45 карт с женскими изображениями "
        "без лица. Работая с ней, помните, что она показывает сейчас "
        "ваше лицо, ваше состояние."
    )

    await message.answer(
        "Еще чуть-чуть важной информации\n"
        "Вытягивая карту, вы получаете точное описание, что происходит, "
        "что делать, а также совет карт.\n\n"
        "👆Но главное, к каждой карте есть аффирмация, которую нужно "
        "повторять или писать 7 дней, что в разы усиливает энергию карты "
        "и буквально запускает новые процессы, вам нужно лишь быть "
        "внимательными и наблюдать, какие чудеса будут происходить, "
        "как будет решаться ваш запрос.\n\n"
        "p.s. можете скачать карту и поставить на заставку для усиления эффекта"
    )

    await message.answer_video(
        video=FSInputFile(WELCOME_VIDEO_2),
        reply_markup=get_ready_keyboard(),
    )


@dp.callback_query(F.data == "welcome_ready")
async def welcome_ready_callback(callback: CallbackQuery):
    await callback.answer()
    await mark_intro_seen(callback.from_user.id)

    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        await callback.message.answer(
            "☀️Обращаемся к шаманским картам за подсказкой, инструкция по применению:\n"
            "1️⃣  Загадайте ваше желание и задайте вопрос в формате: "
            "«Что мне нужно сделать, чтобы... (добавьте своё)».\n"
            "2️⃣Выберите один из двух способов получения подсказки от карт:\n"
            "- Нажмите «Выбрать карту самой» сделайте глубокий вдох-выдох, "
            "закройте глазки, выберите номер карты от 1 до 45 и введите его "
            "в окошко, наслаждайтесь расшифровкой и советом карт🍀\n"
            "- Нажмите «Получить случайным образом» сделайте глубокий "
            "вдох-выдох, проговорите свой запрос, нажмите на кнопку и получите "
            "случайным образом карту, наслаждайтесь расшифровкой и советом карт🍀\n"
            "Приготовьтесь, ваш совет от карт уже в пути.",
            reply_markup=main_keyboard,
        )

        balance = await get_balance(callback.from_user.id)
        await callback.message.answer(f"💫 Доступно карт: {balance}")

        if balance == 0:
            await send_tariffs(callback.message)


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
    F.text == "✨ Получить случайным образом"
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
    F.text == "🔢 Выбрать карту самой"
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

    await callback.message.answer(
        "Выберите, как хотите получить подсказку:",
        reply_markup=main_keyboard,
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