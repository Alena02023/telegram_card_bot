import asyncio
import os
import secrets
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile,
)
from dotenv import load_dotenv


# -------------------------
# НАСТРОЙКИ
# -------------------------

logging.basicConfig(level=logging.INFO)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден")

bot = Bot(token=TOKEN)
dp = Dispatcher()


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
        ),
    }
    for i in range(1, 46)
}


# -------------------------
# ГЛАВНОЕ МЕНЮ
# -------------------------

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
                text="✨ Хочу больше карт"
            )
        ],
    ],
    resize_keyboard=True,
)


# -------------------------
# ФУНКЦИЯ ОТПРАВКИ КАРТЫ
# -------------------------

async def send_card(message: Message, card_number: int):

    card = cards[card_number]

    image_path = f"cards/card_{card_number}.png"

    # Проверяем, существует ли изображение
    if os.path.exists(image_path):

        photo = FSInputFile(image_path)

        await message.answer_photo(
            photo=photo,
            caption=(
                f"🎴 {card['title']}\n\n"
                f"{card['description']}"
            ),
        )

    else:
        # Если картинки вдруг нет, бот всё равно отправит текст
        await message.answer(
            f"🎴 {card['title']}\n\n"
            f"{card['description']}\n\n"
            "⚠️ Изображение карты пока не найдено."
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
        reply_markup=main_keyboard,
    )


# -------------------------
# СЛУЧАЙНАЯ КАРТА
# -------------------------

@dp.message(F.text == "🎴 Выбрать случайную карту")
async def random_card_handler(message: Message):

    card_number = secrets.randbelow(45) + 1

    await send_card(
        message=message,
        card_number=card_number,
    )


# -------------------------
# ВЫБОР КАРТЫ ПО НОМЕРУ
# -------------------------

@dp.message(F.text == "🔢 Выбрать карту по номеру")
async def choose_number_handler(message: Message):

    await message.answer(
        "🔢 Введите номер карты от 1 до 45:"
    )


# -------------------------
# ХОЧУ БОЛЬШЕ КАРТ
# -------------------------

@dp.message(F.text == "✨ Хочу больше карт")
async def more_cards_handler(message: Message):

    await message.answer(
        "✨ Здесь скоро появится возможность "
        "приобрести дополнительные карты.\n\n"
        "На следующем этапе мы добавим тарифы "
        "и тестовую оплату."
    )


# -------------------------
# ОБРАБОТКА НОМЕРА КАРТЫ
# -------------------------

@dp.message(F.text.regexp(r"^\d+$"))
async def number_handler(message: Message):

    number = int(message.text)

    if 1 <= number <= 45:

        await send_card(
            message=message,
            card_number=number,
        )

    else:

        await message.answer(
            "❌ Такой карты нет.\n\n"
            "Введите номер от 1 до 45."
        )


# -------------------------
# ОСТАЛЬНЫЕ СООБЩЕНИЯ
# -------------------------

@dp.message()
async def other_message_handler(message: Message):

    await message.answer(
        "Пожалуйста, воспользуйтесь кнопками меню 👇",
        reply_markup=main_keyboard,
    )


# -------------------------
# ЗАПУСК БОТА
# -------------------------

async def main():

    me = await bot.get_me()

    print(f"Подключение успешно: @{me.username}")
    print("Бот запущен и ждёт сообщения...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())