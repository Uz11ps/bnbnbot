import asyncio
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.config import load_settings
from bot.db import Database
from bot.handlers.start import router as start_router
from bot.handlers.admin import router as admin_router


# Настройка логирования
log_dir = "/app/data"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "bot.log")

# Создаем root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Очищаем существующие handlers
root_logger.handlers.clear()

# Handler для файла (ротация при 10MB, максимум 5 файлов)
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

# Handler для консоли
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    '%(levelname)s:%(name)s:%(message)s'
)
console_handler.setFormatter(console_formatter)

# Добавляем handlers
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Тестовое сообщение для проверки создания файла
logger = logging.getLogger(__name__)
logger.info(f"Логирование настроено. Файл логов: {log_file}")


@asynccontextmanager
async def lifespan(dp: Dispatcher, db: Database):
    await db.init()
    yield


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запуск бота"),
        ]
    )


async def main() -> None:
    settings = load_settings()

    # Учитываем системные переменные прокси только если они явно нужны (в данном случае для ТГ они не нужны)
    # т.к. сервер находится в Европе. Удаляем глобальную установку прокси.
    
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # Извлекаем путь к БД из DATABASE_URL (поддержка формата sqlite+aiosqlite:///./bot.db)
    db_path = "bot.db"
    db_url = settings.database_url
    if db_url.startswith("sqlite"):
        if ":///" in db_url:
            db_path = db_url.split("///", 1)[-1] or "bot.db"
        else:
            db_path = "bot.db"

    db = Database(db_path=db_path)

    dp.include_router(admin_router)
    dp.include_router(start_router)

    async with lifespan(dp, db):
        dp['db'] = db  # dependency injection via context
        dp['settings'] = settings
        await set_commands(bot)
        await dp.start_polling(bot, db=db, settings=settings)


if __name__ == "__main__":
    asyncio.run(main())


