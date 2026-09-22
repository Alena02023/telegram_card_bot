import asyncio
import logging
import os
import secrets

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

logging.basicConfig(level=logging.INFO)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден")

bot = Bot(token=TOKEN)
dp = Dispatcher()

DATABASE = "bot_demo_clean.db"


# =========================================================
# 45 ТЕСТОВЫХ КАРТ
# =========================================================

cards = {
    i: {
        "title": f"Карта №{i}",
        "description": (
            f"Это тестовое описание карты №{i}.\n\n"
            "Позже здесь будет настоящее описание карты, "
            "которое предоставит заказчик."
        ),
    }
    for i in range(1, 46)
}


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
# ГЛАВНОЕ МЕНЮ
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


# =========================================================
# КЛАВИАТУРА ТАРИФОВ
# =========================================================

def get_tariffs_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎴 1 карта — 50 ₽",
                    callback_data="tariff_1",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎴 3 карты — 120 ₽",
                    callback_data="tariff_3",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎴 5 карт — 180 ₽",
                    callback_data="tariff_5",
                )
            ],
        ]
    )


# =========================================================
# КНОПКА "ХОЧУ БОЛЬШЕ КАРТ"
# =========================================================

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
            INSERT OR IGNORE INTO users (user_id, balance)
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

        if row:
            return row[0]

        return 0


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
            (amount, user_id),
        )

        await db.commit()


async def use_card(user_id: int) -> bool:

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
# ПОКАЗАТЬ ТАРИФЫ
# =========================================================

async def send_tariffs(message: Message):

    await message.answer(
        "✨ Выберите пакет дополнительных карт:\n\n"
        "🎴 1 карта — 50 ₽\n"
        "🎴 3 карты — 120 ₽\n"
        "🎴 5 карт — 180 ₽\n\n"
        "Сейчас используется демонстрационная оплата.\n"
        "Настоящие деньги списываться не будут.",
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

    # Если карт уже нет
    if not success:

        await message.answer(
            "✨ У вас закончились доступные карты.\n\n"
            "Выберите пакет, чтобы получить новые карты:",
            reply_markup=get_tariffs_keyboard(),
        )

        return

    card = cards[card_number]

    image_path = f"cards/card_{card_number}.png"

    balance = await get_balance(user_id)

    caption = (
        f"🎴 {card['title']}\n\n"
        f"{card['description']}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Осталось карт: {balance}"
    )

    # Если пользователь только что потратил последнюю карту
    if balance == 0:

        caption += (
            "\n\n"
            "✨ Это была ваша последняя доступная карта.\n"
            "Хотите открыть ещё?"
        )

        reply_markup = get_buy_keyboard()

    else:

        reply_markup = None

    if os.path.exists(image_path):

        photo = FSInputFile(image_path)

        await message.answer_photo(
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
        )

    else:

        await message.answer(
            caption,
            reply_markup=reply_markup,
        )


# =========================================================
# /START
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: Message):

    await create_user(message.from_user.id)

    balance = await get_balance(
        message.from_user.id
    )

    text = (
        "🎴 Добро пожаловать!\n\n"
        "Перед вами колода из 45 карт.\n\n"
        "🎁 Новый пользователь получает "
        "1 бесплатную карту.\n\n"
        "Вы можете выбрать случайную карту "
        "или указать её номер самостоятельно.\n\n"
        f"💰 Доступно карт: {balance}"
    )

    await message.answer(
        text,
        reply_markup=main_keyboard,
    )

    # Если пользователь уже потратил карту
    if balance == 0:

        await message.answer(
            "✨ У вас сейчас нет доступных карт.\n\n"
            "Вы можете приобрести дополнительные:",
            reply_markup=get_tariffs_keyboard(),
        )


# =========================================================
# МОЙ БАЛАНС
# =========================================================

@dp.message(F.text == "💰 Мой баланс")
async def balance_handler(message: Message):

    balance = await get_balance(
        message.from_user.id
    )

    if balance > 0:

        await message.answer(
            f"💰 Ваш баланс: {balance} карт."
        )

    else:

        await message.answer(
            "💰 Ваш баланс: 0 карт.\n\n"
            "✨ Хотите получить дополнительные карты?",
            reply_markup=get_tariffs_keyboard(),
        )


# =========================================================
# СЛУЧАЙНАЯ КАРТА
# =========================================================

@dp.message(F.text == "🎴 Выбрать случайную карту")
async def random_card_handler(message: Message):

    balance = await get_balance(
        message.from_user.id
    )

    if balance <= 0:

        await message.answer(
            "✨ У вас закончились доступные карты.\n\n"
            "Выберите пакет:",
            reply_markup=get_tariffs_keyboard(),
        )

        return

    card_number = secrets.randbelow(45) + 1

    await send_card(
        message=message,
        card_number=card_number,
    )


# =========================================================
# ВЫБОР КАРТЫ ПО НОМЕРУ
# =========================================================

@dp.message(F.text == "🔢 Выбрать карту по номеру")
async def choose_number_handler(message: Message):

    balance = await get_balance(
        message.from_user.id
    )

    if balance <= 0:

        await message.answer(
            "✨ У вас закончились доступные карты.\n\n"
            "Выберите пакет:",
            reply_markup=get_tariffs_keyboard(),
        )

        return

    await message.answer(
        "🔢 Введите номер карты от 1 до 45:"
    )


# =========================================================
# КНОПКА ГЛАВНОГО МЕНЮ "ХОЧУ БОЛЬШЕ КАРТ"
# =========================================================

@dp.message(F.text == "✨ Хочу больше карт")
async def more_cards_handler(message: Message):

    await send_tariffs(message)


# =========================================================
# INLINE-КНОПКА "ХОЧУ БОЛЬШЕ КАРТ"
# =========================================================

@dp.callback_query(F.data == "show_tariffs")
async def show_tariffs_handler(
    callback: CallbackQuery,
):

    await callback.message.answer(
        "✨ Выберите пакет дополнительных карт:\n\n"
        "🎴 1 карта — 50 ₽\n"
        "🎴 3 карты — 120 ₽\n"
        "🎴 5 карт — 180 ₽\n\n"
        "Сейчас используется демонстрационная оплата.",
        reply_markup=get_tariffs_keyboard(),
    )

    await callback.answer()


# =========================================================
# ВЫБОР ТАРИФА
# =========================================================

@dp.callback_query(F.data.startswith("tariff_"))
async def tariff_handler(
    callback: CallbackQuery,
):

    tariff_id = callback.data.split("_")[1]

    tariff = tariffs.get(tariff_id)

    if not tariff:

        await callback.answer(
            "Тариф не найден."
        )

        return

    cards_amount = tariff["cards"]
    price = tariff["price"]

    payment_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💳 Оплатить {price} ₽ (ДЕМО)",
                    callback_data=f"pay_{tariff_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к тарифам",
                    callback_data="back_to_tariffs",
                )
            ],
        ]
    )

    await callback.message.edit_text(
        "🎴 Вы выбрали пакет:\n\n"
        f"Количество карт: {cards_amount}\n"
        f"Стоимость: {price} ₽\n\n"
        "Для демонстрации нажмите кнопку оплаты.\n\n"
        "⚠️ Настоящие деньги списываться не будут.",
        reply_markup=payment_keyboard,
    )

    await callback.answer()


# =========================================================
# НАЗАД К ТАРИФАМ
# =========================================================

@dp.callback_query(F.data == "back_to_tariffs")
async def back_to_tariffs_handler(
    callback: CallbackQuery,
):

    await callback.message.edit_text(
        "✨ Выберите пакет дополнительных карт:\n\n"
        "🎴 1 карта — 50 ₽\n"
        "🎴 3 карты — 120 ₽\n"
        "🎴 5 карт — 180 ₽\n\n"
        "Сейчас используется демонстрационная оплата.",
        reply_markup=get_tariffs_keyboard(),
    )

    await callback.answer()


# =========================================================
# ДЕМО-ОПЛАТА
# =========================================================

@dp.callback_query(F.data.startswith("pay_"))
async def payment_handler(
    callback: CallbackQuery,
):

    tariff_id = callback.data.split("_")[1]

    tariff = tariffs.get(tariff_id)

    if not tariff:

        await callback.answer(
            "Ошибка оплаты."
        )

        return

    cards_amount = tariff["cards"]
    price = tariff["price"]

    user_id = callback.from_user.id

    # ДЕМО:
    # реальной оплаты здесь пока нет.
    # Просто начисляем выбранное количество карт.
    await add_cards(
        user_id=user_id,
        amount=cards_amount,
    )

    balance = await get_balance(user_id)

    await callback.message.edit_text(
        "✅ ДЕМО-ОПЛАТА УСПЕШНА\n\n"
        f"💳 Сумма: {price} ₽\n"
        f"🎴 Начислено карт: {cards_amount}\n\n"
        f"💰 Теперь доступно карт: {balance}\n\n"
        "Можете продолжить выбирать карты 👇"
    )

    await callback.answer(
        "Карты начислены!"
    )


# =========================================================
# ОБРАБОТКА НОМЕРОВ 1–45
# =========================================================

@dp.message(F.text.regexp(r"^\d+$"))
async def number_handler(message: Message):

    number = int(message.text)

    if not 1 <= number <= 45:

        await message.answer(
            "❌ Такой карты нет.\n\n"
            "Введите номер от 1 до 45."
        )

        return

    balance = await get_balance(
        message.from_user.id
    )

    if balance <= 0:

        await message.answer(
            "✨ У вас закончились доступные карты.\n\n"
            "Выберите пакет:",
            reply_markup=get_tariffs_keyboard(),
        )

        return

    await send_card(
        message=message,
        card_number=number,
    )


# =========================================================
# ОСТАЛЬНЫЕ СООБЩЕНИЯ
# =========================================================

@dp.message()
async def other_message_handler(message: Message):

    await message.answer(
        "Пожалуйста, воспользуйтесь кнопками меню 👇",
        reply_markup=main_keyboard,
    )


# =========================================================
# ЗАПУСК БОТА
# =========================================================

async def main():

    await init_db()

    me = await bot.get_me()

    print(f"Подключение успешно: @{me.username}")
    print("База данных подключена.")
    print("Бот запущен и ждёт сообщения...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())