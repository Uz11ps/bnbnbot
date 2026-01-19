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
            BotCommand(command="start", description="🏠 Главное меню"),
            BotCommand(command="profile", description="👤 Мой профиль"),
            BotCommand(command="settings", description="⚙️ Настройки"),
            BotCommand(command="reset", description="🔄 Сброс"),
            BotCommand(command="help", description="❓ Инструкция"),
        ]
    )


from aiogram.enums import ParseMode, ChatType
from aiogram.types import Message, CallbackQuery
from bot.handlers.start import _ensure_access
import logging

class AccessMiddleware:
    async def __call__(self, handler, event, data):
        # Работаем только в личных чатах
        if not (isinstance(event, (Message, CallbackQuery)) and event.chat.type == ChatType.PRIVATE):
            return await handler(event, data)
        
        # Проверяем, не является ли это командой /start или системными кнопками
        is_callback = isinstance(event, CallbackQuery)
        callback_data = event.data if is_callback else None
        
        # Список исключений (где проверка не нужна)
        exceptions = ["accept_terms", "check_subscription", "menu_agreement"]
        if not is_callback and event.text and event.text.startswith("/start"):
            return await handler(event, data)
        if is_callback and callback_data in exceptions:
            return await handler(event, data)
            
        # Пропускаем администраторов
        settings = data.get("settings")
        user_id = event.from_user.id
        if settings and user_id in (settings.admin_ids or []):
            return await handler(event, data)
            
        # Основная проверка
        db = data.get("db")
        bot = data.get("bot")
        
        # Вызываем нашу функцию проверки
        if await _ensure_access(event, db, bot):
            return await handler(event, data)
            
        # Если проверка не прошла, _ensure_access сам отправит нужное сообщение
        return

async def main() -> None:
    settings = load_settings()

    # Жестко используем /app/data/bot.db для Docker
    db_path = "/app/data/bot.db"
    
    # Если мы не в Docker и файла по этому пути нет, пробуем локальный путь
    if not os.path.exists("/app") and not os.path.exists(db_path):
        db_path = "data/bot.db"

    db = Database(db_path=db_path)
    await db.init()

    # Пробуем получить прокси из БД
    proxy_url = await db.get_app_setting("bot_proxy")
    
    # Если в БД нет, берем из .env
    if not proxy_url:
        proxy_url = os.getenv("BOT_HTTP_PROXY")
    
    if proxy_url and ":" in proxy_url and "://" not in proxy_url:
        # Приводим к формату URL
        parts = proxy_url.split(":")
        if len(parts) == 4:
            proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        elif len(parts) == 2:
            proxy_url = f"http://{parts[0]}:{parts[1]}"

    if proxy_url:
        from aiogram.client.session.aiohttp import AiohttpSession
        session = AiohttpSession(proxy=proxy_url)
        bot = Bot(
            token=settings.bot_token,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        logger.info(f"Бот запущен через прокси: {proxy_url}")
    else:
        bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрация Middleware
    dp.update.outer_middleware(AccessMiddleware())

    dp.include_router(admin_router)
    dp.include_router(start_router)

    async with lifespan(dp, db):
        dp['db'] = db  # dependency injection via context
        dp['settings'] = settings
        await set_commands(bot)
        await dp.start_polling(bot, db=db, settings=settings)


if __name__ == "__main__":
    asyncio.run(main())


