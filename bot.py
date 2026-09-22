import asyncio
import os
import secrets
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден")

# Создаём бота
bot = Bot(token=TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)


# -------------------------
# ТЕСТОВЫЕ 45 КАРТ
# -------------------------

cards = {
    i: {
        "title": f"Карта №{i}",
        "description": (
            f"Это тестовое описание карты №{i}.\n\n"
            "Позже здесь будет настоящее описание карты, "
            "которое предоставит заказчик."
        )
    }
    for i in range(1, 46)
}


# -------------------------
# ГЛАВНОЕ МЕНЮ
# -------------------------

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🎴 Выбрать случайную карту")
        ],
        [
            KeyboardButton(text="🔢 Выбрать карту по номеру")
        ],
        [
            KeyboardButton(text="✨ Хочу больше карт")
        ]
    ],
    resize_keyboard=True
)


# -------------------------
# /START
# -------------------------

@dp.message(CommandStart())
async def start_handler(message: Message):

    await message.answer(
        "🎴 Добро пожаловать!\n\n"
        "Перед вами колода из 45 карт.\n\n"
        "Вы можете выбрать случайную карту "
        "или указать её номер самостоятельно.",
        reply_markup=main_keyboard
    )


# -------------------------
# СЛУЧАЙНАЯ КАРТА
# -------------------------

@dp.message(F.text == "🎴 Выбрать случайную карту")
async def random_card_handler(message: Message):

    card_number = secrets.randbelow(45) + 1
    card = cards[card_number]

    await message.answer(
        f"🎴 {card['title']}\n\n"
        f"{card['description']}"
    )


# -------------------------
# ВЫБОР ПО НОМЕРУ
# -------------------------

@dp.message(F.text == "🔢 Выбрать карту по номеру")
async def choose_number_handler(message: Message):

    await message.answer(
        "Введите номер карты от 1 до 45:"
    )


# -------------------------
# КНОПКА ПОКУПКИ
# -------------------------

@dp.message(F.text == "✨ Хочу больше карт")
async def more_cards_handler(message: Message):

    await message.answer(
        "✨ Здесь скоро появится возможность "
        "приобрести дополнительные карты.\n\n"
        "На следующем этапе мы добавим тарифы и оплату."
    )


# -------------------------
# ОБРАБОТКА ЧИСЕЛ
# -------------------------

@dp.message(F.text.regexp(r"^\d+$"))
async def number_handler(message: Message):

    number = int(message.text)

    if 1 <= number <= 45:

        card = cards[number]

        await message.answer(
            f"🎴 {card['title']}\n\n"
            f"{card['description']}"
        )

    else:

        await message.answer(
            "Такой карты нет.\n\n"
            "Введите номер от 1 до 45."
        )


# -------------------------
# ОСТАЛЬНЫЕ СООБЩЕНИЯ
# -------------------------

@dp.message()
async def other_message_handler(message: Message):

    await message.answer(
        "Пожалуйста, воспользуйтесь кнопками меню 👇",
        reply_markup=main_keyboard
    )


# -------------------------
# ЗАПУСК
# -------------------------

async def main():

    me = await bot.get_me()

    print(f"Подключение успешно: @{me.username}")
    print("Бот запущен и ждёт сообщения...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())