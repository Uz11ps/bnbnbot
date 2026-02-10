import asyncio
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse
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
        # Извлекаем фактическое событие из Update
        actual_event = event.message or event.callback_query
        if not actual_event:
            return await handler(event, data)

        # Работаем только в личных чатах
        chat = actual_event.chat if event.message else actual_event.message.chat
        if chat.type != ChatType.PRIVATE:
            return await handler(event, data)
        
        user_id = actual_event.from_user.id
        is_callback = bool(event.callback_query)
        
        # Список исключений (где проверка не нужна)
        if not is_callback and actual_event.text and actual_event.text.startswith("/start"):
            # Для команды /start мы НЕ пропускаем проверку, а вызываем её внутри хендлера
            # Но Middleware должен пропустить событие дальше
            return await handler(event, data)
            
        exceptions = ["accept_terms", "check_subscription", "menu_agreement"]
        if is_callback and event.callback_query.data in exceptions:
            return await handler(event, data)
            
        # 1. Проверка блокировки (даже для админов, если они сами себя заблокировали)
        db = data.get("db")
        if await db.get_user_blocked(user_id):
            lang = await db.get_user_language(user_id)
            from bot.strings import get_string
            text = get_string("user_blocked", lang)
            if is_callback:
                await event.callback_query.answer(text, show_alert=True)
            else:
                await event.message.answer(text)
            return

        # 2. Пропускаем администраторов для остальных проверок (подписка и т.д.)
        settings = data.get("settings")
        if settings and user_id in (settings.admin_ids or []):
            return await handler(event, data)
            
        # Основная проверка
        bot = data.get("bot")
        
        # Вызываем нашу функцию проверки (передаем actual_event вместо Update)
        if await _ensure_access(actual_event, db, bot):
            return await handler(event, data)
            
        return

async def main() -> None:
    settings = load_settings()

    # Получаем путь к базе из настроек
    db_url = settings.database_url
    if "sqlite+aiosqlite:///" in db_url:
        db_path = db_url.replace("sqlite+aiosqlite:///", "")
    else:
        db_path = "data/bot.db"

    # Приводим путь к абсолютному, если это не Docker (в Docker /app/data уже абсолютный)
    if not os.path.isabs(db_path) and not db_path.startswith("/app"):
        db_path = os.path.join(os.getcwd(), db_path)

    db = Database(db_path=db_path)
    await db.init()

    # Пробуем получить прокси из БД
    proxy_url = await db.get_app_setting("bot_proxy")
    if not proxy_url:
        proxy_url = os.getenv("BOT_HTTP_PROXY", "").strip()
    # Фолбэк: берём первый активный прокси из таблицы (стандартный германский)
    if not proxy_url:
        for url in (await db.get_active_proxies_urls() or [])[:1]:
            proxy_url = url
            break

    def _parse_proxy(raw: str) -> tuple[str, object] | str | None:
        """Возвращает (url, BasicAuth) или url. Всегда (url, auth) при наличии учётки."""
        if not raw or not raw.strip():
            return None
        raw = raw.strip().split(",")[0].strip()
        from aiohttp import BasicAuth

        # URL: http://user:pass@host:port — urlparse
        if raw.startswith("http://") or raw.startswith("https://"):
            try:
                p = urlparse(raw)
                if p.hostname:
                    port = p.port if p.port is not None else (80 if p.scheme == "http" else 443)
                    proxy_base = f"{p.scheme}://{p.hostname}:{port}"
                    if p.username is not None and p.password is not None:
                        return (proxy_base, BasicAuth(login=p.username, password=p.password))
                    return proxy_base
            except (ValueError, TypeError):
                pass
            # Fallback: http://user:host:port (3 части) или http://host:port:user:pass (4 части)
            rest = raw.split("://", 1)[-1].split("/")[0]
            parts = rest.split(":")
            if len(parts) == 4 and parts[1].isdigit():
                host, port, user, password = parts[0], parts[1], parts[2], parts[3]
                return (f"http://{host}:{port}", BasicAuth(login=user, password=password))
            if len(parts) == 3 and parts[2].isdigit():
                user, host, port = parts[0], parts[1], parts[2]
                return (f"http://{host}:{port}", BasicAuth(login=user, password=""))
            if len(parts) == 3 and parts[1].isdigit():
                host, port, user = parts[0], parts[1], parts[2]
                return (f"http://{host}:{port}", BasicAuth(login=user, password=""))
            return raw

        # IP:PORT:USER:PASS
        parts = raw.split(":")
        if len(parts) == 4:
            host, port, user, password = parts[0], parts[1], parts[2], parts[3]
            try:
                int(port)
            except ValueError:
                return None
            return (f"http://{host}:{port}", BasicAuth(login=user, password=password))
        if len(parts) == 2:
            try:
                int(parts[1])
            except ValueError:
                return None
            return f"http://{parts[0]}:{parts[1]}"
        return None

    selected_proxy = _parse_proxy(proxy_url) if proxy_url else None

    if selected_proxy:
        from aiogram.client.session.aiohttp import AiohttpSession
        proxy_arg = selected_proxy if isinstance(selected_proxy, tuple) else selected_proxy
        try:
            session = AiohttpSession(proxy=proxy_arg)
            bot = Bot(
                token=settings.bot_token,
                session=session,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            host_log = proxy_arg[0] if isinstance(proxy_arg, tuple) else (proxy_arg.split("@")[-1] if "@" in proxy_arg else proxy_arg)
            logger.info(f"Бот запущен через прокси: {host_log}")
        except Exception as e:
            logger.error(f"Ошибка настройки прокси: {e}. Запуск без прокси.")
            bot = Bot(
                token=settings.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
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


