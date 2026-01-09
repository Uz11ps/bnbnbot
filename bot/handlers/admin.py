from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from io import BytesIO
import asyncio
from typing import Optional
import subprocess
import logging
import requests
import os

from bot.config import Settings, load_settings
from bot.db import Database

logger = logging.getLogger(__name__)
from bot.keyboards import (
    admin_main_keyboard,
    admin_categories_keyboard,
    admin_users_keyboard,
    admin_user_actions_keyboard,
    admin_user_history_keyboard,
    admin_models_keyboard,
    admin_models_category_keyboard,
    admin_models_cloth_keyboard,
    admin_models_actions_keyboard,
    admin_model_list_keyboard,
    admin_model_edit_keyboard,
    admin_prompt_pick_keyboard,
    admin_model_created_keyboard,
    admin_api_keys_keyboard,
    main_menu_keyboard,
    broadcast_skip_keyboard,
    broadcast_confirm_keyboard,
    admin_own_prompts_keyboard,
    admin_own_variant_prompts_keyboard,
    admin_own_variant_api_keys_keyboard,
    admin_category_prices_keyboard,
)


router = Router()


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in (settings.admin_ids or [])


async def _safe_answer(callback: CallbackQuery, text: str | None = None, show_alert: bool = False) -> None:
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest:
        pass
    except Exception:
        pass


async def _replace_with_text(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        if getattr(callback.message, "photo", None):
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=reply_markup)
        else:
            await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await callback.message.answer(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            pass


@router.message(Command("admin"))
async def admin_entry(message: Message, settings: Settings, db: Database) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    maint = await db.get_maintenance()
    status = "Включены" if maint else "Выключены"
    await message.answer(f"🛠 Админ-панель\nТехработы: {status}", reply_markup=admin_main_keyboard())


@router.message(Command("add_balance"))
async def cmd_add_balance(message: Message, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("Использование: /add_balance <user_id> <amount>")
        return
    try:
        user_id = int(parts[1])
        amount = int(parts[2])
    except Exception:
        await message.answer("Неверные параметры. Пример: /add_balance 123456 50")
        return
    # Гарантируем наличие пользователя
    await db.upsert_user(user_id=user_id, username=None, first_name=None, last_name=None)
    await db.increment_user_balance(user_id, amount)
    new_bal = await db.get_user_balance(user_id)
    await message.answer(f"OK. Баланс пользователя {user_id}: {new_bal} (изменение: +{amount})")


@router.message(Command("remove_balance"))
async def cmd_remove_balance(message: Message, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("Использование: /remove_balance <user_id> <amount>")
        return
    try:
        user_id = int(parts[1])
        amount = int(parts[2])
    except Exception:
        await message.answer("Неверные параметры. Пример: /remove_balance 123456 10")
        return
    await db.upsert_user(user_id=user_id, username=None, first_name=None, last_name=None)
    await db.increment_user_balance(user_id, -abs(amount))
    new_bal = await db.get_user_balance(user_id)
    await message.answer(f"OK. Баланс пользователя {user_id}: {new_bal} (изменение: -{abs(amount)})")


@router.message(Command("reset_user"))
async def cmd_reset_user(message: Message, db: Database, settings: Settings, state: FSMContext, bot: Bot) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /reset_user <user_id>")
        return
    try:
        user_id = int(parts[1])
    except Exception:
        await message.answer("Неверные параметры. Пример: /reset_user 123456789")
        return
    # Сбрасываем состояние FSM для пользователя через storage
    from aiogram.fsm.storage.base import StorageKey
    
    # Создаем ключ для пользователя
    key = StorageKey(
        bot_id=bot.id,
        chat_id=user_id,
        user_id=user_id
    )
    
    # Получаем storage из event (через dependency injection)
    try:
        # В aiogram 3.x можно получить storage через event
        # Создаем новый контекст для целевого пользователя
        # Получаем storage из state (который уже имеет доступ к storage)
        # Используем тот же storage, что и текущий state
        target_state = FSMContext(
            storage=state.storage,
            key=key
        )
        await target_state.clear()
        await message.answer(f"✅ Состояние пользователя {user_id} сброшено")
    except Exception as e:
        # Если не удалось, очищаем состояние текущего пользователя, если это он
        if message.from_user.id == user_id:
            await state.clear()
            await message.answer(f"✅ Состояние пользователя {user_id} сброшено")
        else:
            logger.error(f"Ошибка при сбросе состояния пользователя {user_id}: {e}")
            await message.answer(f"⚠️ Ошибка при сбросе состояния: {e}")


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    stats = await db.get_stats()
    text = (
        "📊 Статистика\n\n"
        f"Всего пользователей: {stats['total_users']}\n"
        f"Суммарный баланс: {stats['total_balance']}\n"
        f"Новых сегодня: {stats['today_users']}\n"
    )
    try:
        await callback.message.edit_text(text, reply_markup=admin_main_keyboard())
    except TelegramBadRequest:
        pass
    await _safe_answer(callback)


@router.callback_query(F.data == "admin_main")
async def admin_main_back(callback: CallbackQuery, settings: Settings, db: Database) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    maint = await db.get_maintenance()
    status = "Включены" if maint else "Выключены"
    await callback.message.edit_text(f"🛠 Админ-панель\nТехработы: {status}", reply_markup=admin_main_keyboard())
    await _safe_answer(callback)

@router.callback_query(F.data == "admin_categories")
async def admin_categories(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    status = await db.list_categories_enabled()
    await _replace_with_text(callback, "Категории (нажмите, чтобы включить/отключить):", reply_markup=admin_categories_keyboard(status))
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("admin_toggle_cat:"))
async def admin_toggle_category(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    name = callback.data.split(":", 1)[1]
    current = await db.get_category_enabled(name)
    await db.set_category_enabled(name, not current)
    status = await db.list_categories_enabled()
    await _replace_with_text(callback, "Категории (нажмите, чтобы включить/отключить):", reply_markup=admin_categories_keyboard(status))
    await _safe_answer(callback, "Сохранено", show_alert=False)


# Category prices management
@router.callback_query(F.data == "admin_category_prices")
async def admin_category_prices(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    prices = await db.list_category_prices()
    await _replace_with_text(callback, "💰 Цены категорий (нажмите для редактирования):", reply_markup=admin_category_prices_keyboard(prices))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_price_edit:"))
async def admin_price_edit_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    category = callback.data.split(":", 1)[1]
    current_price = await db.get_category_price(category)
    category_names = {
        "female": "Женская",
        "male": "Мужская",
        "child": "Детская",
        "storefront": "Витринное фото",
        "whitebg": "На белом фоне",
        "random": "Одежда и обувь",
        "own": "Пробовать своё",
        "own_variant": "Свой вариант",
    }
    cat_name = category_names.get(category, category)
    current_price_str = f"{current_price / 10:.1f}" if current_price % 10 != 0 else f"{current_price // 10}"
    await state.set_state(OwnPromptState.waiting_text)
    await state.update_data(price_category=category)
    await _replace_with_text(callback, f"Текущая цена категории «{cat_name}»: {current_price_str} токен(ов)\n\nОтменю для редактирования цены. Введите новую цену в формате: число или число с точкой (например: 1, 1.2, 2.0). Цена указывается в токенах (например: 1 = 1 токен, 1.2 = 1.2 токена).\n\nОтправьте новую цену:")

# Поиск пользователя по ID
class UserSearch(StatesGroup):
    waiting_id = State()

@router.callback_query(F.data == "admin_user_search")
async def admin_user_search_start(callback: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await state.set_state(UserSearch.waiting_id)
    await _replace_with_text(callback, "Введите ID пользователя (числом):")
    await _safe_answer(callback)

@router.message(UserSearch.waiting_id)
async def admin_user_search_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    txt = (message.text or "").strip()
    try:
        uid = int(txt)
    except Exception:
        await message.answer("Укажите ID числом, например: 123456789")
        return
    balance = await db.get_user_balance(uid)
    blocked = await db.get_user_blocked(uid)
    state_txt = "⛔ Заблокирован" if blocked else "✅ Активен"
    text = f"👤 Пользователь {uid}\nСтатус: {state_txt}\nТекущий баланс: {balance}\n\nИстория транзакций: нажмите кнопку ниже."
    await state.clear()
    await message.answer(text, reply_markup=admin_user_actions_keyboard(uid))


PAGE_SIZE = 10


@router.callback_query(F.data.startswith("admin_users_page:"))
async def admin_users_page(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    try:
        page = int(callback.data.split(":", 1)[1])
    except Exception:
        page = 0
    offset = page * PAGE_SIZE
    users = await db.list_users_page(offset=offset, limit=PAGE_SIZE + 1)
    has_next = len(users) > PAGE_SIZE
    users_page = users[:PAGE_SIZE]
    text = "👥 Пользователи:"
    try:
        await callback.message.edit_text(text, reply_markup=admin_users_keyboard(users_page, page, has_next))
    except TelegramBadRequest:
        pass
    await _safe_answer(callback)


# Models management


@router.callback_query(F.data == "admin_models")
async def admin_models_root(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await callback.message.edit_text("🧩 Модели", reply_markup=admin_models_keyboard())
    await _safe_answer(callback)
@router.callback_query(F.data == "admin_maint_on")
async def admin_maintenance_on(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await db.set_maintenance(True)
    try:
        await callback.message.edit_text("🛠 Админ-панель\nТехработы: Включены", reply_markup=admin_main_keyboard())
    except TelegramBadRequest:
        pass
    await _safe_answer(callback, "Техработы включены", show_alert=False)


@router.callback_query(F.data == "admin_maint_off")
async def admin_maintenance_off(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await db.set_maintenance(False)
    try:
        await callback.message.edit_text("🛠 Админ-панель\nТехработы: Выключены", reply_markup=admin_main_keyboard())
    except TelegramBadRequest:
        pass
    await _safe_answer(callback, "Техработы выключены", show_alert=False)


def _get_docker_logs(lines: int = 100) -> str:
    """Получает последние логи из Docker контейнера"""
    # Сначала пробуем docker logs
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(lines), "fashion-bot"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout or "Логи пусты"
        else:
            # Если docker logs не сработал, пробуем альтернативы
            pass
    except FileNotFoundError:
        # Docker команда не найдена - пробуем альтернативы
        pass
    except subprocess.TimeoutExpired:
        return "⏱ Таймаут при получении логов через docker."
    except Exception:
        pass
    
    # Альтернатива 1: Пробуем docker compose logs
    try:
        result = subprocess.run(
            ["docker", "compose", "logs", "--tail", str(lines), "bot"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd="/app"  # Может не работать, но попробуем
        )
        if result.returncode == 0:
            return result.stdout or "Логи пусты"
    except Exception:
        pass
    
    # Альтернатива 2: Пробуем прочитать из файла логов (если настроено)
    log_files = [
        "/app/data/bot.log",
        "/app/bot.log",
        "/var/log/bot.log",
        "/tmp/bot.log",
    ]
    
    checked_files = []
    for log_file in log_files:
        try:
            checked_files.append(f"{log_file} ({'существует' if os.path.exists(log_file) else 'не найден'})")
            if os.path.exists(log_file):
                # Проверяем размер файла
                file_size = os.path.getsize(log_file)
                if file_size == 0:
                    continue
                    
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    all_lines = f.readlines()
                    if all_lines:
                        # Берем последние N строк
                        selected_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                        log_content = "".join(selected_lines)
                        if log_content.strip():
                            return f"📋 Логи из файла `{log_file}` (последние {len(selected_lines)} строк из {len(all_lines)}):\n\n```\n{log_content}```"
        except PermissionError:
            checked_files[-1] = f"{log_file} (нет доступа)"
            continue
        except Exception as e:
            checked_files[-1] = f"{log_file} (ошибка: {str(e)[:50]})"
            continue
    
    # Если ничего не сработало - возвращаем инструкцию с информацией о проверенных файлах
    debug_info = "\n".join([f"• {f}" for f in checked_files])
    return (
        "⚠️ Не удалось получить логи автоматически.\n\n"
        f"**Проверенные файлы:**\n{debug_info}\n\n"
        "**Возможные причины:**\n"
        "• Файл логов еще не создан (бот только что запущен)\n"
        "• Файл пустой (логи еще не записаны)\n"
        "• Нет прав доступа к файлу\n\n"
        "**Для просмотра логов используйте на сервере:**\n"
        "```bash\n"
        "docker compose logs -f bot --tail=200\n"
        "```\n\n"
        "Или для последних 100 строк:\n"
        "```bash\n"
        "docker compose logs bot --tail=100\n"
        "```\n\n"
        "**Примечание:** После перезапуска бота логи начнут записываться в `/app/data/bot.log`"
    )


@router.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    
    await _safe_answer(callback, "Получаю логи...", show_alert=False)
    
    logs = await asyncio.to_thread(_get_docker_logs, 200)
    
    # Экранируем HTML-символы для безопасной отправки
    def escape_html(text: str) -> str:
        """Экранирует HTML-символы"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;'))
    
    # Разбиваем на части, если слишком длинные (Telegram ограничение ~4096 символов)
    max_length = 3500  # Оставляем запас для заголовков и экранирования
    if len(logs) > max_length:
        logs_parts = []
        current_part = ""
        for line in logs.split('\n'):
            if len(current_part) + len(line) + 1 > max_length:
                if current_part:
                    logs_parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'
        if current_part:
            logs_parts.append(current_part)
        
        # Отправляем первую часть (с экранированием HTML)
        header = f"📋 Последние логи сервера (часть 1/{len(logs_parts)}):"
        escaped_logs = escape_html(logs_parts[0][:max_length])
        try:
            await callback.message.answer(
                f"{header}\n\n<pre>{escaped_logs}</pre>",
                parse_mode="HTML"
            )
        except Exception as e:
            # Если HTML не работает, отправляем без форматирования
            logger.warning(f"Ошибка отправки логов с HTML: {e}")
            await callback.message.answer(
                f"{header}\n\n{logs_parts[0][:max_length]}"
            )
        
        # Отправляем остальные части
        for i, part in enumerate(logs_parts[1:], 2):
            escaped_part = escape_html(part[:max_length])
            try:
                await callback.message.answer(
                    f"📋 Логи (часть {i}/{len(logs_parts)}):\n\n<pre>{escaped_part}</pre>",
                    parse_mode="HTML"
                )
            except Exception:
                await callback.message.answer(
                    f"📋 Логи (часть {i}/{len(logs_parts)}):\n\n{part[:max_length]}"
                )
    else:
        # Если логи уже содержат заголовок (из файла), отправляем как есть
        if logs.startswith("📋"):
            # Разделяем заголовок и содержимое
            if "\n\n" in logs:
                header_part, content_part = logs.split("\n\n", 1)
                escaped_content = escape_html(content_part)
                try:
                    await callback.message.answer(
                        f"{header_part}\n\n<pre>{escaped_content}</pre>",
                        parse_mode="HTML"
                    )
                except Exception:
                    await callback.message.answer(logs)
            else:
                await callback.message.answer(logs)
        else:
            escaped_logs = escape_html(logs)
            try:
                await callback.message.answer(
                    f"📋 Последние логи сервера:\n\n<pre>{escaped_logs}</pre>",
                    parse_mode="HTML"
                )
            except Exception:
                await callback.message.answer(
                    f"📋 Последние логи сервера:\n\n{logs}"
                )
    
    await callback.message.answer("🛠 Админ-панель", reply_markup=admin_main_keyboard())


def _check_proxy_status(settings: Settings) -> dict:
    """Проверяет состояние прокси"""
    proxy_config = settings.proxy
    result = {
        "configured": False,
        "url": None,
        "status": "Не настроен",
        "test_url": "https://www.google.com",
        "test_result": None,
        "error": None
    }
    
    if not proxy_config.host or not proxy_config.port:
        return result
    
    result["configured"] = True
    result["url"] = proxy_config.as_url()
    
    # Формируем прокси для requests
    proxies = {}
    if proxy_config.scheme:
        proxy_url = proxy_config.as_url()
        if proxy_config.scheme in ("http", "https"):
            proxies["http"] = proxy_url
            proxies["https"] = proxy_url
        elif proxy_config.scheme in ("socks5", "socks5h"):
            proxies["http"] = proxy_url
            proxies["https"] = proxy_url
    
    # Проверяем переменные окружения
    env_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if env_proxy:
        result["env_proxy"] = env_proxy
    
    # Делаем тестовый запрос
    try:
        response = requests.get(
            result["test_url"],
            proxies=proxies if proxies else None,
            timeout=10
        )
        result["status"] = "✅ Работает"
        result["test_result"] = f"HTTP {response.status_code}"
    except requests.exceptions.ProxyError as e:
        result["status"] = "❌ Ошибка прокси"
        error_msg = str(e)
        # Упрощаем сообщение об ошибке
        if "Unable to connect to proxy" in error_msg:
            result["error"] = "Не удалось подключиться к прокси-серверу"
        elif "ReadTimeoutError" in error_msg:
            result["error"] = "Таймаут при подключении к прокси"
        elif "Connection refused" in error_msg:
            result["error"] = "Прокси-сервер отклонил подключение"
        else:
            result["error"] = error_msg[:150]
    except requests.exceptions.Timeout:
        result["status"] = "⏱ Таймаут"
        result["error"] = "Запрос превысил время ожидания (10 сек)"
    except requests.exceptions.ConnectionError as e:
        result["status"] = "❌ Ошибка подключения"
        error_msg = str(e)
        if "Max retries exceeded" in error_msg:
            result["error"] = "Превышено максимальное количество попыток подключения"
        else:
            result["error"] = error_msg[:150]
    except requests.exceptions.RequestException as e:
        result["status"] = "❌ Ошибка запроса"
        result["error"] = str(e)[:150]
    except Exception as e:
        result["status"] = "❌ Неизвестная ошибка"
        result["error"] = str(e)[:150]
    
    return result


@router.callback_query(F.data == "admin_proxy_status")
async def admin_proxy_status(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    
    await _safe_answer(callback, "Проверяю прокси...", show_alert=False)
    
    proxy_status = await asyncio.to_thread(_check_proxy_status, settings)
    
    status_text = "🌐 **Состояние прокси:**\n\n"
    
    if proxy_status["configured"]:
        status_text += f"**Настроен:** ✅\n"
        if proxy_status['url']:
            # Маскируем пароль в URL для безопасности
            url = proxy_status['url']
            if '@' in url:
                parts = url.split('@')
                if len(parts) == 2:
                    auth_part = parts[0]
                    if ':' in auth_part:
                        user_pass = auth_part.split('://', 1)[-1]
                        if ':' in user_pass:
                            user, _ = user_pass.split(':', 1)
                            scheme = url.split('://')[0]
                            masked_url = f"{scheme}://{user}:***@{parts[1]}"
                            status_text += f"**URL:** `{masked_url}`\n"
                        else:
                            status_text += f"**URL:** `{url}`\n"
                    else:
                        status_text += f"**URL:** `{url}`\n"
                else:
                    status_text += f"**URL:** `{url}`\n"
            else:
                status_text += f"**URL:** `{url}`\n"
        if proxy_status.get("env_proxy"):
            env_proxy = proxy_status['env_proxy']
            if '@' in env_proxy:
                parts = env_proxy.split('@')
                if len(parts) == 2 and ':' in parts[0]:
                    user_pass = parts[0].split('://', 1)[-1]
                    if ':' in user_pass:
                        user, _ = user_pass.split(':', 1)
                        scheme = env_proxy.split('://')[0]
                        masked_env = f"{scheme}://{user}:***@{parts[1]}"
                        status_text += f"**Переменная окружения:** `{masked_env}`\n"
                    else:
                        status_text += f"**Переменная окружения:** `{env_proxy}`\n"
                else:
                    status_text += f"**Переменная окружения:** `{env_proxy}`\n"
            else:
                status_text += f"**Переменная окружения:** `{env_proxy}`\n"
        status_text += f"\n**Статус:** {proxy_status['status']}\n"
        if proxy_status.get("test_result"):
            status_text += f"**Тестовый запрос:** {proxy_status['test_result']}\n"
        if proxy_status.get("error"):
            status_text += f"\n**Ошибка:**\n`{proxy_status['error']}`\n"
    else:
        status_text += "**Настроен:** ❌\n"
        status_text += "Прокси не настроен в конфигурации.\n"
    
    await callback.message.answer(status_text, parse_mode="Markdown")
    await callback.message.answer("🛠 Админ-панель", reply_markup=admin_main_keyboard())


@router.callback_query(F.data == "admin_models_browse")
async def admin_models_browse(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await callback.message.edit_text("Выберите категорию", reply_markup=admin_models_category_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_cat:"))
async def admin_models_pick_category(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    category = callback.data.split(":", 1)[1]
    await callback.message.edit_text("Выберите тип одежды", reply_markup=admin_models_cloth_keyboard(category))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_cloth:"))
async def admin_models_pick_cloth(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    _, category, cloth = callback.data.split(":", 2)
    # Для whitebg — только промт; storefront теперь поддерживает модели
    if category == "whitebg":
        await callback.message.edit_text("Для этой категории добавьте только промт.")
    else:
        await callback.message.edit_text("Действия", reply_markup=admin_models_actions_keyboard(category, cloth))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_model_list:"))
async def admin_model_list(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    _, category, cloth, page_str = callback.data.split(":", 3)
    page = int(page_str)
    limit = 8
    offset = page * limit
    models = await db.list_models_page(category, cloth, offset, limit + 1)
    has_next = len(models) > limit
    models = models[:limit]
    items: list[tuple[int, str, str]] = []
    for mid, name, prompt_id, _pos in models:
        title = await db.get_prompt_title(prompt_id)
        items.append((mid, name, title))
    await callback.message.edit_text("Список моделей", reply_markup=admin_model_list_keyboard(category, cloth, items, page, has_next))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_models_actions:"))
async def admin_models_actions(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    _, category, cloth = callback.data.split(":", 2)
    await callback.message.edit_text("Действия", reply_markup=admin_models_actions_keyboard(category, cloth))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_model_edit:"))
async def admin_model_edit(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    model_id = int(callback.data.split(":", 1)[1])
    await callback.message.edit_text(f"Модель #{model_id}", reply_markup=admin_model_edit_keyboard(model_id))
    await _safe_answer(callback)


class ModelCreate(StatesGroup):
    waiting_photo = State()
    waiting_prompt = State()
    waiting_name = State()
    category: str
    cloth: str


@router.callback_query(F.data.startswith("admin_model_add:"))
async def admin_model_add(callback: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    _, category, cloth = callback.data.split(":", 2)
    await state.clear()
    await state.update_data(category=category, cloth=cloth)
    await state.set_state(ModelCreate.waiting_photo)
    await callback.message.edit_text("Пришлите фото модели (изображение сообщением)")
    await _safe_answer(callback)


@router.message(ModelCreate.waiting_photo)
async def admin_model_add_photo(message: Message, state: FSMContext, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    if not message.photo:
        await message.answer("Нужно отправить фото")
        return
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    await state.set_state(ModelCreate.waiting_prompt)
    await message.answer("Пришлите промт для этой модели (текстом)")


@router.message(ModelCreate.waiting_prompt)
async def admin_model_add_prompt_text(message: Message, state: FSMContext, settings: Settings, bot: Bot) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    prompt_text: str | None = None
    # Поддержка .txt документа
    if message.document:
        doc = message.document
        filename = (doc.file_name or "").lower()
        mime = (doc.mime_type or "").lower()
        if filename.endswith(".txt") or mime == "text/plain":
            buf = BytesIO()
            try:
                await bot.download(doc, destination=buf)
                content = buf.getvalue().decode("utf-8", errors="ignore").strip()
                if content:
                    prompt_text = content
            except Exception:
                pass
        if prompt_text is None:
            await message.answer("Пришлите .txt файл с промптом (text/plain) или текстовым сообщением.")
            return
    else:
        # Текстовое сообщение
        if not message.text or not message.text.strip():
            await message.answer("Промт не может быть пустым. Отправьте текст промта или .txt файл.")
            return
        prompt_text = message.text.strip()
    await state.update_data(prompt_text=prompt_text)
    await state.set_state(ModelCreate.waiting_name)
    await message.answer("Укажите название модели (например: Model 1)")


@router.message(ModelCreate.waiting_name)
async def admin_model_add_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    data = await state.get_data()
    category = data.get("category")
    cloth = data.get("cloth")
    name = message.text.strip() or "Model"
    prompt_title = name
    # Защита от пустого промта: если отсутствует — попросить ввести
    prompt_text = (data.get("prompt_text") or "").strip()
    if not prompt_text:
        await state.set_state(ModelCreate.waiting_prompt)
        await message.answer("Для модели не указан промт. Отправьте текст промта.")
        return
    prompt_id = await db.add_prompt(prompt_title, prompt_text)
    model_id = await db.add_model(category, cloth, name=name, prompt_id=prompt_id)
    if data.get("photo_file_id"):
        await db.set_model_photo(model_id, data["photo_file_id"])
    await state.clear()
    await message.answer(
        f"Создана модель #{model_id}",
        reply_markup=admin_model_created_keyboard(category, cloth),
    )


# Prompt create flow


class PromptCreate(StatesGroup):
    waiting_title = State()
    waiting_text = State()


class ModelRename(StatesGroup):
    waiting_name = State()

class RebindState(StatesGroup):
    running = State()


class BroadcastState(StatesGroup):
    waiting_message = State()
    waiting_media = State()
    confirming = State()

# Own prompts editor
class OwnPromptState(StatesGroup):
    waiting_text = State()
    key = State()

@router.callback_query(F.data == "admin_own_prompts")
async def admin_own_prompts_root(callback: CallbackQuery, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, "Промты «Пробовать своё» — выберите шаг:", reply_markup=admin_own_prompts_keyboard())
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("admin_own_prompt_edit:"))
async def admin_own_prompt_edit_start(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    _, idx = callback.data.split(":", 1)
    idx = idx.strip()
    if idx not in ("1", "2", "3"):
        await _safe_answer(callback)
        return
    await state.set_state(OwnPromptState.waiting_text)
    await state.update_data(own_prompt_idx=idx)
    names = {"1":"Шаг 1 — Описание модели","2":"Шаг 2 — (не используется)","3":"Шаг 3 — Финальная генерация"}
    await _replace_with_text(callback, f"{names[idx]}: отправьте текст промта (или .txt)")
    await _safe_answer(callback)

@router.message(OwnPromptState.waiting_text)
async def admin_own_prompt_edit_save(message: Message, state: FSMContext, settings: Settings, db: Database, bot: Bot) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    data = await state.get_data()
    price_category = data.get("price_category")
    
    # Если это редактирование цены категории
    if price_category:
        try:
            price_text = (message.text or "").strip()
            if not price_text:
                await message.answer("Цена пуста. Отправьте число или число с точкой.")
                return
            # Парсим цену (может быть "1", "1.2", "2.0" и т.д.)
            price_float = float(price_text)
            if price_float <= 0:
                await message.answer("Цена должна быть больше нуля.")
                return
            # Конвертируем в десятые доли токена
            price_tenths = int(price_float * 10)
            await db.set_category_price(price_category, price_tenths)
            await state.clear()
            prices = await db.list_category_prices()
            await message.answer("✅ Цена сохранена", reply_markup=admin_category_prices_keyboard(prices))
            return
        except ValueError:
            await message.answer("Неверный формат цены. Отправьте число или число с точкой (например: 1, 1.2, 2.0).")
            return
    
    # Остальная логика для промптов
    idx = (data.get("own_prompt_idx") or "").strip()
    prompt_type = data.get("prompt_type")
    new_text: str | None = None
    if message.document:
        doc = message.document
        filename = (doc.file_name or "").lower()
        mime = (doc.mime_type or "").lower()
        if filename.endswith(".txt") or mime == "text/plain":
            from io import BytesIO
            buf = BytesIO()
            try:
                await bot.download(doc, destination=buf)
                content = buf.getvalue().decode("utf-8", errors="ignore").strip()
                if content:
                    new_text = content
            except Exception:
                pass
        if new_text is None:
            await message.answer("Пришлите .txt файл (text/plain) или текстом.")
            return
    else:
        if message.text and message.text.strip():
            new_text = message.text.strip()
        else:
            await message.answer("Текст пуст. Пришлите текст.")
            return
    if prompt_type == "own_variant":
        await db.set_own_variant_prompt(new_text)
        await state.clear()
        await message.answer("✅ Сохранено", reply_markup=admin_own_variant_prompts_keyboard())
    elif idx == "1":
        await db.set_own_prompt1(new_text)
        await state.clear()
        await message.answer("✅ Сохранено", reply_markup=admin_own_prompts_keyboard())
    elif idx == "2":
        await db.set_own_prompt2(new_text)
        await state.clear()
        await message.answer("✅ Сохранено", reply_markup=admin_own_prompts_keyboard())
    else:
        await db.set_own_prompt3(new_text)
        await state.clear()
        await message.answer("✅ Сохранено", reply_markup=admin_own_prompts_keyboard())


class ModelSetPhoto(StatesGroup):
    waiting_photo = State()


@router.callback_query(F.data == "admin_prompt_add")
async def on_prompt_add(callback: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await state.clear()
    await state.set_state(PromptCreate.waiting_title)
    await callback.message.edit_text("Введите название промта (сообщением).")
    await _safe_answer(callback)


@router.message(PromptCreate.waiting_title)
async def on_prompt_title(message: Message, state: FSMContext, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(PromptCreate.waiting_text)
    await message.answer("Отправьте текст промта.")


@router.message(PromptCreate.waiting_text)
async def on_prompt_text(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    data = await state.get_data()
    title = str(data.get("title", "Prompt"))
    text = message.text
    pid = await db.add_prompt(title, text)
    await state.clear()
    await message.answer(f"Промт создан #{pid}")


@router.callback_query(F.data.startswith("admin_model_rename:"))
async def admin_model_rename_start(callback: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer()
        return
    model_id = int(callback.data.split(":", 1)[1])
    await state.set_state(ModelRename.waiting_name)
    await state.update_data(model_id=model_id)
    await callback.message.edit_text("Введите новое имя модели сообщением")
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_model_setphoto:"))
async def admin_model_setphoto_start(callback: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    model_id = int(callback.data.split(":", 1)[1])
    await state.set_state(ModelSetPhoto.waiting_photo)
    await state.update_data(model_id=model_id)
    await _replace_with_text(callback, "Пришлите новое фото модели (изображением в сообщении)")
    await _safe_answer(callback)


@router.message(ModelSetPhoto.waiting_photo)
async def admin_model_setphoto_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    if not message.photo:
        await message.answer("Нужно отправить фото")
        return
    data = await state.get_data()
    model_id = int(data.get("model_id"))
    file_id = message.photo[-1].file_id
    await db.set_model_photo(model_id, file_id)
    await state.clear()
    await message.answer(
        f"Фото обновлено для модели #{model_id}")


@router.message(ModelRename.waiting_name)
async def admin_model_rename_finish(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    data = await state.get_data()
    model_id = int(data.get("model_id"))
    name = message.text.strip()[:100]
    await db.rename_model(model_id, name)
    await state.clear()
    await message.answer("Имя обновлено")


@router.callback_query(F.data.startswith("admin_model_prompt:"))
async def admin_model_prompt(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    _, model_id_str, page_str = callback.data.split(":", 2)
    model_id = int(model_id_str)
    page = int(page_str)
    limit = 8
    offset = page * limit
    prompts = await db.list_prompts_page(offset, limit + 1)
    has_next = len(prompts) > limit
    prompts = prompts[:limit]
    await callback.message.edit_text("Выберите промт", reply_markup=admin_prompt_pick_keyboard(model_id, prompts, page, has_next))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_model_setprompt:"))
async def admin_model_setprompt(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    _, model_id_str, prompt_id_str = callback.data.split(":", 2)
    await db.set_model_prompt(int(model_id_str), int(prompt_id_str))
    try:
        await callback.message.edit_text(f"Модель #{int(model_id_str)}", reply_markup=admin_model_edit_keyboard(int(model_id_str)))
    except TelegramBadRequest:
        pass
    await _safe_answer(callback, "Промт сохранен", show_alert=False)


@router.callback_query(F.data.startswith("admin_model_delete:"))
async def admin_model_delete(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    model_id = int(callback.data.split(":", 1)[1])
    await db.delete_model(model_id)
    try:
        await callback.message.edit_text("Удалено. Вернитесь к списку.", reply_markup=admin_models_keyboard())
    except TelegramBadRequest:
        pass
    await _safe_answer(callback, "Удалено", show_alert=False)


@router.message(Command("rebind_photos"))
async def cmd_rebind_photos(message: Message, db: Database, settings: Settings, bot: Bot, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    if not settings.old_bot_token:
        await message.answer("OLD_BOT_TOKEN не задан в .env")
        return
    await message.answer("Запускаю перепривязку фото моделей... Это может занять время.")

    # Временный бот со старым токеном, чтобы скачать файлы по старым file_id
    from aiogram import Bot as AioBot
    old_bot = AioBot(token=settings.old_bot_token)
    updated = 0
    failed = 0
    models = await db.list_all_models_with_photo()
    for model_id, file_id in models:
        if not file_id:
            continue
        try:
            # 1) если file_id уже валиден для текущего бота — пропускаем
            try:
                await bot.get_file(file_id)
                continue
            except Exception:
                pass

            # 2) иначе пробуем скачать через старый бот и перезалить
            f = await old_bot.get_file(file_id)
            b = await old_bot.download_file(f.file_path)
            content = b.read()
            from aiogram.types import BufferedInputFile
            new_photo = BufferedInputFile(content, filename=f"model_{model_id}.jpg")
            sent = await bot.send_photo(chat_id=message.chat.id, photo=new_photo)
            new_id = sent.photo[-1].file_id
            await db.set_model_photo(model_id, new_id)
            updated += 1
            await asyncio.sleep(0.1)
        except Exception:
            failed += 1
            continue
    await old_bot.session.close()
    await message.answer(f"Готово. Обновлено: {updated}, ошибок: {failed}.")


@router.message(Command("all"))
async def cmd_broadcast(message: Message, db: Database, settings: Settings, bot: Bot, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    # 1) Если команда отправлена ответом на сообщение — рассылаем это сообщение
    if message.reply_to_message:
        await _broadcast_forward(bot, db, message.reply_to_message)
        await message.answer("Рассылка завершена")
        return
    # 2) Мастер-режим: просим прислать текст (или переданный аргумент)
    await state.set_state(BroadcastState.waiting_message)
    preset = ""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        preset = parts[1].strip()
        await state.update_data(bc_text=preset)
        await state.set_state(BroadcastState.waiting_media)
        await message.answer("Текст принят. Прикрепите изображение (фото), видео или нажмите 'Пропустить'.", reply_markup=broadcast_skip_keyboard())
    else:
        await message.answer("Пришлите текст для рассылки (сообщением). Потом можно будет добавить картинку или пропустить.")


@router.message(BroadcastState.waiting_message)
async def cmd_broadcast_text(message: Message, db: Database, settings: Settings, bot: Bot, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст пуст. Пришлите текст.")
        return
    await state.update_data(bc_text=text)
    await state.set_state(BroadcastState.waiting_media)
    await message.answer("Текст принят. Прикрепите изображение (фото), видео или нажмите 'Пропустить'.", reply_markup=broadcast_skip_keyboard())

@router.message(BroadcastState.waiting_media)
async def cmd_broadcast_media(message: Message, state: FSMContext, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    data = await state.get_data()
    text = data.get("bc_text") or ""
    
    # Поддерживаем фото и видео
    if message.photo:
        file_id = message.photo[-1].file_id
        await state.update_data(bc_photo=file_id, bc_video=None)
        await state.set_state(BroadcastState.confirming)
        await message.answer_photo(photo=file_id, caption=f"Предпросмотр рассылки:\n\n{text}", reply_markup=broadcast_confirm_keyboard())
    elif message.video:
        file_id = message.video.file_id
        await state.update_data(bc_video=file_id, bc_photo=None)
        await state.set_state(BroadcastState.confirming)
        await message.answer_video(video=file_id, caption=f"Предпросмотр рассылки:\n\n{text}", reply_markup=broadcast_confirm_keyboard())
    else:
        await message.answer("Пришлите изображение (фото), видео или нажмите 'Пропустить' ниже.")

@router.callback_query(F.data == "broadcast_skip")
async def on_broadcast_skip(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    data = await state.get_data()
    text = data.get("bc_text") or ""
    await state.set_state(BroadcastState.confirming)
    await _replace_with_text(callback, f"Предпросмотр рассылки:\n\n{text}", reply_markup=broadcast_confirm_keyboard())
    await _safe_answer(callback)

@router.callback_query(F.data == "broadcast_cancel")
async def on_broadcast_cancel(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await state.clear()
    await _replace_with_text(callback, "Отменено.")
    await _safe_answer(callback)

@router.callback_query(F.data == "broadcast_send")
async def on_broadcast_send(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    data = await state.get_data()
    text = data.get("bc_text") or ""
    photo = data.get("bc_photo")
    video = data.get("bc_video")
    await state.clear()
    try:
        await _broadcast_send(bot, db, text, photo, video)
        await _replace_with_text(callback, "✅ Рассылка отправлена")
    except Exception as e:
        await _replace_with_text(callback, f"❌ Ошибка отправки: {e}")
    await _safe_answer(callback)


async def _broadcast_text(bot: Bot, db: Database, text: str) -> None:
    user_ids = await db.list_all_user_ids()
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=text)
            await asyncio.sleep(0.03)
        except Exception:
            continue

async def _broadcast_send(bot: Bot, db: Database, text: str, photo_file_id: Optional[str], video_file_id: Optional[str]) -> None:
    user_ids = await db.list_all_user_ids()
    for uid in user_ids:
        try:
            if video_file_id:
                await bot.send_video(chat_id=uid, video=video_file_id, caption=text or "")
            elif photo_file_id:
                await bot.send_photo(chat_id=uid, photo=photo_file_id, caption=text or "")
            else:
                await bot.send_message(chat_id=uid, text=text or "")
            await asyncio.sleep(0.03)
        except Exception:
            continue

async def _broadcast_forward(bot: Bot, db: Database, src_msg: Message) -> None:
    user_ids = await db.list_all_user_ids()
    for uid in user_ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=src_msg.chat.id, message_id=src_msg.message_id)
            await asyncio.sleep(0.03)
        except Exception:
            continue


@router.callback_query(F.data.startswith("admin_user:"))
async def admin_choose_user(callback: CallbackQuery, settings: Settings, db: Database) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    try:
        user_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await _safe_answer(callback, "Неверный пользователь", show_alert=True)
        return
    balance = await db.get_user_balance(user_id)
    blocked = await db.get_user_blocked(user_id)
    state_txt = "⛔ Заблокирован" if blocked else "✅ Активен"
    text = f"👤 Пользователь {user_id}\nСтатус: {state_txt}\nТекущий баланс: {balance}"
    try:
        await callback.message.edit_text(text, reply_markup=admin_user_actions_keyboard(user_id))
    except TelegramBadRequest:
        pass
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_user_history:"))
async def admin_user_history(callback: CallbackQuery, settings: Settings, db: Database) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    try:
        parts = callback.data.split(":")
        user_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
    except Exception:
        await _safe_answer(callback, "Неверный формат", show_alert=True)
        return
    
    PAGE_SIZE = 10
    offset = page * PAGE_SIZE
    transactions = await db.list_user_transactions(user_id, offset=offset, limit=PAGE_SIZE + 1)
    has_next = len(transactions) > PAGE_SIZE
    transactions_page = transactions[:PAGE_SIZE]
    
    if not transactions_page:
        text = f"📜 История транзакций пользователя {user_id}\n\nИстория пуста."
        try:
            await callback.message.edit_text(text, reply_markup=admin_user_history_keyboard(user_id, page, has_next))
        except TelegramBadRequest:
            pass
        await _safe_answer(callback)
        return
    
    lines = [f"📜 История транзакций пользователя {user_id}:\n"]
    for tx_id, amount, tx_type, reason, created_at in transactions_page:
        sign = "+" if amount > 0 else ""
        type_emoji = {
            "adjust": "⚙️",
            "generation": "🎨",
            "refund": "↩️",
            "bonus": "🎁",
        }.get(tx_type, "📝")
        reason_text = f" ({reason})" if reason else ""
        lines.append(f"{type_emoji} {sign}{amount} токенов{reason_text}\n{created_at}")
    
    text = "\n\n".join(lines)
    try:
        await callback.message.edit_text(text, reply_markup=admin_user_history_keyboard(user_id, page, has_next))
    except TelegramBadRequest:
        pass
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("admin_add:"))
async def admin_add_balance(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    try:
        _, uid_str, amount_str = callback.data.split(":", 2)
        user_id = int(uid_str)
        amount = int(amount_str)
    except Exception:
        await _safe_answer(callback, "Неверный формат", show_alert=True)
        return
    # Гарантируем, что пользователь существует в БД, чтобы UPDATE сработал
    await db.upsert_user(user_id=user_id, username=None, first_name=None, last_name=None)
    await db.increment_user_balance(user_id, amount)
    balance = await db.get_user_balance(user_id)
    text = f"👤 Пользователь {user_id}\nТекущий баланс: {balance}"
    try:
        await callback.message.edit_text(text, reply_markup=admin_user_actions_keyboard(user_id))
    except TelegramBadRequest:
        pass
    await _safe_answer(callback, "Изменено", show_alert=False)


@router.callback_query(F.data.startswith("admin_block:"))
async def admin_block_user(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    try:
        _, uid_str, flag_str = callback.data.split(":", 2)
        user_id = int(uid_str)
        blocked = (flag_str == "1")
    except Exception:
        await _safe_answer(callback, "Неверный формат", show_alert=True)
        return
    await db.upsert_user(user_id=user_id, username=None, first_name=None, last_name=None)
    await db.set_user_blocked(user_id, blocked)
    balance = await db.get_user_balance(user_id)
    state_txt = "⛔ Заблокирован" if blocked else "✅ Активен"
    text = f"👤 Пользователь {user_id}\nСтатус: {state_txt}\nТекущий баланс: {balance}"
    try:
        await callback.message.edit_text(text, reply_markup=admin_user_actions_keyboard(user_id))
    except TelegramBadRequest:
        pass
    await _safe_answer(callback, "Статус обновлён", show_alert=False)


class ApiKeyAddState(StatesGroup):
    waiting_token = State()
    waiting_priority = State()


class ApiKeyEditState(StatesGroup):
    waiting_token = State()
    waiting_priority = State()
    key_id = State()


@router.callback_query(F.data == "admin_api_keys")
async def admin_api_keys(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    keys = await db.list_api_keys()
    await callback.message.edit_text("🔑 Ключи Gemini:", reply_markup=admin_api_keys_keyboard(keys))
    await _safe_answer(callback)


@router.callback_query(F.data == "api_key_add")
async def admin_api_key_add_start(callback: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await state.set_state(ApiKeyAddState.waiting_token)
    await _replace_with_text(callback, "Отправьте новый GEMINI_API_KEY (строкой). Затем укажите приоритет (целое) или /skip")
    await _safe_answer(callback)


@router.message(ApiKeyAddState.waiting_token)
async def admin_api_key_add_token(message: Message, state: FSMContext, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    token = (message.text or "").strip()
    if not token:
        await message.answer("Ключ пуст. Пришлите строку с ключом")
        return
    await state.update_data(token=token)
    await state.set_state(ApiKeyAddState.waiting_priority)
    await message.answer("Укажите приоритет (целое, больше — выше приоритет) или отправьте /skip")


@router.message(ApiKeyAddState.waiting_priority)
async def admin_api_key_add_priority(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    data = await state.get_data()
    token = data.get("token")
    pr_text = (message.text or "").strip()
    priority = 0
    if pr_text and pr_text != "/skip":
        try:
            priority = int(pr_text)
        except Exception:
            await message.answer("Неверный приоритет. Введите целое число или /skip")
            return
    is_own_variant = data.get("own_variant", False)
    if is_own_variant:
        await db.add_own_variant_api_key(token, priority)
        await state.clear()
        keys = await db.list_own_variant_api_keys()
        await message.answer("Ключ добавлен", reply_markup=admin_own_variant_api_keys_keyboard(keys))
    else:
        await db.add_api_key(token, priority)
        await state.clear()
        keys = await db.list_api_keys()
        await message.answer("Ключ добавлен", reply_markup=admin_api_keys_keyboard(keys))


@router.callback_query(F.data.startswith("api_key_toggle:"))
async def admin_api_key_toggle(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    key_id = int(callback.data.split(":", 1)[1])
    keys = await db.list_api_keys()
    status = 1
    for kid, _tok, is_active in keys:
        if kid == key_id:
            status = 0 if is_active else 1
            break
    await db.update_api_key(key_id, is_active=status)
    keys = await db.list_api_keys()
    await callback.message.edit_text("🔑 Ключи Gemini:", reply_markup=admin_api_keys_keyboard(keys))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("api_key_delete:"))
async def admin_api_key_delete(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    key_id = int(callback.data.split(":", 1)[1])
    await db.delete_api_key(key_id)
    keys = await db.list_api_keys()
    await callback.message.edit_text("🔑 Ключи Gemini:", reply_markup=admin_api_keys_keyboard(keys))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("api_key_show:"))
async def admin_api_key_show(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    key_id = int(callback.data.split(":", 1)[1])
    keys = await db.list_api_keys()
    token = None
    state_txt = ""
    for kid, tok, is_active in keys:
        if kid == key_id:
            token = tok
            state_txt = "Активен" if is_active else "Отключен"
            break
    if token is None:
        await _safe_answer(callback, "Ключ не найден", show_alert=True)
        return
    try:
        await callback.answer(f"#{key_id} {state_txt}: {token}", show_alert=True)
    except Exception:
        pass


@router.callback_query(F.data.startswith("api_key_edit:"))
async def admin_api_key_edit_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    key_id = int(callback.data.split(":", 1)[1])
    await state.update_data(edit_key_id=key_id)
    await state.set_state(ApiKeyEditState.waiting_token)
    await _replace_with_text(callback, "Пришлите новый токен (или /skip чтобы оставить старый)")
    await _safe_answer(callback)


@router.message(ApiKeyEditState.waiting_token)
async def admin_api_key_edit_token(message: Message, state: FSMContext, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    txt = (message.text or "").strip()
    if txt != "/skip" and not txt:
        await message.answer("Токен пуст. Пришлите строку или /skip")
        return
    if txt != "/skip":
        await state.update_data(new_token=txt)
    await state.set_state(ApiKeyEditState.waiting_priority)
    await message.answer("Укажите новый приоритет (целое) или /skip")


@router.message(ApiKeyEditState.waiting_priority)
async def admin_api_key_edit_priority(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(message.from_user.id, settings):
        return
    data = await state.get_data()
    key_id = int(data.get("edit_key_id"))
    token = data.get("new_token")
    pr_text = (message.text or "").strip()
    pr_value = None
    if pr_text and pr_text != "/skip":
        try:
            pr_value = int(pr_text)
        except Exception:
            await message.answer("Неверный приоритет. Введите целое или /skip")
            return
    await db.update_api_key(key_id, token=token if token else None, priority=pr_value)
    await state.clear()
    keys = await db.list_api_keys()
    await message.answer("Ключ обновлен", reply_markup=admin_api_keys_keyboard(keys))


# Own Variant API Keys Management
@router.callback_query(F.data == "admin_own_variant_api_keys")
async def admin_own_variant_api_keys(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    keys = await db.list_own_variant_api_keys()
    await callback.message.edit_text("🔑 Ключи 'Свой вариант':", reply_markup=admin_own_variant_api_keys_keyboard(keys))
    await _safe_answer(callback)


@router.callback_query(F.data == "own_variant_api_key_add")
async def admin_own_variant_api_key_add_start(callback: CallbackQuery, settings: Settings, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await state.set_state(ApiKeyAddState.waiting_token)
    await state.update_data(own_variant=True)
    await _replace_with_text(callback, "Отправьте новый GEMINI_API_KEY для 'Свой вариант' (строкой). Затем укажите приоритет (целое) или /skip")
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("own_variant_api_key_toggle:"))
async def admin_own_variant_api_key_toggle(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    key_id = int(callback.data.split(":", 1)[1])
    keys = await db.list_own_variant_api_keys()
    status = 1
    for kid, _tok, is_active in keys:
        if kid == key_id:
            status = 0 if is_active else 1
            break
    await db.update_own_variant_api_key(key_id, is_active=status)
    keys = await db.list_own_variant_api_keys()
    await callback.message.edit_text("🔑 Ключи 'Свой вариант':", reply_markup=admin_own_variant_api_keys_keyboard(keys))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("own_variant_api_key_delete:"))
async def admin_own_variant_api_key_delete(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    key_id = int(callback.data.split(":", 1)[1])
    await db.delete_own_variant_api_key(key_id)
    keys = await db.list_own_variant_api_keys()
    await callback.message.edit_text("🔑 Ключи 'Свой вариант':", reply_markup=admin_own_variant_api_keys_keyboard(keys))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("own_variant_api_key_show:"))
async def admin_own_variant_api_key_show(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    key_id = int(callback.data.split(":", 1)[1])
    keys = await db.list_own_variant_api_keys()
    token = None
    state_txt = ""
    for kid, tok, is_active in keys:
        if kid == key_id:
            token = tok
            state_txt = "Активен" if is_active else "Отключен"
            break
    if token is None:
        await _safe_answer(callback, "Ключ не найден", show_alert=True)
        return
    await _safe_answer(callback, f"Ключ #{key_id}: {token}\nСтатус: {state_txt}", show_alert=True)


# Own Variant Prompt Management
@router.callback_query(F.data == "admin_own_variant_prompts")
async def admin_own_variant_prompts_root(callback: CallbackQuery, settings: Settings, db: Database) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, "Промт «Свой вариант»:", reply_markup=admin_own_variant_prompts_keyboard())
    await _safe_answer(callback)

@router.callback_query(F.data == "admin_own_variant_prompt_view")
async def admin_own_variant_prompt_view(callback: CallbackQuery, settings: Settings, db: Database) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    current = await db.get_own_variant_prompt()
    if current:
        # Разбиваем длинный промт на части, если он слишком длинный для Telegram (4096 символов)
        max_length = 4000
        if len(current) > max_length:
            # Показываем первую часть
            text = f"📋 Текущий промт «Свой вариант»:\n\n{current[:max_length]}...\n\n(промт обрезан, полный промт в базе данных)"
        else:
            text = f"📋 Текущий промт «Свой вариант»:\n\n{current}"
        await _replace_with_text(callback, text, reply_markup=admin_own_variant_prompts_keyboard())
    else:
        await _replace_with_text(callback, "Промт «Свой вариант» не задан.", reply_markup=admin_own_variant_prompts_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "admin_own_variant_prompt_edit")
async def admin_own_variant_prompt_edit_start(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await _safe_answer(callback)
        return
    current = await db.get_own_variant_prompt()
    if current:
        await _replace_with_text(callback, f"Текущий промт:\n\n{current}\n\nОтправьте новый промт (текстом):")
    else:
        await _replace_with_text(callback, "Промт не задан. Отправьте промт (текстом):")
    await state.set_state(OwnPromptState.waiting_text)
    await state.update_data(prompt_type="own_variant")
    await _safe_answer(callback)


