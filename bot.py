import asyncio
import os
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message):
    print("Получена команда /start")
    await message.answer(
        "🎴 Добро пожаловать!\n\n"
        "Бот работает! ✅"
    )


@dp.message()
async def any_message(message: Message):
    print(f"Получено сообщение: {message.text}")
    await message.answer("Я получил ваше сообщение ✅")


async def main():
    me = await bot.get_me()
    print(f"Подключение успешно: @{me.username}")
    print("Бот запущен и ждёт сообщения...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())