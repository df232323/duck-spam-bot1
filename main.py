import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, LOG_FILE, LOG_LEVEL
import database
from handlers import setup_handlers

# Создаём папку для логов
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Скрываем логи Telethon
logging.getLogger('telethon').setLevel(logging.WARNING)

# Инициализация базы данных
database.init_db()

# Создание бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Регистрация обработчиков
setup_handlers(dp)

async def main():
    """Основная функция запуска бота"""
    logging.info("🦆 DUCK SPAM БОТ ЗАПУЩЕН!")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка polling: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("\n👋 Бот остановлен")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")