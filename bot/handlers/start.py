from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import BufferedInputFile
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from bot.keyboards import (
    terms_keyboard,
    main_menu_keyboard,
    create_product_keyboard_dynamic,
    ready_presets_keyboard,
    female_clothes_keyboard,
    male_clothes_keyboard,
    boy_clothes_keyboard,
    girl_clothes_keyboard,
    child_gender_keyboard,
    infographic_selection_keyboard,
    back_step_keyboard,
    back_main_keyboard,
    model_select_keyboard,
    garment_length_keyboard,
    form_view_keyboard,
    confirm_generation_keyboard,
    result_actions_keyboard,
    result_actions_own_keyboard,
    pants_style_keyboard,
    aspect_ratio_keyboard,
    form_generate_keyboard,
    sleeve_length_keyboard,
    camera_distance_keyboard,
    random_gender_keyboard,
    random_loc_group_keyboard,
    random_location_keyboard,
    profile_keyboard,
    plans_keyboard,
    settings_keyboard,
    language_keyboard,
    random_vibe_keyboard,
    random_season_keyboard,
    random_decor_keyboard,
    random_shot_keyboard,
    pose_keyboard,
    angle_keyboard,
    plus_location_keyboard,
    plus_season_keyboard,
    plus_vibe_keyboard,
    plus_gender_keyboard,
    info_lang_keyboard,
    skip_step_keyboard,
    infographic_gender_keyboard,
    infographic_style_keyboard,
    yes_no_keyboard,
)
from bot.db import Database
from bot.strings import get_string
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.config import load_settings
from bot.gemini import generate_image, generate_text
import asyncio
import time
from asyncio import Lock
from aiogram.enums import ChatAction

state_lock = Lock()
import logging
import os
import json
import aiosqlite

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Базовый URL для кнопки скачивания оригинала результата.
TELEGRAM_DOWNLOAD_BASE_URL = os.getenv("TELEGRAM_DOWNLOAD_BASE_URL", "http://g-box.space").rstrip("/")
logger = logging.getLogger(__name__)

def _public_url_for(db_path: str) -> str:
    # db_path обычно "data/history/xxx.jpg" -> "http://.../download/history/xxx.jpg"
    p = (db_path or "").replace("\\", "/").lstrip("/")
    if p.startswith("data/"):
        p = p[5:]
    return f"{TELEGRAM_DOWNLOAD_BASE_URL}/download/{p}"

def _telegram_candidate_urls(url: str) -> list[str]:
    """
    Telegram sendPhoto(URL) иногда падает из-за сетевых/ДНС/маршрутизации.
    Пробуем несколько безопасных вариантов (домен/IP, https->http) прежде чем уйти в upload.
    """
    if not url:
        return []

    candidates: list[str] = [url]

    if url.startswith("https://"):
        candidates.append(url.replace("https://", "http://", 1))

    # Иногда домен недоступен из сети Telegram, но IP работает.
    if "g-box.space" in url:
        candidates.append(url.replace("g-box.space", "130.49.148.147"))
        if url.startswith("https://"):
            candidates.append(url.replace("https://", "http://", 1).replace("g-box.space", "130.49.148.147"))

    # дедуп с сохранением порядка
    seen = set()
    uniq: list[str] = []
    for u in candidates:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return uniq


def _result_keyboard_with_download(base_kb: InlineKeyboardMarkup | None, download_url: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="⬇️ Скачать оригинал", url=download_url)]
    ]
    if base_kb and getattr(base_kb, "inline_keyboard", None):
        rows.extend(base_kb.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


#
# NOTE: Результат отправляем как PHOTO (для полноэкранного просмотра),
# а оригинал отдаем отдельной URL-кнопкой "Скачать оригинал".


router = Router()

 
class CreateForm(StatesGroup):
    waiting_age = State()
    waiting_child_gender = State()
    waiting_info_gender = State()
    waiting_size = State()
    waiting_height = State()
    waiting_body_type = State() # Добавлено
    waiting_length = State()
    waiting_view = State()
    waiting_prompt = State()
    waiting_aspect = State()
    waiting_support_message = State()
    waiting_sleeve = State()
    waiting_foot = State()
    waiting_pants_style = State()
    waiting_edit_text = State()
    result_ready = State()
    # Random mode custom steps reuse existing where possible
    random_mode = State()
    random_other_mode = State()
    random_dummy = State()
    waiting_custom_location = State()
    waiting_has_person = State()
    # Own flow
    own_mode = State()
    waiting_ref_photo = State()
    waiting_product_photo = State()
    waiting_own_view = State()
    waiting_own_size = State()
    waiting_own_length = State()
    waiting_own_sleeve = State()
    waiting_own_cut = State()
    plus_loc = State()
    plus_season = State()
    plus_vibe = State()
    waiting_model_search = State()
    category = State()
    cloth = State()
    # Infographic flow
    waiting_info_load = State()
    waiting_info_lang = State()     # Добавлено
    waiting_info_lang_custom = State()
    waiting_info_brand = State()
    waiting_info_adv1 = State()
    waiting_info_adv2 = State()
    waiting_info_adv3 = State()
    waiting_info_extra = State()
    waiting_info_angle = State()
    waiting_info_pose = State()
    waiting_info_age = State()
    waiting_info_holiday = State()
    waiting_info_season = State()
    waiting_info_has_person = State()
    # Presets flow
    waiting_preset_pose = State()
    waiting_preset_dist = State()
    waiting_preset_view = State()
    waiting_preset_season = State()
    waiting_preset_holiday = State()
    # ...
    # Random Other flow
    waiting_rand_other_has_person = State()
    waiting_rand_other_gender = State()
    waiting_rand_other_name = State()
    waiting_rand_other_angle = State()
    waiting_rand_other_dist = State()
    waiting_rand_other_height = State()
    waiting_rand_other_width = State()
    waiting_rand_other_length = State()
    waiting_rand_other_season = State()
    waiting_rand_other_style = State()
    waiting_rand_other_style_custom = State()
    waiting_rand_loc_group = State()
    waiting_rand_gender = State()
    waiting_rand_loc = State()
    waiting_rand_vibe = State()
    waiting_rand_decor = State()
    waiting_rand_shot = State()
    index = State()
    model_id = State()
    prompt_id = State()
    # Own background flow
    waiting_own_bg_photo = State()
    waiting_own_product_photo = State()
    waiting_dynamic_step = State() # Новый статус для динамических шагов

WELCOME_TEXT = (
    "👋 Добро пожаловать в Fashion AI Generator!\n\n"
    "Превращаем фотографии вашей одежды в профессиональные снимки на моделях.\n\n"
    "📋 Перед использованием ознакомьтесь с:\n"
    "1. Условиями использования\n"
    "2. Согласием на обработку данных"
)

## Глобальный guard убран для совместимости с текущей версией aiogram; точечные проверки остаются в хендлерах

async def _safe_answer(callback: CallbackQuery, text: str | None = None, show_alert: bool = False) -> None:
    try:
        if callback.id != "0":
            await callback.answer(text, show_alert=show_alert)
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
    except TelegramRetryAfter:
        # Фолбэк при флуд-контроле TG — отправляем новое сообщение вместо редактирования
        try:
            await callback.message.answer(text, reply_markup=reply_markup)
        except Exception:
            pass


async def _ask_sleeve_length(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(message_or_callback.from_user.id)
    from bot.keyboards import own_sleeve_length_keyboard
    text = get_string("select_sleeve_length", lang)
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=own_sleeve_length_keyboard(lang))
    else:
        await _replace_with_text(message_or_callback, text, reply_markup=own_sleeve_length_keyboard(lang))
    await state.set_state(CreateForm.waiting_own_sleeve)

@router.callback_query(F.data.startswith("own_sleeve:"))
async def on_own_sleeve(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    
    sleeve_map = {
        "normal": "Обычный",
        "long": "Длинные",
        "three_quarter": "Три четверти",
        "elbow": "До локтей",
        "short": "Короткие",
        "none": "Без рукав",
        "skip": "Пропустить",
    }
    sleeve_text = sleeve_map.get(val, "Пропустить")
    await state.update_data(own_sleeve=sleeve_text)
    
    if data.get("own_mode"):
        # Для "Свой вариант модели" после рукавов просим ФОТО ТОВАРА (п. 8.3)
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]])
        await _replace_with_text(callback, get_string("upload_product", lang), reply_markup=back_kb)
        await state.set_state(CreateForm.waiting_own_product_photo)
        await _safe_answer(callback)
        return

    # Далее длина изделия
    await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)

async def _ask_garment_length(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    """Вспомогательная функция для запроса длины изделия"""
    lang = await db.get_user_language(message_or_callback.from_user.id)
    text = get_string("select_garment_length", lang)
    kb = garment_length_keyboard(lang)
    
    await state.set_state(CreateForm.waiting_length)
    
    if isinstance(message_or_callback, CallbackQuery):
        await _replace_with_text(message_or_callback, text, reply_markup=kb)
    else:
        await message_or_callback.answer(text, reply_markup=kb)


async def _run_generation_progress(bot, chat_id: int, message_id: int, stop_event: asyncio.Event) -> None:
    start_time = time.time()
    steps_text = [
        "Изучаю ваш запрос",
        "Обрабатываю детали",
        "Применяю нейронные фильтры",
        "Улучшаю качество",
        "Финализирую"
    ]
    total_steps = 5
    step = 1
    try:
        while not stop_event.is_set() and step <= total_steps:
            for sub in range(4):
                if stop_event.is_set(): break
                elapsed = int(time.time() - start_time)
                progress = int(((step - 1) / total_steps + (sub / 4) / total_steps) * 100)
                if progress > 99: progress = 99
                
                filled = int(progress / 10)
                bar = "🟦" * filled + "⬜️" * (10 - filled)
                
                text = (
                    f"🚀 Генерация\n\n"
                    f"{steps_text[step-1]}\n\n"
                    f"{bar} {progress}%\n\n"
                    f"Прошло: {elapsed}с • Шаг {step}/{total_steps}\n\n"
                    f"Результат вас приятно удивит"
                )
                try:
                    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
                    await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
                except: pass
                await asyncio.sleep(1.5)
            step += 1
    except: pass


async def _answer_model_photo(callback: CallbackQuery, photo: str, caption: str, reply_markup=None) -> Message | None:
    from aiogram.types import InputMediaPhoto, FSInputFile
    import os

    # Определяем медиа-объект
    if photo.startswith("AgAC"): # Telegram file_id
        media = InputMediaPhoto(media=photo, caption=caption)
    else: # Локальный файл
        file_path = photo if os.path.exists(photo) else os.path.join("/app", photo)
        if os.path.exists(file_path):
            media = InputMediaPhoto(media=FSInputFile(file_path), caption=caption)
        else:
            logger.error(f"Файл фото модели не найден: {photo}")
            await _replace_with_text(callback, caption, reply_markup=reply_markup)
            return None

    try:
        # Пытаемся отредактировать текущее медиа (это намного быстрее и нет прыжков)
        return await callback.message.edit_media(media=media, reply_markup=reply_markup)
    except Exception as e:
        # Если не получилось отредактировать (например, сообщение было текстовым),
        # удаляем старое и отправляем новое
        try:
            await callback.message.delete()
        except:
            pass
        
        try:
            if photo.startswith("AgAC"):
                return await callback.message.answer_photo(photo=photo, caption=caption, reply_markup=reply_markup)
            else:
                file_path = photo if os.path.exists(photo) else os.path.join("/app", photo)
                return await callback.message.answer_photo(photo=FSInputFile(file_path), caption=caption, reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Ошибка отправки фото модели: {e2}")
            await callback.message.answer(caption, reply_markup=reply_markup)
            return None


@router.callback_query(F.data.startswith("child_gender:"))
async def on_child_gender_select(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    gender = callback.data.split(":")[1]
    # gender is 'boy' or 'girl'
    await state.clear()
    await state.update_data(child_gender=gender, category="child", cloth=gender, is_preset=True)
    lang = await db.get_user_language(callback.from_user.id)
    
    # Для детей ПРОПУСКАЕМ возраст, сразу к телосложению
    await _replace_with_text(callback, "📏 Введите размер одежды или телосложение числом:", reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_dynamic_step)
    await state.update_data(current_step_key="size")
    await _safe_answer(callback)


async def _check_subscription(user_id: int, bot: Bot, db: Database) -> bool:
    """Проверяет подписку пользователя на обязательный канал"""
    channel_id = await db.get_app_setting("required_channel_id")
    if not channel_id:
        return True 
    try:
        # Пытаемся получить статус участника
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        # Статусы, которые считаются "подписан"
        is_subbed = member.status in ("member", "administrator", "creator")
        logger.info(f"Subscription check for {user_id} in {channel_id}: {member.status} (is_subbed: {is_subbed})")
        return is_subbed
    except Exception as e:
        err_msg = str(e).lower()
        logger.error(f"Error checking subscription for {user_id} in {channel_id}: {e}")
        
        # Если ошибка "chat not found", значит ID канала неверный или бот не в канале
        if "chat not found" in err_msg:
            logger.error(f"CRITICAL: Required channel {channel_id} not found. Check if bot is admin there.")
            return False
        
        # Если ошибка "member not found", значит пользователь точно не подписан
        if "user not found" in err_msg or "member not found" in err_msg:
            return False
            
        # Для остальных ошибок (например, временный сбой) разрешаем, чтобы не блокировать сервис
        return True

async def _show_confirmation(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    """Показывает сводку параметров и кнопку создания фото"""
    data = await state.get_data()
    category_key = data.get("category")
    lang = await db.get_user_language(message_or_callback.from_user.id)
    
    # Получаем название категории из базы
    category = await db.get_category_by_key(category_key)
    cat_name = category[2] if category else category_key
    
    parts = ["📋 Проверьте выбранные параметры:\n\n"]
    parts.append(f"📦 **Раздел**: {cat_name}\n")

    # Получаем все шаги этой категории, чтобы знать их названия
    logic_cat = category_key
    if data.get("is_preset") and category_key in ("female", "male", "child"):
        logic_cat = "presets"
    
    cat_info = await db.get_category_by_key(logic_cat)
    if cat_info:
        steps = await db.list_steps(cat_info[0])
        for step in steps:
            s_id, s_key, s_question, s_type, s_optional, s_order = step
            val = data.get(s_key)
            if val:
                # Если у нас есть сохраненная метка (label) — используем ее
                label = data.get(f"{s_key}_label", val)
                # Не показываем file_id и чувствительные значения
                if s_type == "photo":
                    label = "Фото получено"
                elif isinstance(label, str) and (label.startswith("AgAC") or label.startswith("AQAD")):
                    label = "Фото получено"
                elif isinstance(label, str) and label.startswith("AIza") and len(label) > 20:
                    label = "Скрыто"
                
                # Убираем эмодзи из вопроса для метки, если нужно, 
                # или просто берем часть текста до двоеточия
                clean_question = s_question.split(':')[0].strip()
                parts.append(f"🔹 **{clean_question}**: {label}\n")

    if data.get("normal_gen_mode"):
        parts.append(f"📝 **Промпт**: {data.get('prompt', '—')}\n")

    parts.append(f"\n{get_string('generation_confirm', lang)}")
    
    text = "".join(parts)
    from bot.keyboards import confirm_generation_keyboard
    kb = confirm_generation_keyboard(lang)
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=kb)
    else:
        await _replace_with_text(message_or_callback, text, reply_markup=kb)

async def _show_model_selection(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    """Хелпер для отображения выбора модели (пресета)"""
    import logging
    logger = logging.getLogger(__name__)
    data = await state.get_data()
    # Определяем категорию и тип одежды для выбора моделей
    # Если они не заданы в data, пробуем использовать текущие
    if data.get("is_preset") and data.get("gender"):
        category = data.get("gender")
        cloth = "all"
    else:
        category = data.get("display_category") or data.get("category", "female")
        cloth = data.get("selected_cloth") or data.get("cloth", "all")
    
    total = await db.count_models(category, cloth)
    logger.info("[flow] model_select category=%s cloth=%s total=%s", category, cloth, total)
    if total <= 0:
        # Если нет моделей - пробуем с 'all'
        cloth = "all"
        total = await db.count_models(category, cloth)

    # Для пресетов не используем фолбэк на другие категории,
    # чтобы не показывать модели другого пола

    if total <= 0:
        # Если совсем нет - показываем ошибку и остаемся на шаге
        text = "Извините, в этой категории пока нет доступных моделей."
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(text)
        else:
            await _replace_with_text(message_or_callback, text)
        return

    index = data.get("model_index", 0)
    if index >= total: index = 0
    
    model = await db.get_model_by_index(category, cloth, index)
    lang = await db.get_user_language(message_or_callback.from_user.id)
    
    # helper functions
    from bot.handlers.start import _model_header
    text = _model_header(index, total)
    
    from bot.keyboards import model_select_keyboard
    kb = model_select_keyboard(category, cloth, index, total, lang, logic_category=data.get("category"))
    
    if model and model[3]: # photo_file_id
        if isinstance(message_or_callback, CallbackQuery):
            res_msg = await _answer_model_photo(message_or_callback, model[3], text, kb)
            if res_msg and res_msg.photo and not model[3].startswith("AgAC"):
                await db.set_model_photo(model[0], res_msg.photo[-1].file_id)
        else:
            await message_or_callback.answer_photo(photo=model[3], caption=text, reply_markup=kb)
    else:
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(text, reply_markup=kb)
        else:
            await _replace_with_text(message_or_callback, text, reply_markup=kb)

async def _show_next_step(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    import logging
    logger = logging.getLogger(__name__)
    data = await state.get_data()
    cat_key = data.get("category")
    if not cat_key:
        return
    
    # Если это пресетная категория, но ключ - пол, переключаемся на 'presets' для поиска шагов
    logic_cat = cat_key
    if data.get("is_preset") and cat_key in ("female", "male", "child"):
        logic_cat = "presets"
    
    category = await db.get_category_by_key(logic_cat)
    if not category:
        # Фолбэк на старую логику или ошибку
        return
    
    cat_id = category[0]
    steps = await db.list_steps(cat_id)
    
    # Определяем текущий индекс шага
    current_step_index = data.get("current_step_index", 0)
    
    logger.info("[flow] show_next_step data=%s", {k: v for k, v in data.items() if not k.startswith("_")})
    
    # Проверка на пропуск шагов
    while current_step_index < len(steps):
        step = steps[current_step_index]
        step_id, step_key, question, input_type, is_optional, order = step
        gender = data.get("gender") or data.get("rand_gender") or data.get("info_gender") or data.get("child_gender")
        
        # 1. Пропускаем возраст для детей
        if step_key == "age" and gender in ("boy", "girl"):
            current_step_index += 1
            continue

        # Условие: если присутствие человека = Нет, пропускаем Возраст и Позу
        # Ищем во всех данных любое значение, означающее отсутствие человека
        person_absent = False
        for k, v in data.items():
            # Если это метка кнопки
            if k.endswith("_label"):
                label_v = str(v).lower()
                # Если текст кнопки однозначно говорит об отсутствии человека
                if any(x in label_v for x in ("без человека", "without person", "không có người")):
                    person_absent = True
                    break
                # Если текст "нет" и ключ связан с человеком
                if any(x in label_v for x in ("нет", "no", "không")):
                    low_k = k.lower()
                    if any(x in low_k for x in ("person", "presence", "человек", "присутствие")):
                        person_absent = True
                        break
            
            # Если значение само по себе говорит об отсутствии человека (ID или спец. значение)
            if isinstance(v, str):
                v_low = v.lower()
                if v_low in ("person_no", "without_person", "no_person", "no-person"):
                    person_absent = True
                    break
                # Если значение "нет" и ключ связан с человеком
                if v_low in ("no", "off", "нет"):
                    low_k = k.lower()
                    if any(x in low_k for x in ("person", "presence", "человек", "присутствие")):
                        person_absent = True
                        break
        
        # Проверяем ключи шагов более гибко (по вхождению подстроки)
        low_step_key = step_key.lower()
        # Для Рандом прочее и Инфографика прочее: 'height/рост' может быть параметром товара, а не модели
        if cat_key in ("random_other", "infographic_other"):
            is_skip_target = any(x in low_step_key for x in ("age", "pose", "size", "возраст", "поза", "телосложение"))
        else:
            is_skip_target = any(x in low_step_key for x in ("age", "pose", "height", "size", "возраст", "поза", "рост", "телосложение"))
        
        # Специальное условие для infographic_other и random_other
        # "если нет (человека) то спрашиваем только пол" -> пропускаем возраст, позу, рост, размер
        if cat_key in ["infographic_other", "random_other"] and person_absent:
            if any(x in low_step_key for x in ("age", "возраст", "pose", "поза", "size", "телосложение")):
                logger.info("[flow] SPECIAL SKIP step=%s for %s because person_absent=True", step_key, cat_key)
                current_step_index += 1
                continue

        if person_absent and is_skip_target:
            logger.info("[flow] SKIP step=%s because person_absent=True found in data", step_key)
            current_step_index += 1
            continue
        
        # Условие для локаций в Рандоме
        loc_group = data.get("rand_loc_group")
        if loc_group:
            if loc_group == "indoor" and step_key == "rand_location_outdoor":
                logger.info("[flow] SKIP rand_location_outdoor because loc_group is indoor")
                current_step_index += 1
                continue
            if loc_group == "outdoor" and step_key == "rand_location_indoor":
                logger.info("[flow] SKIP rand_location_indoor because loc_group is outdoor")
                current_step_index += 1
                continue
            
            # Если В ПОМЕЩЕНИИ (indoor), пропускаем выбор сезона (season)
            if loc_group == "indoor" and "season" in step_key.lower():
                logger.info("[flow] SKIP %s because loc_group is indoor", step_key)
                current_step_index += 1
                continue

        if is_skip_target:
            logger.info("[flow] CHECK skip target=%s person_absent=%s", step_key, person_absent)
            
        # 2. Пропускаем шаги, которые уже есть в данных (но только если мы НЕ идем назад)
        is_going_back = data.get("is_going_back", False)
        if step_key in data and data.get(step_key) is not None and not is_going_back:
            current_step_index += 1
            continue
            
        # 3. Проверка на наличие опций для кнопочных шагов
        if input_type == "buttons":
            options = await db.list_step_options(step_id)
            if not options and not is_optional:
                current_step_index += 1
                continue

        # Если шаг не пропущен — выходим из цикла
        break

    # ОБЯЗАТЕЛЬНО сохраняем текущий индекс, чтобы обработчики (on_dynamic_option) знали, где мы
    await state.update_data(current_step_index=current_step_index)
    
    # [FIX] Очищаем флаг возврата, если мы успешно нашли шаг
    await state.update_data(is_going_back=False)

    if current_step_index >= len(steps):
        # Все шаги пройдены — переходим к финалу
        # Но сначала проверим формат (обязателен для всех генераций)
        aspect = data.get("aspect")
        if not aspect:
            await state.set_state(CreateForm.waiting_aspect)
            lang = await db.get_user_language(message_or_callback.from_user.id)
            from bot.keyboards import aspect_ratio_keyboard
            text = get_string("select_format", lang)
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(text, reply_markup=aspect_ratio_keyboard(lang))
            else:
                await _replace_with_text(message_or_callback, text, reply_markup=aspect_ratio_keyboard(lang))
            return

        await _show_confirmation(message_or_callback, state, db)
        return

    # Показываем текущий шаг
    step = steps[current_step_index]
    step_id, step_key, question, input_type, is_optional, order = step
    lang = await db.get_user_language(message_or_callback.from_user.id)
    logger.info("[flow] show_step category=%s step=%s type=%s index=%s", cat_key, step_key, input_type, current_step_index)
    question = await db.get_step_text(step_id, lang)
    
    await state.update_data(current_step_id=step_id, current_step_key=step_key)
    await state.set_state(CreateForm.waiting_dynamic_step)
    
    if input_type == "buttons":
        options = await db.list_step_options_localized(step_id, lang)
        from bot.keyboards import dynamic_keyboard
        
        # [FIX] Если шаг необязательный или это текстовый ввод, добавляем кнопку "Пропустить"
        # Проверяем также по ключам для преимуществ и доп текста
        show_skip = bool(is_optional)
        if any(x in step_key.lower() for x in ("adv_", "extra_info", "brand_name", "info_load", "преимущество", "доп_инфо", "доп_текст", "название", "бренд", "product_name")):
            show_skip = True
            
        kb = dynamic_keyboard(options, show_skip, lang)
        
        # Для длины изделия просто отправляем текст с кнопками (без фото)
        if step_key == "length":
            if isinstance(message_or_callback, CallbackQuery):
                await _replace_with_text(message_or_callback, question, reply_markup=kb)
            else:
                await message_or_callback.answer(question, reply_markup=kb)
            return

        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(question, reply_markup=kb)
        else:
            await _replace_with_text(message_or_callback, question, reply_markup=kb)
            
    elif input_type == "photo":
        kb = back_step_keyboard(lang)
        show_skip = bool(is_optional)
        if any(x in step_key.lower() for x in ("adv_", "extra_info", "brand_name", "info_load", "преимущество", "доп_инфо", "доп_текст", "название", "бренд", "product_name")):
            show_skip = True
            
        if show_skip:
            from bot.keyboards import skip_step_keyboard
            kb = skip_step_keyboard("dyn_opt", lang)
            
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(question, reply_markup=kb)
        else:
            await _replace_with_text(message_or_callback, question, reply_markup=kb)
            
    elif input_type == "model_select":
        # Логика выбора модели
        # Мы предполагаем, что _show_model_selection уже существует в start.py
        # Если нет, нужно убедиться что она вызывается правильно
        try:
            # Пытаемся вызвать внутреннюю функцию выбора модели
            await _show_model_selection(message_or_callback, state, db)
        except Exception as e:
            logger.exception("Error in model_select step")
            err_text = "⚠️ Ошибка при показе выбора модели. Попробуйте ещё раз."
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(err_text)
            else:
                await _replace_with_text(message_or_callback, err_text)
            return
        
    else: # text
        kb = back_step_keyboard(lang)
        show_skip = bool(is_optional)
        if any(x in step_key.lower() for x in ("adv_", "extra_info", "brand_name", "info_load", "преимущество", "доп_инфо", "доп_текст", "название", "бренд", "product_name")):
            show_skip = True
            
        if show_skip:
            from bot.keyboards import skip_step_keyboard
            kb = skip_step_keyboard("dyn_opt", lang)
            
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(question, reply_markup=kb)
        else:
            await _replace_with_text(message_or_callback, question, reply_markup=kb)

@router.callback_query(F.data == "menu_support")
async def on_menu_support(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(CreateForm.waiting_support_message)
    
    chat_history = await db.get_support_chat(callback.from_user.id)
    history_text = ""
    if chat_history:
        history_text = "\n\n<b>Последние сообщения:</b>\n"
        for _, text, is_admin, _, _, f_id, f_type in chat_history[-5:]:
            prefix = "👤 Вы: " if not is_admin else "👨‍💻 Поддержка: "
            if f_type == 'text':
                content = text
            elif f_type == 'photo':
                content = "🖼 Фото"
            elif f_type == 'video':
                content = "🎥 Видео"
            else:
                content = "📎 Файл"
            history_text += f"{prefix}{content}\n"

    text = (
        "👋 Добро пожаловать в тех.поддержку!\n\n"
        "Опишите вашу проблему или отправьте фото/видео прямо здесь. "
        "Администратор ответит вам в ближайшее время."
        f"{history_text}"
    )
    await _replace_with_text(callback, text, reply_markup=back_main_keyboard(lang))
    await _safe_answer(callback)

@router.message(CreateForm.waiting_support_message)
async def on_support_message(message: Message, state: FSMContext, db: Database) -> None:
    if message.text and message.text.startswith("/"):
        return

    f_id = None
    f_type = 'text'
    text = message.text or message.caption

    if message.photo:
        f_id = message.photo[-1].file_id
        f_type = 'photo'
    elif message.video:
        f_id = message.video.file_id
        f_type = 'video'
    elif not message.text:
        return

    await db.add_support_message(message.from_user.id, text=text, file_id=f_id, file_type=f_type, is_admin=False)
    lang = await db.get_user_language(message.from_user.id)
    
    await message.answer("✅ Ваше сообщение отправлено поддержке. Ожидайте ответа.")
    from bot.keyboards import back_main_keyboard
    await message.answer("Вы можете отправить ещё что-то или вернуться в меню:", reply_markup=back_main_keyboard(lang))

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    await state.clear()
    user = message.from_user
    await db.upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    
    # Сначала проверяем доступ (соглашение, подписка, блокировка)
    if not await _ensure_access(message, db, bot):
        return

    lang = await db.get_user_language(user.id)
    await message.answer(get_string("start_welcome", lang), reply_markup=main_menu_keyboard(lang))

@router.message(F.text == "/profile")
async def cmd_profile(message: Message, db: Database) -> None:
    # Dummy callback to reuse on_menu_profile logic
    class FakeCallback:
        def __init__(self, message, from_user):
            self.message = message
            self.from_user = from_user
        async def answer(self, *args, **kwargs): pass
    await on_menu_profile(FakeCallback(message, message.from_user), db)


@router.message(F.text == "/settings")
async def cmd_settings(message: Message, db: Database) -> None:
    class FakeCallback:
        def __init__(self, message, from_user):
            self.message = message
            self.from_user = from_user
        async def answer(self, *args, **kwargs): pass
    await on_menu_settings(FakeCallback(message, message.from_user), db)

@router.message(F.text == "/reset")
async def cmd_reset(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(get_string("main_menu_title", lang), reply_markup=main_menu_keyboard(lang))


@router.message(F.text == "/help")
async def cmd_help(message: Message, db: Database) -> None:
    class FakeCallback:
        def __init__(self, message, from_user):
            self.message = message
            self.from_user = from_user
        async def answer(self, *args, **kwargs): pass
    await on_menu_howto(FakeCallback(message, message.from_user), db)

@router.callback_query(F.data.startswith("dyn_opt:"))
async def on_dynamic_option(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    step_key = data.get("current_step_key")
    lang = await db.get_user_language(callback.from_user.id)
    
    if val == "skip":
        # Пропускаем шаг
        if step_key:
            await state.update_data({step_key: ""})
            await state.update_data({f"{step_key}_label": "Пропущено"})
    else:
        # val - это ID опции (или skip)
        try:
            opt_id = int(val)
            # Нам нужно получить value и custom_prompt из step_options
            import aiosqlite
            async with aiosqlite.connect(db._db_path) as conn:
                async with conn.execute("SELECT option_text, option_value, custom_prompt FROM step_options WHERE id=?", (opt_id,)) as cur:
                    row = await cur.fetchone()
                    if row:
                        opt_text, opt_val, custom_prompt = row
                        
                        if opt_val == "back":
                            await on_back_step(callback, state, db)
                            await _safe_answer(callback)
                            return

                        if opt_val == "skip":
                            # Пропускаем шаг без сохранения ответа
                            opt_text = None
                            opt_val = None

                        if custom_prompt:
                            # Если есть кастомный промпт — запрашиваем ввод текста
                            await state.update_data(waiting_custom_for=step_key)
                            await _replace_with_text(callback, custom_prompt, reply_markup=back_step_keyboard(lang))
                            await _safe_answer(callback)
                            return
                        
                        if opt_val is not None:
                            # Иначе просто сохраняем значение
                            await state.update_data({step_key: opt_val})
                            # Также сохраняем человекочитаемое название для сводки
                            await state.update_data({f"{step_key}_label": opt_text})
        except ValueError:
            # На случай если пришло не число (старый формат или ошибка)
            await state.update_data({step_key: val})
    
    # Получаем актуальные данные после обновления значения шага
    new_data = await state.get_data()
    current_idx = new_data.get("current_step_index", 0)

    # Для пресетов после выбора пола сразу переходим к выбору модели
    if new_data.get("is_preset") and step_key == "gender":
        cat_db = await db.get_category_by_key("presets")
        if cat_db:
            steps = await db.list_steps(cat_db[0])
            for idx, s in enumerate(steps):
                if s[1] == "model_select":
                    await state.update_data(current_step_index=idx)
                    await _show_next_step(callback, state, db)
                    await _safe_answer(callback)
                    return
    
    # Переходим к следующему шагу
    await state.update_data(current_step_index=current_idx + 1)
    await _show_next_step(callback, state, db)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_dynamic_step, F.photo)
async def on_dynamic_photo(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    step_key = data.get("current_step_key")
    if not step_key:
        return
    
    photo_id = message.photo[-1].file_id
    await state.update_data({step_key: photo_id, f"{step_key}_label": "Фото загружено"})
    
    # Идем к следующему шагу
    current_idx = data.get("current_step_index", 0)
    await state.update_data(current_step_index=current_idx + 1)
    await _show_next_step(message, state, db)

@router.message(CreateForm.waiting_dynamic_step)
async def on_dynamic_input(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    
    # 0. Проверка на "Пропустить"
    if message.text and message.text.lower() in ("пропустить", "skip", "/skip"):
        step_key = data.get("current_step_key")
        if step_key:
            await state.update_data({step_key: ""})
            await state.update_data({f"{step_key}_label": "Пропущено"})
        current_idx = data.get("current_step_index", 0)
        await state.update_data(current_step_index=current_idx + 1)
        await _show_next_step(message, state, db)
        return

    # 1. Валидация текстового ввода
    if message.text:
        step_key = data.get("current_step_key")
        waiting_custom_for = data.get("waiting_custom_for")
        
        # Определяем целевой ключ для валидации
        target_key = waiting_custom_for if waiting_custom_for else step_key
        
        text_len = len(message.text)
        max_len = 200 # Дефолт
        
        if target_key:
            low_key = target_key.lower()
            if any(x in low_key for x in ("adv_", "преимущество")):
                max_len = 100
            elif any(x in low_key for x in ("extra_info", "доп_текст")):
                max_len = 80
            elif waiting_custom_for: # "Свой вариант" (если не подошло под категории выше)
                max_len = 70

        if text_len > max_len:
            lang = await db.get_user_language(message.from_user.id)
            await message.answer(f"⚠️ Текст слишком длинный ({text_len}/{max_len} симв.). Пожалуйста, сократите до {max_len} символов.")
            return

    # 2. Если мы ждали ввода для "своего варианта"
    if data.get("waiting_custom_for"):
        step_key = data.get("waiting_custom_for")
        await state.update_data({step_key: message.text})
        await state.update_data({f"{step_key}_label": message.text})
        await state.update_data(waiting_custom_for=None)
    else:
        step_key = data.get("current_step_key")
        # Если ожидается фото
        if message.photo:
            await state.update_data({step_key: message.photo[-1].file_id})
        else:
            await state.update_data({step_key: message.text})
            await state.update_data({f"{step_key}_label": message.text})
    
    # Получаем актуальные данные
    new_data = await state.get_data()
    current_idx = new_data.get("current_step_index", 0)
    
    # Переходим к следующему шагу
    await state.update_data(current_step_index=current_idx + 1)
    await _show_next_step(message, state, db)


@router.callback_query(F.data == "accept_terms")
async def on_accept_terms(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    await db.set_terms_acceptance(callback.from_user.id, True)
    # После принятия соглашения проверяем подписку (через middleware или явно)
    if await _ensure_access(callback, db, bot):
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, get_string("main_menu_title", lang), reply_markup=main_menu_keyboard(lang))
    await _safe_answer(callback)


@router.callback_query(F.data == "check_subscription")
async def on_check_subscription(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    """Обработчик кнопки 'Я подписался'"""
    if await _ensure_access(callback, db, bot):
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, get_string("main_menu_title", lang), reply_markup=main_menu_keyboard(lang))
    else:
        # Если все еще не подписан
        await _safe_answer(callback, "Вы все еще не подписаны!", show_alert=True)


@router.callback_query(F.data == "back_main")
async def on_back_main(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    current = await state.get_state()
    lang = await db.get_user_language(callback.from_user.id)
    text = get_string("main_menu_title", lang)
    # Если на экране результат (фото), не редактируем/не удаляем, а отправляем новое сообщение
    if current == CreateForm.result_ready.state:
        await callback.message.answer(text, reply_markup=main_menu_keyboard(lang))
        await state.clear()
        await _safe_answer(callback)
        return
    await state.clear()
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=main_menu_keyboard(lang))
    await _safe_answer(callback)


@router.callback_query(F.data == "menu_create")
async def on_create_photo(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Техработы: блокируем для не-админов
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", lang), show_alert=True)
            return
    balance = await db.get_user_balance(callback.from_user.id)
    price = await db.get_user_generation_price(callback.from_user.id)
    # Блокировка пользователя
    if await db.get_user_blocked(callback.from_user.id):
        await _safe_answer(callback, get_string("user_blocked", lang), show_alert=True)
        return
    if balance < price:
        await _safe_answer(callback, get_string("limit_rem_zero", lang), show_alert=True)
        return
    
    # Обычная генерация: фото (до 4) -> промпт -> генерация
    # НЕ ОЧИЩАЕМ ВЕСЬ state, чтобы не сбить параллельные загрузки, а обновляем ключи
    await state.update_data(category="normal", normal_gen_mode=True, aspect="auto", photos=[], last_photos_msg_id=None)
    
    text = "📸 Пришлите до 4 фото (можно по одному или серией)."
    await _replace_with_text(callback, text, reply_markup=back_main_keyboard(lang))
    await state.set_state(CreateForm.waiting_view)


@router.callback_query(F.data == "menu_market")
async def on_marketplace_menu(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Техработы
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", lang), show_alert=True)
            return
    balance = await db.get_user_balance(callback.from_user.id)
    price = await db.get_user_generation_price(callback.from_user.id)
    # Блокировка пользователя
    if await db.get_user_blocked(callback.from_user.id):
        await _safe_answer(callback, get_string("user_blocked", lang), show_alert=True)
        return
    if balance < price:
        await _safe_answer(callback, get_string("limit_rem_zero", lang), show_alert=True)
        return
    
    statuses = await db.list_categories_enabled()
    from bot.keyboards import marketplace_menu_keyboard
    await _replace_with_text(callback, get_string("marketplace_menu", lang), reply_markup=marketplace_menu_keyboard(statuses, lang))
    await _safe_answer(callback)


async def _ensure_access(message_or_callback: Message | CallbackQuery, db: Database, bot: Bot) -> bool:
    """Проверяет условия доступа (соглашение и подписка) и выводит нужный экран"""
    user_id = message_or_callback.from_user.id
    lang = await db.get_user_language(user_id)
    from bot.keyboards import terms_keyboard, subscription_check_keyboard
    
    # 1. Сначала Блокировка
    if await db.get_user_blocked(user_id):
        text = get_string("user_blocked", lang)
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(text)
        else:
            await _replace_with_text(message_or_callback, text)
        return False

    # 2. Проверка администратора (админы проходят мимо подписки и соглашения)
    settings = load_settings()
    if user_id in (settings.admin_ids or []):
        logger.info(f"Admin {user_id} bypasses access checks")
        return True

    # 3. Потом Соглашение
    accepted = await db.get_user_accepted_terms(user_id)
    if not accepted:
        text = get_string("start_welcome", lang)
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(text, reply_markup=terms_keyboard(lang))
        else:
            await _replace_with_text(message_or_callback, text, reply_markup=terms_keyboard(lang))
        return False
        
    # 4. Потом Подписка
    channel_id = await db.get_app_setting("required_channel_id")
    logger.info(f"Checking subscription for {user_id} in channel '{channel_id}'")
    if channel_id and str(channel_id).strip():
        is_subbed = await _check_subscription(user_id, bot, db)
        logger.info(f"User {user_id} sub status: {is_subbed}")
        if not is_subbed:
            channel_url = await db.get_app_setting("required_channel_url", "https://t.me/bnbslow")
            text = get_string("subscribe_channel", lang)
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(text, reply_markup=subscription_check_keyboard(channel_url, lang))
            else:
                await _replace_with_text(message_or_callback, text, reply_markup=subscription_check_keyboard(channel_url, lang))
            return False
            
    return True

@router.callback_query(F.data.startswith("create_cat:"))
async def on_create_category_universal(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    """Универсальный обработчик выбора категории, поддерживающий динамические шаги"""
    cat_key = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)

    # Техработы
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", lang), show_alert=True)
            return
            
    # Проверка, что категория включена
    if not await db.get_category_enabled(cat_key):
        await _safe_answer(callback, get_string("no_models_in_category_alert", lang), show_alert=True)
        return

    # Специальные меню-прокладки (инфографика)
    if cat_key == "infographics":
        await on_infographic_selection_menu(callback, db)
        return

    # Инициализация состояния
    await state.clear()
    await state.update_data(category=cat_key)
    
    # Устанавливаем флаги режимов для совместимости с промптами
    if cat_key == "random": await state.update_data(random_mode=True)
    elif cat_key == "random_other": await state.update_data(random_other_mode=True)
    elif cat_key == "own": await state.update_data(own_mode=True)
    elif cat_key == "presets": await state.update_data(is_preset=True)
    elif cat_key.startswith("infographic"): await state.update_data(infographic_mode=True)
    elif cat_key == "storefront": await state.update_data(storefront_mode=True)
    
    # Пытаемся запустить динамический флоу
    category_db = await db.get_category_by_key(cat_key)
    if category_db:
        steps = await db.list_steps(category_db[0])
        if steps:
            # Сбрасываем ответы шагов, чтобы новый запуск не пропускал первый шаг
            reset_payload = {s[1]: None for s in steps}
            reset_payload["current_step_index"] = 0
            await state.update_data(**reset_payload)
            await _show_next_step(callback, state, db)
            await _safe_answer(callback)
            return

    # Если динамических шагов нет — используем старую логику (фолбэк)
    if cat_key == "female": await on_female_category(callback, db, state)
    elif cat_key == "male": await on_male_category(callback, db, state)
    elif cat_key == "child": await on_child_category(callback, db, state)
    elif cat_key == "storefront": await on_storefront_category(callback, db, state)
    elif cat_key == "whitebg": await on_whitebg_category(callback, db, state)
    elif cat_key == "own": await on_create_own(callback, db, state)
    elif cat_key == "own_variant": await on_create_own_variant(callback, db, state)
    elif cat_key == "random": await on_create_random(callback, state, db)
    elif cat_key == "random_other": await _show_next_step(callback, state, db)
    elif cat_key.startswith("infographic"): await _show_next_step(callback, state, db)
    elif cat_key == "presets": await on_ready_presets(callback, db, state)
    
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("preset_gender:"))
async def on_preset_gender_selected(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    gender = callback.data.split(":")[1]
    await state.clear()
    
    # Если в пресетах есть шаг выбора модели — используем динамический флоу
    cat_db = await db.get_category_by_key("presets")
    if cat_db:
        steps = await db.list_steps(cat_db[0])
        for idx, s in enumerate(steps):
            if s[1] == "model_select":
                # Сбрасываем ответы шагов, но сохраняем выбранный пол
                reset_payload = {st[1]: None for st in steps}
                reset_payload.update({
                    "category": "presets",
                    "is_preset": True,
                    "gender": gender,
                    "gender_label": get_string("cat_female", await db.get_user_language(callback.from_user.id)) if gender == "female"
                        else get_string("cat_male", await db.get_user_language(callback.from_user.id)) if gender == "male"
                        else get_string("gender_boy", await db.get_user_language(callback.from_user.id)) if gender == "boy"
                        else get_string("gender_girl", await db.get_user_language(callback.from_user.id)),
                    "current_step_index": idx
                })
                await state.update_data(**reset_payload)
                await _show_next_step(callback, state, db)
                await _safe_answer(callback)
                return
    
    # Сохраняем выбранный пол и флаг пресета (фолбэк)
    await state.update_data(category="presets", gender=gender, is_preset=True)

    # Иначе показываем выбор моделей для этого пола (старый флоу)
    await _show_models_for_category(callback, db, category=gender, cloth="all", index=0, logic_category="presets")
    await _safe_answer(callback)

async def on_infographic_selection_menu(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    enabled = await db.list_categories_enabled()
    from bot.keyboards import infographic_selection_keyboard
    await _replace_with_text(callback, get_string("cat_infographics", lang), reply_markup=infographic_selection_keyboard(enabled, lang))

async def on_ready_presets(callback: CallbackQuery, db: Database, state: FSMContext | None = None) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Если в конструкторе есть шаги для пресетов — используем их напрямую
    cat_db = await db.get_category_by_key("presets")
    if cat_db and state:
        steps = await db.list_steps(cat_db[0])
        if steps:
            # Сбрасываем ответы шагов и запускаем флоу
            reset_payload = {s[1]: None for s in steps}
            reset_payload.update({"category": "presets", "is_preset": True, "current_step_index": 0})
            await state.clear()
            await state.update_data(**reset_payload)
            await _show_next_step(callback, state, db)
            await _safe_answer(callback)
            return
    enabled = await db.list_categories_enabled()
    from bot.keyboards import ready_presets_keyboard
    await _replace_with_text(callback, get_string("cat_presets", lang), reply_markup=ready_presets_keyboard(enabled, lang))

async def on_female_category(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    # Фолбэк (теперь всё в БД)
    await state.clear()
    await state.update_data(category="female", cloth="all", is_preset=True)
    
    category_db = await db.get_category_by_key("female")
    if category_db:
        await state.update_data(current_step_index=0)
        await _show_next_step(callback, state, db)
    else:
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, "🎂 Введите возраст модели числом:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_dynamic_step)
        await state.update_data(current_step_key="age")

async def on_male_category(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    # Фолбэк
    await state.clear()
    await state.update_data(category="male", cloth="all", is_preset=True)
    
    category_db = await db.get_category_by_key("male")
    if category_db:
        await state.update_data(current_step_index=0)
        await _show_next_step(callback, state, db)
    else:
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, "🎂 Введите возраст модели числом:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_dynamic_step)
        await state.update_data(current_step_key="age")

async def _show_models_for_category(callback: CallbackQuery, db: Database, category: str, cloth: str, index: int = 0, logic_category: str = None) -> None:
    total = await db.count_models(category, cloth)
    if total <= 0:
        await _safe_answer(callback, "Модели не найдены", show_alert=True)
        return
    
    # Ограничиваем индекс
    if index < 0: index = total - 1
    if index >= total: index = 0
    
    text = _model_header(index, total)
    model = await db.get_model_by_index(category, cloth, index)
    
    lang = await db.get_user_language(callback.from_user.id)
    kb = model_select_keyboard(category, cloth, index, total, lang, logic_category=logic_category)
    
    if model and model[3]:
        # photo_file_id или путь
        res_msg = await _answer_model_photo(callback, model[3], text, kb)
        
        # Кэшируем file_id в базу, если это был локальный файл (для мгновенной загрузки в след. раз)
        if res_msg and res_msg.photo and not model[3].startswith("AgAC"):
            new_file_id = res_msg.photo[-1].file_id
            await db.set_model_photo(model[0], new_file_id)
            logger.info(f"Cached file_id for model {model[0]}")
    else:
        await _replace_with_text(callback, text, reply_markup=kb)

async def on_child_category(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    # Фолбэк
    await state.update_data(category="child")
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=child_gender_keyboard(lang))

async def on_create_random(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Оставляем тело функции для фолбэка
    await state.clear()
    await state.update_data(random_mode=True, category="random")
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_loc_group", lang), reply_markup=random_loc_group_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_loc_group)

@router.callback_query(CreateForm.waiting_rand_loc, F.data.startswith("rand_location:"))
@router.callback_query(CreateForm.waiting_custom_location)
async def on_random_location_after(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Сохраняем локацию если она пришла из колбэка
    if callback.data.startswith("rand_location:"):
        loc = callback.data.split(":", 1)[1]
        await state.update_data(rand_location=loc)
    
    lang = await db.get_user_language(callback.from_user.id)
    # 2. Пол
    await _replace_with_text(callback, get_string("select_model_gender", lang), reply_markup=random_gender_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_gender)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_custom_location)
async def on_random_location_custom_msg(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    await state.update_data(rand_location_custom=text, rand_location="custom")
    lang = await db.get_user_language(message.from_user.id)
    # 2. Пол
    await message.answer(get_string("select_model_gender", lang), reply_markup=random_gender_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_gender)

@router.callback_query(F.data.startswith("rand_gender:"))
async def on_random_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    gender = callback.data.split(":")[1]
    await state.update_data(rand_gender=gender)
    lang = await db.get_user_language(callback.from_user.id)
    
    # 2.1 Если юзер выбирает Женский/Мужской то мы уточняем возраст
    if gender in ("male", "female"):
        await _replace_with_text(callback, "🎂 Введите возраст модели числом:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_dynamic_step)
        await state.update_data(current_step_key="age")
    else:
        # Для мальчик/девочка сразу к размеру
        await _replace_with_text(callback, "📏 Введите размер одежды или телосложение числом:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_dynamic_step)
        await state.update_data(current_step_key="size")
    await _safe_answer(callback)


async def on_create_random_other(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Оставляем тело функции для фолбэка
    await state.clear()
    await state.update_data(random_other_mode=True, category="random_other")
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_has_person)

@router.callback_query(CreateForm.waiting_rand_other_has_person, F.data.startswith("choice:"))
async def on_rand_other_has_person(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    choice = callback.data.split(":")[1]
    has_person = (choice == "yes")
    await state.update_data(has_person=has_person)
    lang = await db.get_user_language(callback.from_user.id)
    
    if has_person:
        # Если есть человек — спрашиваем пол (п. 1)
        from bot.keyboards import infographic_gender_keyboard
        await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_gender)
    else:
        # Если нет человека — сразу к нагрузке (п. 2)
        await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=skip_step_keyboard("info_load", lang))
        await state.set_state(CreateForm.waiting_info_load)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_rand_other_gender, F.data.startswith("info_gender:"))
async def on_rand_other_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    lang = await db.get_user_language(callback.from_user.id)
    # После пола — нагруженность (п. 2)
    await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=skip_step_keyboard("info_load", lang))
    await state.set_state(CreateForm.waiting_info_load)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_rand_other_name)
@router.callback_query(F.data == "rand_name:skip")
async def on_rand_other_name(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(message_or_callback.from_user.id)
    
    if isinstance(message_or_callback, Message):
        text = (message_or_callback.text or "").strip()
        if not text or len(text) > 50:
            await message_or_callback.answer("⚠️ Название слишком длинное (максимум 50 символов). Попробуйте еще раз:")
            return
        await state.update_data(product_name=text)
    else:
        await state.update_data(product_name="")
        
    from bot.keyboards import form_view_keyboard
    msg_text = "Выберите угол камеры (Спереди/Сзади):"
    markup = form_view_keyboard(lang)
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(msg_text, reply_markup=markup)
    else:
        await _replace_with_text(message_or_callback, msg_text, reply_markup=markup)
        await _safe_answer(message_or_callback)
    await state.set_state(CreateForm.waiting_rand_other_angle)

@router.callback_query(CreateForm.waiting_rand_other_angle, F.data.startswith("form_view:"))
async def on_rand_other_angle(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    view = callback.data.split(":")[1]
    await state.update_data(view=view)
    lang = await db.get_user_language(callback.from_user.id)
    # После угла — Ракурс (Дальний/Средний/Близкий) (п. 5)
    from bot.keyboards import camera_dist_keyboard
    await _replace_with_text(callback, "Выберите ракурс фотографии (Дальний/Средний/Близкий):", reply_markup=camera_dist_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_dist)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_rand_other_dist, F.data.startswith("angle:"))
async def on_rand_other_dist(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    dist = callback.data.split(":")[1]
    await state.update_data(dist=dist)
    lang = await db.get_user_language(callback.from_user.id)
    
    # После ракурса — Высота (п. 6: сперва высоту потом ширину и потом длину)
    await _replace_with_text(callback, "Введите высоту (см):", reply_markup=skip_step_keyboard("rand_height", lang))
    await state.set_state(CreateForm.waiting_rand_other_height)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_rand_other_height)
@router.callback_query(F.data == "rand_height:skip")
async def on_rand_other_height(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(message_or_callback.from_user.id)
    if isinstance(message_or_callback, Message):
        text = (message_or_callback.text or "").strip()
        await state.update_data(height_cm=text)
    else:
        await state.update_data(height_cm="")
    
    # После высоты — Ширина (п. 6)
    msg_text = "Введите ширину (см):"
    markup = skip_step_keyboard("rand_width", lang)
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(msg_text, reply_markup=markup)
    else:
        await _replace_with_text(message_or_callback, msg_text, reply_markup=markup)
        await _safe_answer(message_or_callback)
    await state.set_state(CreateForm.waiting_rand_other_width)

@router.message(CreateForm.waiting_rand_other_width)
@router.callback_query(F.data == "rand_width:skip")
async def on_rand_other_width(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(message_or_callback.from_user.id)
    if isinstance(message_or_callback, Message):
        text = (message_or_callback.text or "").strip()
        await state.update_data(width_cm=text)
    else:
        await state.update_data(width_cm="")
    
    # После ширины — Длина (п. 6)
    msg_text = "Введите длину (см):"
    markup = skip_step_keyboard("rand_length", lang)
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(msg_text, reply_markup=markup)
    else:
        await _replace_with_text(message_or_callback, msg_text, reply_markup=markup)
        await _safe_answer(message_or_callback)
    await state.set_state(CreateForm.waiting_rand_other_length)

@router.message(CreateForm.waiting_rand_other_length)
@router.callback_query(F.data == "rand_length:skip")
async def on_rand_other_length(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(message_or_callback.from_user.id)
    if isinstance(message_or_callback, Message):
        text = (message_or_callback.text or "").strip()
        await state.update_data(length_cm=text)
    else:
        await state.update_data(length_cm="")
    
    # После длины — Сезон (п. 7)
    from bot.keyboards import random_season_keyboard
    msg_text = "Выберите сезон:"
    markup = random_season_keyboard(lang)
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(msg_text, reply_markup=markup)
    else:
        await _replace_with_text(message_or_callback, msg_text, reply_markup=markup)
        await _safe_answer(message_or_callback)
    await state.set_state(CreateForm.waiting_rand_other_season)

@router.callback_query(CreateForm.waiting_rand_other_season, F.data.startswith("rand_season:"))
async def on_rand_other_season(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    season = callback.data.split(":")[1]
    await state.update_data(season="" if season == "skip" else season)
    lang = await db.get_user_language(callback.from_user.id)
    # После сезона — Стиль (п. 8)
    from bot.keyboards import style_keyboard
    await _replace_with_text(callback, get_string("select_style", lang), reply_markup=style_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_style)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_rand_other_season)
async def on_rand_other_season_message(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    await state.update_data(season=text)
    lang = await db.get_user_language(message.from_user.id)
    from bot.keyboards import style_keyboard
    await message.answer(get_string("select_style", lang), reply_markup=style_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_style)

@router.callback_query(CreateForm.waiting_rand_other_style, F.data.startswith("style:"))
async def on_rand_other_style(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if val == "custom":
        await _replace_with_text(callback, get_string("enter_custom_style", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_style_custom)
    else:
        if val != "skip":
            await state.update_data(style=val)
        else:
            await state.update_data(style="")
        
        # 11. ФОТО ТОВАРА (в конце)
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]])
        await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_kb)
        await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_rand_other_style_custom)
async def on_rand_other_style_custom(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    await state.update_data(style=text)
    lang = await db.get_user_language(message.from_user.id)
    
    # 11. ФОТО ТОВАРА (в конце)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]])
    await message.answer(get_string("upload_photo", lang), reply_markup=back_kb)
    await state.set_state(CreateForm.waiting_view)


@router.callback_query(F.data == "create_cat:storefront")
async def on_storefront_category(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id in (settings.admin_ids or []): pass
        else:
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
    if not await db.get_category_enabled("storefront"):
        await _safe_answer(callback, get_string("no_models_in_category_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
        return
    await state.clear()
    await state.update_data(category="storefront", storefront_mode=True)
    lang = await db.get_user_language(callback.from_user.id)
    
    # Теперь для Витрины запрашиваем пол, чтобы показать фоны (как в пресетах)
    from bot.keyboards import gender_selection_keyboard
    await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=gender_selection_keyboard("storefront", lang))
    await _safe_answer(callback)


async def on_whitebg_category(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
    if not await db.get_category_enabled("whitebg"):
        await _safe_answer(callback, get_string("no_models_in_category_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
        return
    await state.clear()
    await state.update_data(category="whitebg")
    lang = await db.get_user_language(callback.from_user.id)
    # Кнопка назад в меню маркетплейсов
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_market")]])
    await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_kb)
    await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("gender_select:"))
async def on_generic_gender_select(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    parts = callback.data.split(":")
    category = parts[1]
    gender = parts[2]
    
    # Сохраняем данные
    await state.update_data(category=category, gender=gender, cloth="all")
    
    # Если это категория child, дополнительно помечаем child_gender для совместимости
    if gender in ("boy", "girl") or category == "child":
        await state.update_data(child_gender=gender)
        
    # Сразу показываем модели для этой категории и пола
    # Для Витрины реализуем логику: сначала ищем модели именно в категории storefront с типом одежды = пол
    if category == "storefront":
        total_sf = await db.count_models("storefront", gender)
        if total_sf > 0:
            await _show_models_for_category(callback, db, "storefront", gender)
        else:
            # ВАЖНО: витрина должна брать промпт строго из вкладки "Витрина" (models.category='storefront').
            # Поэтому без fallback на женские/мужские модели.
            await _safe_answer(
                callback,
                get_string("no_models_in_category_alert", await db.get_user_language(callback.from_user.id)),
                show_alert=True,
            )
            return
    else:
        await _show_models_for_category(callback, db, category, "all")
    await _safe_answer(callback)

# --- РАЗДЕЛ ИНФОГРАФИКА ---

@router.callback_query(F.data == "create_cat:infographics")
async def on_infographics_menu(callback: CallbackQuery, db: Database) -> None:
    enabled = await db.list_categories_enabled()
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import infographic_selection_keyboard
    await _replace_with_text(callback, get_string("select_infographic_type", lang), reply_markup=infographic_selection_keyboard(enabled, lang))
    await _safe_answer(callback)


async def on_infographic_category(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
    cat = callback.data.split(":")[1]
    # Проверка, что категория включена
    if not await db.get_category_enabled(cat):
        await _safe_answer(callback, get_string("no_models_in_category_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
        return
    await state.clear()
    await state.update_data(category=cat, infographic_mode=True)
    lang = await db.get_user_language(callback.from_user.id)
    
    if cat == "infographic_clothing":
        # 1. Пол (п. 4.1)
        await state.update_data(has_person=True)
        await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang, back_data="create_cat:infographics"))
        await state.set_state(CreateForm.waiting_info_gender)
    else: # infographic_other
        # Сначала спрашиваем Присутствие человека (новые требования)
        await _replace_with_text(callback, "👤 Присутствует ли человек на фото?", reply_markup=yes_no_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_has_person)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_info_has_person, F.data.startswith("choice:"))
async def on_info_has_person(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    choice = callback.data.split(":")[1]
    has_person = (choice == "yes")
    await state.update_data(has_person=has_person)
    lang = await db.get_user_language(callback.from_user.id)
    
    if has_person:
        from bot.keyboards import infographic_gender_keyboard
        await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_gender)
    else:
        # Если нет человека — сразу к нагрузке (п. 2 в списке пользователя)
        await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=skip_step_keyboard("info_load", lang))
        await state.set_state(CreateForm.waiting_info_load)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_info_gender, F.data.startswith("info_gender:"))
async def on_infographic_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    g = callback.data.split(":")[1]
    await state.update_data(info_gender=g)
    lang = await db.get_user_language(callback.from_user.id)
    
    # 2. Возраст (п. 4.2)
    await _replace_with_text(callback, "🔢 Введите возраст модели числом:", reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_age)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_info_age)
async def on_info_age(message: Message, state: FSMContext, db: Database) -> None:
    age_text = (message.text or "").strip()
    await state.update_data(age=age_text)
    lang = await db.get_user_language(message.from_user.id)
    
    # 3. Нагруженность инфографики (п. 4.3)
    await message.answer(get_string("enter_info_load", lang), reply_markup=skip_step_keyboard("info_load", lang))
    await state.set_state(CreateForm.waiting_info_load)


@router.callback_query(F.data.startswith("info_style:"))
async def on_infographic_style(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":")[1]
    await state.update_data(info_style=val)
    lang = await db.get_user_language(callback.from_user.id)
    # Запрашиваем нагруженность как текстовый ввод от 1 до 10
    await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=skip_step_keyboard("info_load", lang))
    await state.set_state(CreateForm.waiting_info_load)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_info_load)
async def on_infographic_load_input(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    data = await state.get_data()
    
    # Извлекаем только цифры или проверяем на пропуск
    load_value = ""
    if text.lower() not in ("пропустить", "skip"):
        digits = ''.join(ch for ch in text if ch.isdigit())
        if not digits or not (1 <= int(digits) <= 10):
            await message.answer(get_string("enter_info_load_error", lang))
            return
        load_value = digits
    
    await state.update_data(info_load=load_value)

    if data.get("random_other_mode"):
        # Рандом для остальных товаров — Название продукта (п. 3)
        from bot.keyboards import skip_step_keyboard
        await message.answer(get_string("enter_product_name", lang), reply_markup=skip_step_keyboard("rand_name", lang))
        await state.set_state(CreateForm.waiting_rand_other_name)
    else:
        # 4. Язык инфографики (п. 4.4)
        from bot.keyboards import info_lang_keyboard
        await message.answer(get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_lang)

@router.callback_query(F.data == "info_load:skip")
async def on_infographic_load_skip_btn(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.update_data(info_load="")
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    if data.get("random_other_mode"):
        # Рандом для остальных товаров — Название продукта
        await _replace_with_text(callback, get_string("enter_product_name", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_name)
    else:
        # Выбор языка
        from bot.keyboards import info_lang_keyboard
        await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_lang)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_info_lang, F.data.startswith("info_lang:"))
async def on_infographic_lang(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    
    if val == "custom":
        await _replace_with_text(callback, get_string("enter_info_lang_custom", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_lang_custom)
        await _safe_answer(callback)
        return
        
    await state.update_data(info_lang="" if val == "skip" else val)
    # Далее Название бренда/товара (п. 5)
    await _replace_with_text(callback, get_string("enter_info_brand", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_brand)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_info_lang_custom)
async def on_infographic_lang_custom(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if not text:
        await message.answer(get_string("enter_lang_error", lang))
        return
    await state.update_data(info_lang=text)
    await message.answer(get_string("enter_info_brand", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_brand)


@router.message(CreateForm.waiting_info_brand)
async def on_infographic_brand(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if not text:
        await message.answer(get_string("enter_info_brand_error", lang))
        return
    if len(text) > 50:
        await message.answer("⚠️ Название слишком длинное (максимум 50 символов). Попробуйте еще раз:")
        return
    await state.update_data(info_brand=text)
    # Преймущества 1-2-3 (п. 5)
    await message.answer(get_string("enter_adv1_skip", lang), reply_markup=skip_step_keyboard("info_adv1", lang))
    await state.set_state(CreateForm.waiting_info_adv1)


@router.message(CreateForm.waiting_info_adv1)
async def on_infographic_adv1(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if len(text) > 100:
        await message.answer("⚠️ Текст слишком длинный (максимум 100 символов). Попробуйте еще раз:")
        return
    await state.update_data(info_adv1=text)
    await message.answer(get_string("enter_adv2_skip", lang), reply_markup=skip_step_keyboard("info_adv2", lang))
    await state.set_state(CreateForm.waiting_info_adv2)

@router.message(CreateForm.waiting_info_adv2)
async def on_infographic_adv2(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if len(text) > 100:
        await message.answer("⚠️ Текст слишком длинный (максимум 100 символов). Попробуйте еще раз:")
        return
    await state.update_data(info_adv2=text)
    await message.answer(get_string("enter_adv3_skip", lang), reply_markup=skip_step_keyboard("info_adv3", lang))
    await state.set_state(CreateForm.waiting_info_adv3)

@router.message(CreateForm.waiting_info_adv3)
async def on_infographic_adv3(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if len(text) > 100:
        await message.answer("⚠️ Текст слишком длинный (максимум 100 символов). Попробуйте еще раз:")
        return
    await state.update_data(info_adv3=text)
    await message.answer(get_string("enter_extra_info_skip", lang), reply_markup=skip_step_keyboard("info_extra", lang))
    await state.set_state(CreateForm.waiting_info_extra)

@router.callback_query(F.data == "info_adv1:skip")
async def on_infographic_adv1_skip(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(info_adv1="")
    await _replace_with_text(callback, get_string("enter_adv2_skip", lang), reply_markup=skip_step_keyboard("info_adv2", lang))
    await state.set_state(CreateForm.waiting_info_adv2)
    await _safe_answer(callback)

@router.callback_query(F.data == "info_adv2:skip")
async def on_infographic_adv2_skip(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(info_adv2="")
    await _replace_with_text(callback, get_string("enter_adv3_skip", lang), reply_markup=skip_step_keyboard("info_adv3", lang))
    await state.set_state(CreateForm.waiting_info_adv3)
    await _safe_answer(callback)

@router.callback_query(F.data == "info_adv3:skip")
async def on_infographic_adv3_skip(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(info_adv3="")
    await _replace_with_text(callback, get_string("enter_extra_info_skip", lang), reply_markup=skip_step_keyboard("info_extra", lang))
    await state.set_state(CreateForm.waiting_info_extra)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_info_extra)
async def on_infographic_extra(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if len(text) > 65:
        await message.answer("⚠️ Текст слишком длинный (максимум 65 символов). Попробуйте еще раз:")
        return
    await state.update_data(info_extra=text)
    
    data = await state.get_data()
    if data.get("category") == "infographic_other":
        # Для прочих товаров: Угол камеры (п. 8)
        from bot.keyboards import form_view_keyboard
        await message.answer("Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_angle)
    else:
        # Для одежды: Параметры модели (п. 7)
        await message.answer("📏 Введите размер одежды или телосложение числом:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_dynamic_step)
        await state.update_data(current_step_key="size")

@router.callback_query(F.data == "info_extra:skip")
async def on_infographic_extra_skip(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(info_extra="")
    
    data = await state.get_data()
    if data.get("category") == "infographic_other":
        from bot.keyboards import form_view_keyboard
        await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_angle)
    else:
        # Для одежды: Параметры модели (п. 7)
        await _replace_with_text(callback, "📏 Введите размер одежды или телосложение числом:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_dynamic_step)
        await state.update_data(current_step_key="size")
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_has_person, F.data.startswith("choice:"))
async def on_has_person_selected(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":")[1]
    has_person = (val == "yes")
    await state.update_data(has_person=has_person)
    
    lang = await db.get_user_language(callback.from_user.id)
    # После выбора наличия человека в рандоме для прочего - переходим к выбору локации
    await _replace_with_text(callback, "Где будет находиться товар?", reply_markup=random_loc_group_keyboard(lang))
    # Мы не меняем стейт тут, так как rand_locgroup: обработает дальше
    await _safe_answer(callback)


# Own flow (reference + product)
async def on_create_own(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Техработы: блокируем для не-админов
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    # Категория может быть выключена в админке
    if not await db.get_category_enabled("own"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    await state.clear()
    await state.update_data(own_mode=True, category="own")
    
    # 1. Длина изделия (п. 8.1) — начинаем сразу с параметров, без фото модели
    await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)


# Own Background Variant Flow
async def on_create_own_variant(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
    if not await db.get_category_enabled("own_variant"):
        await _safe_answer(callback, get_string("no_models_in_category_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
        return
    await state.clear()
    await state.update_data(category="own_variant")
    lang = await db.get_user_language(callback.from_user.id)
    # 1. Фото фона (п. 9.1)
    await _replace_with_text(callback, get_string("upload_background", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_own_bg_photo)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_own_bg_photo, F.photo)
async def on_own_bg_photo(message: Message, state: FSMContext, db: Database) -> None:
    photo_id = message.photo[-1].file_id
    await state.update_data(own_bg_photo_id=photo_id)
    lang = await db.get_user_language(message.from_user.id)
    # 2. Фото товара (п. 9.2)
    await message.answer(get_string("upload_product", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_own_product_photo)

@router.message(CreateForm.waiting_own_product_photo, F.photo)
async def on_own_variant_product_photo(message: Message, state: FSMContext, db: Database) -> None:
    photo_id = message.photo[-1].file_id
    await state.update_data(own_product_photo_id=photo_id)
    data = await state.get_data()
    if data.get("own_mode"):
        # Для "Свой вариант модели" после фото сразу на генерацию
        await _do_generate(message, state, db)
        return
    # 3. Длина рукава (п. 9.3)
    await _ask_sleeve_length(message, state, db)


@router.message(CreateForm.waiting_prompt, F.text)
async def on_prompt_input(message: Message, state: FSMContext, db: Database) -> None:
    prompt = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if len(prompt) > 2500:
        await message.answer(get_string("enter_prompt_error", lang), reply_markup=back_step_keyboard(lang))
        return
    
    await state.update_data(prompt=prompt)
    data = await state.get_data()
    if data.get("normal_gen_mode"):
        await _do_generate(message, state, db)
        return
    await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    await state.set_state(CreateForm.waiting_aspect)


@router.callback_query(F.data == "normal_photos_done")
async def on_normal_photos_done(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    photos = data.get("photos") or []
    if not photos:
        await _safe_answer(callback)
        await _replace_with_text(callback, "📸 Пришлите хотя бы одно фото.", reply_markup=back_step_keyboard(lang))
        return
    await _replace_with_text(callback, "✍️ Теперь отправьте промпт (до 2500 символов).", reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_prompt)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_aspect, F.data.startswith("form_aspect:"))
async def on_aspect_selected(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    aspect = callback.data.split(":", 1)[1]
    # Приводим к единому формату
    aspect = aspect.replace('x', ':')
    await state.update_data(aspect=aspect)
    
    # Возвращаемся в основной флоу для показа подтверждения
    await _show_next_step(callback, state, db)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_ref_photo, F.photo)
async def on_own_ref_photo(message: Message, state: FSMContext, db: Database) -> None:
    ref_id = message.photo[-1].file_id
    await state.update_data(own_ref_photo_id=ref_id)
    # Далее длина изделия (п. 8.1)
    await _ask_garment_length(message, state, db)


@router.message(CreateForm.waiting_product_photo, F.photo)
async def on_own_model_product_photo(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    if data.get("repeat_mode"):
        await state.update_data(repeat_mode=False)
        from bot.keyboards import aspect_ratio_keyboard
        lang = await db.get_user_language(message.from_user.id)
        await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)
        return
        
    prod_id = message.photo[-1].file_id
    await state.update_data(own_product_photo_id=prod_id)
    
    # Для режима "Свой вариант модели" переходим к выбору рукава (п. 3)
    if data.get("own_mode"):
        await _ask_sleeve_length(message, state, db)
    else:
        # Сразу переходим к выбору формата для прочих (если такие есть через этот хендлер)
        lang = await db.get_user_language(message.from_user.id)
        from bot.keyboards import aspect_ratio_keyboard
        await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)


@router.callback_query(F.data.startswith("own_view:"))
async def on_own_view(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    view = callback.data.split(":", 1)[1]
    await state.update_data(own_view=view)
    # Сразу переходим к длине изделия (убираем вопрос о телосложении)
    await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_own_size, F.data.startswith("form_size:"))
async def on_own_size(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Переиспользуем общий размер и кладём в own_size, если own_mode
    val = callback.data.split(":", 1)[1]
    size_map = {"thin": "Худая", "curvy": "Пышная", "plus": "Очень пышная"}
    current = await state.get_data()
    if current.get("own_mode"):
        await state.update_data(own_size=size_map.get(val, ""))
        await _ask_garment_length(callback, state, db)
        await _safe_answer(callback)
        return
    await _safe_answer(callback)


@router.message(CreateForm.waiting_own_length)
async def on_own_length(message: Message, state: FSMContext, db: Database) -> None:
    length_text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if not length_text:
        await message.answer("Длина не может быть пустой. Укажите числом (см) или словами.")
        return
    await state.update_data(own_length=length_text)
    await state.set_state(CreateForm.waiting_own_sleeve)
    await message.answer(get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))



@router.callback_query(F.data.startswith("cut_type:"))
async def on_own_cut(callback: CallbackQuery, state: FSMContext) -> None:
    val = callback.data.split(":", 1)[1]
    cut_map = {
        "fitted": "Приталенный",
        "straight": "Прямой",
        "oversize": "Оверсайз",
        "a_line": "А-силуэт",
        "skip": "",
    }
    await state.update_data(own_cut=cut_map.get(val, ""))
    # Предпросмотр и подтверждение
    data = await state.get_data()
    size = data.get("own_size") or "—"
    length = data.get("own_length") or "—"
    sleeve = data.get("own_sleeve") or "—"
    cut = data.get("own_cut") or "—"
    view = "Спереди" if (data.get("own_view") == "front") else "Сзади"
    preview = (
        "📋 Проверьте параметры:\n\n"
        f"👀 Вид: {view}\n"
        f"📐 Телосложение: {size}\n"
        f"📏 Длина изделия: {length}\n"
        f"🧥 Длина рукава: {sleeve}\n"
        f"✂️ Тип кроя: {cut}\n"
    )
    await _replace_with_text(callback, preview, reply_markup=confirm_generation_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("rand_locgroup:"))
async def on_random_locgroup(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    group = callback.data.split(":", 1)[1]
    await state.update_data(rand_loc_group=group)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import random_location_keyboard
    await _replace_with_text(callback, get_string("select_location", lang), reply_markup=random_location_keyboard(group, lang))
    await state.set_state(CreateForm.waiting_rand_loc)
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("rand_location:"))
async def on_random_location(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    loc = callback.data.split(":", 1)[1]
    await state.update_data(rand_location=loc)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import random_vibe_keyboard
    await _replace_with_text(callback, get_string("select_vibe", lang), reply_markup=random_vibe_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_vibe)
    await _safe_answer(callback)

@router.callback_query(F.data == "rand_location_custom")
async def on_random_location_custom(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(CreateForm.waiting_custom_location)
    await _replace_with_text(callback, get_string("enter_custom_loc", lang))
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("rand_vibe:"))
async def on_random_vibe(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    vibe = callback.data.split(":", 1)[1]
    await state.update_data(rand_vibe=vibe)
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if data.get("rand_location") == "photo_studio":
        from bot.keyboards import random_decor_keyboard
        await _replace_with_text(callback, "Декор фотостудии:", reply_markup=random_decor_keyboard(lang))
    elif data.get("random_other_mode"):
        from bot.keyboards import aspect_ratio_keyboard
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)
    else:
        from bot.keyboards import random_shot_keyboard
        await _replace_with_text(callback, get_string("select_view", lang), reply_markup=random_shot_keyboard(lang))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("rand_decor:"))
async def on_random_decor(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    decor = callback.data.split(":", 1)[1]
    await state.update_data(rand_decor=decor)
    data = await state.get_data()
    if data.get("random_other_mode"):
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)
    else:
        await _replace_with_text(callback, "Выберите ракурс:", reply_markup=random_shot_keyboard())
    await _safe_answer(callback)


def _unused_random_age_input():
    return None


@router.callback_query(F.data.startswith("rand_shot:"))
async def on_random_shot(callback: CallbackQuery, state: FSMContext) -> None:
    shot = callback.data.split(":", 1)[1]
    await state.update_data(rand_shot=shot)
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "🎂 Введите возраст модели числом:", reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_dynamic_step)
    await state.update_data(current_step_key="age")
    await _safe_answer(callback)


@router.callback_query(F.data == "female_mode:model_bg")
async def on_female_mode_model_bg(callback: CallbackQuery) -> None:
    text = "👕 Выберите тип одежды:"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=female_clothes_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "female_mode:plus")
async def on_female_mode_plus(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(plus_mode=True)
    text = "🚻 Выберите пол для большого размера:"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=plus_gender_keyboard())
    await _safe_answer(callback)

def _cloth_from_callback(data: str) -> tuple[str, str] | None:
    # data examples: female_cloth:coat, male_cloth:suit, child_cloth:pants
    try:
        prefix, cloth = data.split(":", 1)
        category = prefix.split("_", 1)[0]  # female / male / child
        return category, cloth
    except Exception:
        return None


def _model_header(index: int, total: int = 31) -> str:
    i = max(1, min(total, index + 1))
    return f"👤 Модель {i} из {total}\n\n" \
           "⚠️ Примерный вид модели и фона.\n" \
           "Может быть изменен в последующем.\n\n" \
           "Используйте кнопки ⬅️ ➡️ для просмотра вариантов\n" \
           "или нажмите ✅ для выбора этой модели."


@router.callback_query(F.data.startswith("female_cloth:") | F.data.startswith("male_cloth:") | F.data.startswith("child_cloth:"))
async def on_any_cloth(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    parsed = _cloth_from_callback(callback.data)
    if not parsed:
        await _safe_answer(callback)
        return
    category, cloth = parsed
    # Сохраним выбранный тип одежды
    await state.update_data(selected_cloth=cloth)
    total = await db.count_models(category, cloth)
    if total <= 0:
        await _safe_answer(callback, "Модели не найдены", show_alert=True)
        return
    text = _model_header(0, total)
    model = await db.get_model_by_index(category, cloth, 0)
    lang = await db.get_user_language(callback.from_user.id)
    if model and model[3]:
        res_msg = await _answer_model_photo(
            callback,
            model[3],
            text,
            model_select_keyboard(category, cloth, 0, total, lang),
        )
        if res_msg and res_msg.photo and not model[3].startswith("AgAC"):
            await db.set_model_photo(model[0], res_msg.photo[-1].file_id)
    else:
        await _replace_with_text(callback, text, reply_markup=model_select_keyboard(category, cloth, 0, total, lang))
    await _safe_answer(callback)


 
@router.message(CreateForm.random_dummy)
async def on_random_age_input(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    if txt.lower() in ("пропустить", "skip"):
        await state.update_data(age="")
    else:
        digits = ''.join(ch for ch in txt if ch.isdigit())
        if not digits:
            await message.answer("Введите возраст числом, например: 25 или нажмите 'Пропустить'")
            return
        await state.update_data(age=f"{digits} лет")
    await state.set_state(CreateForm.waiting_height)
    await message.answer("📏 Введите рост модели в см (например: 170):")

@router.callback_query(F.data == "rand_age:skip")
async def on_random_age_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(age="")
    await _replace_with_text(callback, "📏 Введите рост модели в см (например: 170):")
    await state.set_state(CreateForm.waiting_height)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_custom_location)
async def on_random_location_custom_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст пуст. Введите локацию (до 100 символов):")
        return
    if len(text) > 100:
        await message.answer("Слишком длинно. Сократите до 100 символов.")
        return
    await state.update_data(rand_location="custom", rand_location_custom=text)
    await message.answer("Выберите вайб:", reply_markup=random_vibe_keyboard())


@router.callback_query(F.data.startswith("model_pick:"))
async def on_model_pick(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    try:
        parts = callback.data.split(":")
        # model_pick:logic_cat:display_cat:cloth:index
        category = parts[1] # logic (e.g. storefront)
        display_cat = parts[2] # actual db cat (e.g. female)
        cloth = parts[3]
        index = int(parts[4])
    except Exception:
        await _safe_answer(callback)
        return
        
    total = await db.count_models(display_cat, cloth)
    if total <= 0:
        await _safe_answer(callback, "Модели отсутствуют", show_alert=True)
        return
        
    model = await db.get_model_by_index(display_cat, cloth, index)
    if not model:
        await _safe_answer(callback, "Модель не найдена", show_alert=True)
        return
        
    model_id, name, prompt_id, _photo = model
    # Сохраняем данные
    await state.update_data(
        category=category, 
        display_category=display_cat, 
        cloth=cloth, 
        index=index, 
        model_id=model_id, 
        prompt_id=prompt_id
    )
    # Отмечаем шаг выбора модели как выполненный, чтобы не зациклиться
    await state.update_data(model_select=model_id, model_select_label=name)
    
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    # Витринное фото (НОВЫЙ ФЛОУ)
    if category == "storefront" or data.get("storefront_mode"):
        await state.update_data(current_step_index=0)
        await _show_next_step(callback, state, db)
        await _safe_answer(callback)
        return

    # Готовые пресеты (НОВЫЙ ФЛОУ - как в Свой вариант модели)
    if category == "presets" or data.get("is_preset"):
        # Сохраняем модель как референс (Фото 1)
        model_photo = _photo or model[3]
        await state.update_data(own_ref_photo_id=model_photo)
        
        # Сбрасываем старые фото товара и ID, чтобы юзер загрузил новое
        await state.update_data(user_photo_id=None, photo=None, photos=[])
        
        # Переходим к динамическим шагам (длина, рукав и т.д.)
        await state.update_data(current_step_index=0)
        await _show_next_step(callback, state, db)
        await _safe_answer(callback)
        return

    # 1. Возраст (для обычных пресетов)
    if category in ("female", "male"):
        await _replace_with_text(callback, "🎂 Введите возраст модели числом:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_dynamic_step)
        await state.update_data(current_step_key="age")
    else:
        # Для детей пропускаем возраст, сразу к телосложению
        await _replace_with_text(callback, "📏 Введите размер одежды или телосложение числом:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_dynamic_step)
        await state.update_data(current_step_key="size")
        
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_pants_style, F.data.startswith("pants_style:"))
@router.callback_query(CreateForm.waiting_own_cut, F.data.startswith("pants_style:"))
async def on_pants_style(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    style = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    
    if data.get("own_mode"):
        # Для own_mode сохраняем в own_cut и переходим к рукаву
        cut_map = {
            "fitted": "Приталенный",
            "straight": "Прямой",
            "oversize": "Оверсайз",
            "a_line": "А-силуэт",
            "skip": "",
        }
        await state.update_data(own_cut=cut_map.get(style, ""))
        await state.set_state(CreateForm.waiting_own_sleeve)
        await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))
        await _safe_answer(callback)
        return
    
    await state.update_data(pants_style=style)
    category = data.get("category")

    # 1. Инфографика одежда
    if data.get("infographic_mode") and category == "infographic_clothing":
        # 12. Тип рукава (п. 4.12)
        await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))
        await state.set_state(CreateForm.waiting_sleeve)
        await _safe_answer(callback)
        return

    # 2. Пресеты (Готовые модели) - ЖЕСТКИЙ ПЕРЕХОД К РУКАВАМ
    if category in ("female", "male", "child") and not data.get("random_mode") and not data.get("infographic_mode"):
        await state.set_state(CreateForm.waiting_sleeve)
        await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))
        await _safe_answer(callback)
        return

    # 3. Остальная логика (Рандом и т.д.)
    if data.get("infographic_mode"):
        await state.set_state(CreateForm.waiting_sleeve)
        await _replace_with_text(callback, "Выберите тип рукава (или пропустите):", reply_markup=sleeve_length_keyboard(lang))
        return

    if data.get("random_mode"):
        # Рандом Одежда: к рукавам (п. 7)
        await state.set_state(CreateForm.waiting_sleeve)
        await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))
    else:
        # Для случаев, не попавших под условия выше
        if data.get("plus_mode"):
            await _replace_with_text(callback, "Выберите локацию:", reply_markup=plus_location_keyboard())
            await state.set_state(CreateForm.plus_loc)
        else:
            await _replace_with_text(callback, "📏 Введите размер одежды или телосложение числом:", reply_markup=back_step_keyboard(lang))
            await state.set_state(CreateForm.waiting_dynamic_step)
            await state.update_data(current_step_key="size")
    
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("plus_loc:"))
async def on_plus_loc(callback: CallbackQuery, state: FSMContext) -> None:
    loc = callback.data.split(":", 1)[1]
    await state.update_data(plus_loc=loc)
    await _replace_with_text(callback, "Выберите время года:", reply_markup=plus_season_keyboard())
    await state.set_state(CreateForm.plus_season)
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("plus_season:"))
async def on_plus_season(callback: CallbackQuery, state: FSMContext) -> None:
    season = callback.data.split(":", 1)[1]
    await state.update_data(plus_season=season)
    await _replace_with_text(callback, "Выберите вайб:", reply_markup=plus_vibe_keyboard())
    await state.set_state(CreateForm.plus_vibe)
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("plus_vibe:"))
async def on_plus_vibe(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    vibe = callback.data.split(":", 1)[1]
    await state.update_data(plus_vibe=vibe)
    
    # Пытаемся запустить динамический флоу
    data = await state.get_data()
    cat_key = data.get("category")
    category_db = await db.get_category_by_key(cat_key)
    if category_db:
        await state.update_data(current_step_index=0)
        await _show_next_step(callback, state, db)
    else:
        # Фолбэк на случай если категории нет в базе
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, "🎂 Введите возраст модели числом:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_dynamic_step)
        await state.update_data(current_step_key="age")
    
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("garment_len:"))
async def on_garment_len_callback(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")
    
    if val == "custom":
        await _replace_with_text(callback, get_string("enter_length_custom", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_length)
        await _safe_answer(callback)
        return

    # Маппинг значений для промпта
    len_map = {
        "short_top": "Короткий топ", "regular_top": "Обычный топ",
        "to_waist": "До талии", "below_waist": "Ниже талии",
        "mid_buttocks": "До середины ягодиц", "mid_thigh": "До середины бедра", 
        "to_knees": "До колен", "below_knees": "Ниже колен", 
        "midi": "Миди", "to_ankles": "До щиколоток", 
        "to_floor": "До пола",
        "skip": ""
    }
    
    length_text = len_map.get(val, "")
    await state.update_data(length=length_text)
    
    # Фолбэк для own_mode или own_variant или storefront или инфографика
    if data.get("own_mode") or category == "own_variant" or category == "storefront" or data.get("infographic_mode"):
        await state.update_data(own_length=length_text)

        if data.get("own_mode"):
            # Для "Свой вариант модели" после длины идет Выбор рукава (п. 8.2)
            await _ask_sleeve_length(callback, state, db)
            await _safe_answer(callback)
            return

        if category == "own_variant":
            # Для "Свой вариант фона" — Длина изделия это ФИНАЛЬНЫЙ шаг опроса — к формату (п. 9.5)
            from bot.keyboards import aspect_ratio_keyboard
            await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
            await state.set_state(CreateForm.waiting_aspect)
            await _safe_answer(callback)
            return

        # Для инфографики ОДЕЖДА: после длины идет ВЫБОР ФОРМАТА (п. 4.17)
        if category == "infographic_clothing":
            from bot.keyboards import aspect_ratio_keyboard
            await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
            await state.set_state(CreateForm.waiting_aspect)
            await _safe_answer(callback)
            return

        # Для других (Витрина, Инфографика прочее) — просим фото товара в конце
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]])
        await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_kb)
        await state.set_state(CreateForm.waiting_view)
        await _safe_answer(callback)
        return

    # Для пресетов и Рандом Одежда: после длины — к позе (п. 9)
    if (category in ("female", "male", "child") or data.get("random_mode")) and not data.get("infographic_mode"):
        await state.set_state(CreateForm.waiting_preset_pose)
        gender = data.get("gender") or data.get("rand_gender") or data.get("info_gender") or data.get("child_gender")
        show_vulgar = (gender not in ("boy", "girl"))
        await _replace_with_text(callback, "Выберите тип позы:", reply_markup=pose_keyboard(lang, show_vulgar=show_vulgar))
        await _safe_answer(callback)
        return

    # Обычный флоу
    cloth = data.get("cloth")
    plus_mode = bool(data.get("plus_mode"))
    
    if data.get("random_mode") or cloth == "dress" or (plus_mode and cloth in ("top", "coat", "suit", "overall", "loungewear")):
        await state.set_state(CreateForm.waiting_sleeve)
        await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))
    elif plus_mode and cloth == "pants":
        await state.set_state(CreateForm.waiting_pants_style)
        await _replace_with_text(callback, "Тип кроя штанов (опционально):", reply_markup=pants_style_keyboard(lang))
    else:
        await state.set_state(CreateForm.waiting_view)
        await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=form_view_keyboard(lang))
    
    await _safe_answer(callback)


@router.message(CreateForm.waiting_length)
async def form_set_length(message: Message, state: FSMContext, db: Database) -> None:
    length = (message.text or "").strip()
    await state.update_data(length=length)
    data = await state.get_data()
    lang = await db.get_user_language(message.from_user.id)
    
    if data.get("own_mode") or data.get("category") == "own_variant" or data.get("infographic_mode"):
        if data.get("infographic_mode"):
            await state.set_state(CreateForm.waiting_aspect)
            await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
            return
            
        await state.update_data(own_length=length)
        await state.set_state(CreateForm.waiting_aspect)
        await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        return


@router.message(CreateForm.waiting_foot)
async def form_set_foot(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.lower() in ("пропустить", "skip"):
        await state.update_data(foot_size="")
    else:
        digits = ''.join(ch for ch in text if (ch.isdigit()))
        if not digits:
            await message.answer("Введите размер ноги числом, например: 31 или отправьте 'Пропустить'")
            return
        await state.update_data(foot_size=digits)
    lang = await db.get_user_language(message.from_user.id)
    await state.set_state(CreateForm.waiting_view)
    await message.answer(get_string("select_camera_dist", lang), reply_markup=form_view_keyboard(lang))


@router.callback_query(CreateForm.waiting_sleeve, F.data.startswith("form_sleeve:"))
async def form_set_sleeve(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")
    
    # Маппинг рукава для текста
    sleeve_map = {
        "short": "Короткий", "three_quarters": "3/4", 
        "long": "Длинный", "extra_long": "Удлиненный",
        "skip": "—"
    }
    sleeve_text = sleeve_map.get(val, val)

    # Для всех режимов "Свой вариант" после рукава переходим к ракурсу или сразу к формату
    if data.get("own_mode") or category == "own_variant":
        await state.update_data(own_sleeve=sleeve_text)
        # Для "Своего варианта" тоже можно спросить ракурс (Близкий/Дальний/Средний)
        await state.set_state(CreateForm.waiting_view)
        await _replace_with_text(callback, "👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard(lang))
        await _safe_answer(callback)
        return

    # Инфографика одежда (п. 11)
    if data.get("infographic_mode") and category == "infographic_clothing":
        await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_angle)
        await _safe_answer(callback)
        return

    # Пресеты (Готовые модели) - ПЕРЕХОД К ДЛИНЕ ИЗДЕЛИЯ
    if category in ("female", "male", "child") and not data.get("random_mode") and not data.get("infographic_mode"):
        await _ask_garment_length(callback, state, db)
        await _safe_answer(callback)
        return

    # Остальная логика (рандом, инфографика прочее и т.д.)
    if data.get("infographic_mode"):
        await state.set_state(CreateForm.waiting_info_angle)
        await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=form_view_keyboard(lang))
        return

    if data.get("random_mode"):
        # Рандом Одежда: к длине изделия (п. 8)
        await _ask_garment_length(callback, state, db)
    else:
        await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=form_view_keyboard(lang))
        await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_view, F.data.startswith("form_view:"))
@router.callback_query(CreateForm.waiting_info_angle, F.data.startswith("form_view:"))
@router.callback_query(CreateForm.waiting_rand_other_angle, F.data.startswith("form_view:"))
async def form_set_view(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    view = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")
    current_state = await state.get_state()

    # Если мы в промежуточном состоянии выбора ракурса (для инфографики)
    if current_state == CreateForm.waiting_info_angle.state:
        await state.update_data(info_angle=view)
        # Далее Ракурс (Дальний/Средний/Близкий) - angle_keyboard
        await _replace_with_text(callback, "Выберите ракурс (Дальний/Средний/Близкий):", reply_markup=angle_keyboard(lang))
        await state.set_state(CreateForm.waiting_preset_dist)
        await _safe_answer(callback)
        return

    # Для "Своего варианта"
    if data.get("own_mode") or category == "own_variant":
        await state.update_data(view=view)
        # Если это первый выбор ракурса в начале флоу
        if current_state == CreateForm.waiting_view.state and not data.get("own_product_photo_id"):
            if category == "own_variant":
                await _replace_with_text(callback, get_string("upload_bg_photo", lang), reply_markup=back_step_keyboard(lang))
                await state.set_state(CreateForm.waiting_own_bg_photo)
            else:
                await _replace_with_text(callback, get_string("upload_model_photo", lang), reply_markup=back_step_keyboard(lang))
                await state.set_state(CreateForm.waiting_ref_photo)
            await _safe_answer(callback)
            return
        
        # Если это финальный выбор ракурса после всех фото
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)
        await _safe_answer(callback)
        return

    # Рандом для прочих товаров
    if current_state == CreateForm.waiting_rand_other_angle.state:
        await state.update_data(view=view)
        # Далее дистанция
        await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=camera_distance_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_dist)
        await _safe_answer(callback)
        return

    # Стандартная логика: сохраняем ракурс и возвращаемся в флоу
    await state.update_data(view=view)
    await _show_next_step(callback, state, db)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_preset_pose, F.data.startswith("pose:"))
async def on_preset_pose(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    pose = callback.data.split(":", 1)[1]
    pose_map = {"vulgar": "Вульгарная", "unusual": "Нестандартная", "normal": "Обычная"}
    await state.update_data(pose=pose_map.get(pose, pose))
    lang = await db.get_user_language(callback.from_user.id)
    
    # 9. Ракурс (Дальний - Средний - Близкий - Пропустить)
    await state.set_state(CreateForm.waiting_preset_dist)
    await _replace_with_text(callback, "Выберите ракурс фотографии:", reply_markup=angle_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("form_view:"), CreateForm.waiting_preset_view)
async def on_preset_view(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    view = callback.data.split(":", 1)[1]
    await state.update_data(view=view)
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    # После вида (Спереди/Сзади) -> Сезон
    await state.set_state(CreateForm.waiting_preset_season)
    from bot.keyboards import random_season_keyboard
    await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_preset_dist, F.data.startswith("form_dist:") | F.data.startswith("angle:"))
@router.callback_query(CreateForm.waiting_view, F.data.startswith("form_dist:") | F.data.startswith("angle:"))
@router.callback_query(CreateForm.waiting_rand_other_dist, F.data.startswith("form_dist:") | F.data.startswith("angle:"))
async def on_dist_selected(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    dist_map = {"far": "Дальний", "medium": "Средний", "close": "Близкий", "skip": ""}
    dist_val = dist_map.get(val, val)
    
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")
    current_state = await state.get_state()

    # Инфографика (waiting_view или waiting_preset_dist + infographic_mode)
    if data.get("infographic_mode"):
        await state.update_data(info_dist=dist_val)
        
        # Для всей инфографики (и одежда, и прочее): Поза (если есть человек)
        if data.get("has_person"):
            from bot.keyboards import pose_keyboard
            gender = data.get("gender") or data.get("rand_gender") or data.get("info_gender") or data.get("child_gender")
            show_vulgar = (gender not in ("boy", "girl"))
            await _replace_with_text(callback, "Выберите позу модели:", reply_markup=pose_keyboard(lang, show_vulgar=show_vulgar))
            await state.set_state(CreateForm.waiting_info_pose)
        else:
            # Если нет человека:
            if category == "infographic_other":
                from bot.keyboards import random_season_keyboard
                await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
                await state.set_state(CreateForm.waiting_info_season)
            else:
                # Для одежды без человека (редко, но все же) -> Длина
                await _ask_garment_length(callback, state, db)
        await _safe_answer(callback)
        return

    # Рандом для остальных товаров
    if data.get("random_other_mode"):
        await state.update_data(dist=dist_val)
        await _replace_with_text(callback, get_string("enter_height_cm", lang), reply_markup=skip_step_keyboard("rand_height", lang))
        await state.set_state(CreateForm.waiting_rand_other_height)
        await _safe_answer(callback)
        return

    # Остальные (Рандом, Пресеты, Витрина и т.д.)
    await state.update_data(dist=dist_val)
    
    # Витринное фото
    if data.get("category") == "storefront":
        await _ask_garment_length(callback, state, db)
        await _safe_answer(callback)
        return

    # Рандом Одежда и Обувь или Готовые пресеты -> Вид (Спереди/Сзади)
    await state.set_state(CreateForm.waiting_preset_view)
    await _replace_with_text(callback, "Выберите вид фотографии (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_preset_view, F.data.startswith("form_view:"))
async def on_preset_view(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    view = callback.data.split(":", 1)[1]
    view_map = {"front": "Спереди", "back": "Сзади"}
    await state.update_data(view=view_map.get(view, view))
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    # Витринное фото (п. 4)
    if data.get("category") == "storefront":
        from bot.keyboards import angle_keyboard
        await _replace_with_text(callback, "Выберите ракурс фотографии (Дальний/Средний/Близкий):", reply_markup=angle_keyboard(lang))
        await state.set_state(CreateForm.waiting_preset_dist)
        await _safe_answer(callback)
        return

    # 11. Сезон
    await state.set_state(CreateForm.waiting_preset_season)
    await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_preset_season, F.data.startswith("rand_season:") | F.data.startswith("season:"))
async def on_preset_season(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    season = callback.data.split(":")[1]
    season_map = {"summer": "Лето", "winter": "Зима", "autumn": "Осень", "spring": "Весна", "skip": ""}
    await state.update_data(season=season_map.get(season, season))
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    # Для всех категорий (Пресеты и Рандом) переходим к выбору праздника
    from bot.keyboards import random_holiday_keyboard
    await _replace_with_text(callback, "Выберите праздник (если есть):", reply_markup=random_holiday_keyboard(lang))
    await state.set_state(CreateForm.waiting_preset_holiday)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_preset_holiday, F.data.startswith("rand_holiday:") | F.data.startswith("holiday:"))
async def on_preset_holiday(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    holiday_map = {
        "wedding": "Свадьба", "bday": "День рождения", "may9": "9 мая",
        "newyear": "Новый год", "christmas": "Рождество", "feb23": "23 февраля",
        "march8": "8 марта", "sale": "Распродажа", "skip": ""
    }
    await state.update_data(holiday=holiday_map.get(val, val))
    lang = await db.get_user_language(callback.from_user.id)
    
    # Праздник — финальный шаг. Теперь просим фото (п. 1.1)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]])
    await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_kb)
    await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_info_pose, F.data.startswith("pose:"))
async def on_info_pose(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    pose = callback.data.split(":", 1)[1]
    pose_map = {"vulgar": "Вульгарная", "unusual": "Нестандартная", "normal": "Обычная"}
    await state.update_data(info_pose=pose_map.get(pose, pose))
    
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")
    
    if data.get("infographic_mode"):
        if category == "infographic_clothing":
            # Для инфографики одежда: после позы — к длине изделия (п. 14)
            await _ask_garment_length(callback, state, db)
        else: # infographic_other
            # Для инфографики прочее: после позы — к сезону
            from bot.keyboards import random_season_keyboard
            await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
            await state.set_state(CreateForm.waiting_info_season)
        await _safe_answer(callback)
        return
    elif category in ("female", "male", "child") and not data.get("random_mode") and not data.get("infographic_mode"):
        # Для пресетов: после позы — к ракурсу (п. 9)
        await state.set_state(CreateForm.waiting_preset_dist)
        await _replace_with_text(callback, "Выберите ракурс фотографии:", reply_markup=angle_keyboard(lang))
    elif data.get("random_other_mode"):
        # Для Рандом прочее: после позы — к росту (п. 8)
        await _replace_with_text(callback, get_string("enter_height_cm", lang), reply_markup=skip_step_keyboard("rand_height", lang))
        await state.set_state(CreateForm.waiting_rand_other_height)
    else:
        # Стандарт
        await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)



from collections import defaultdict

# Словар замков для каждого пользователя, чтобы избежать race condition
user_locks = defaultdict(asyncio.Lock)
# Замки для генерации (чтобы не запускать две параллельно)
gen_locks = defaultdict(asyncio.Lock)
# Кэш обработанных сообщений, чтобы не считать одно фото дважды (race condition на стороне TG)
processed_msg_ids = set()

@router.message(CreateForm.waiting_view, F.photo)
async def handle_user_photo(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.from_user.id
    msg_id = message.message_id
    
    # 1. Быстрая проверка на дубликат сообщения (вне лока для скорости)
    if msg_id in processed_msg_ids:
        return
    
    # Используем индивидуальный замок для каждого пользователя
    async with user_locks[user_id]:
        # Повторная проверка внутри замка
        if msg_id in processed_msg_ids:
            return
        processed_msg_ids.add(msg_id)
        # Очищаем старые ID (держим последние 100)
        if len(processed_msg_ids) > 100:
            list(processed_msg_ids)[:50] 

        # Даем микро-паузу для MemoryStorage (aiogram 3 sync)
        await asyncio.sleep(0.05)
        
        data = await state.get_data()
        current_state = await state.get_state()
        
        logger.info(f"[handle_user_photo] User {user_id}, State: {current_state}, Photos in data: {len(data.get('photos', [])) if data else 'N/A'}")
        
        if not data or current_state != CreateForm.waiting_view.state:
            return

        photo_id = message.photo[-1].file_id
        lang = await db.get_user_language(user_id)
        category = data.get("category")

        # --- ОБЫЧНАЯ ГЕНЕРАЦИЯ ---
        if data.get("normal_gen_mode"):
            photos = data.get("photos") or []
            
            # Добавляем фото, если его еще нет в списке
            if photo_id not in photos:
                photos.append(photo_id)
                photos = photos[:4]
                # ВАЖНО: Сначала обновляем данные в state
                await state.update_data(photos=photos)
                # И сразу же обновляем локальную переменную data для консистентности
                data["photos"] = photos
            
            # Формируем клавиатуру и текст
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Далее" if len(photos) < 4 else "Перейти к промпту", callback_data="normal_photos_done")],
                [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]
            ])

            if len(photos) < 4:
                text = f"📸 Фото {len(photos)}/4 получено.\n\nВы можете отправить еще до {4 - len(photos)} фото или нажмите «Далее», чтобы продолжить."
            else:
                text = "✅ Получено 4/4 фото. Теперь нажмите «Далее», чтобы отправить промпт."
                await state.set_state(CreateForm.waiting_prompt)

            # Пытаемся редактировать старое сообщение счетчика
            last_msg_id = data.get("last_photos_msg_id")
            if last_msg_id:
                try:
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=last_msg_id,
                        text=text,
                        reply_markup=kb
                    )
                    return 
                except Exception as e:
                    logger.debug(f"Could not edit counter message: {e}")

            # Отправляем новое, если не удалось редактировать
            msg = await message.answer(text, reply_markup=kb)
            await state.update_data(last_photos_msg_id=msg.message_id)
            return

        # --- ОСТАЛЬНЫЕ РЕЖИМЫ (Свой вариант и т.д.) ---
        # Определяем, в какой ключ сохранять фото (в зависимости от категории)
        photo_key = "user_photo_id"
        if category in ("own", "own_variant") or data.get("own_mode"):
            photo_key = "own_product_photo_id"
            
        await state.update_data({photo_key: photo_id})
        
        if data.get("repeat_mode"):
            await state.update_data(repeat_mode=False)
            await _do_generate(message, state, db)
            return  # ВАЖНО: останавливаем выполнение хендлера здесь
        elif category == "infographic_clothing":
            dummy_callback = CallbackQuery(
                id="0", from_user=message.from_user, chat_instance="0",
                message=message, data=f"form_aspect:{data.get('aspect', '1:1')}"
            ).as_(message.bot)
            await on_aspect_selected(dummy_callback, state, db)
            return
        elif data.get("random_other_mode"):
            await _show_confirmation(message, state, db)
            return
        else:
            await _show_next_step(message, state, db)
            return

    # Обработка завершена внутри лока
    return


@router.callback_query(F.data == "back_step")
async def on_back_step(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    current_state = await state.get_state()
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")
    
    if not current_state:
        await on_back_main(callback, state, db)
        return

    # --- Рандом прочее (нединамические состояния) ---
    if data.get("random_other_mode"):
        from bot.keyboards import yes_no_keyboard, skip_step_keyboard, infographic_gender_keyboard, form_view_keyboard, camera_dist_keyboard, random_season_keyboard, style_keyboard
        if current_state == CreateForm.waiting_rand_other_has_person.state:
            await on_marketplace_menu(callback, db)
            await state.clear()
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_rand_other_gender.state:
            await _replace_with_text(callback, get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))
            await state.set_state(CreateForm.waiting_rand_other_has_person)
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_info_load.state:
            if data.get("has_person"):
                await state.set_state(CreateForm.waiting_rand_other_gender)
                await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang))
            else:
                await state.set_state(CreateForm.waiting_rand_other_has_person)
                await _replace_with_text(callback, get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_rand_other_name.state:
            await state.set_state(CreateForm.waiting_info_load)
            await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=skip_step_keyboard("info_load", lang))
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_rand_other_angle.state:
            await _replace_with_text(callback, get_string("enter_product_name", lang), reply_markup=skip_step_keyboard("rand_name", lang))
            await state.set_state(CreateForm.waiting_rand_other_name)
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_rand_other_dist.state:
            await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
            await state.set_state(CreateForm.waiting_rand_other_angle)
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_rand_other_height.state:
            await _replace_with_text(callback, "Выберите ракурс фотографии (Дальний/Средний/Близкий):", reply_markup=camera_dist_keyboard(lang))
            await state.set_state(CreateForm.waiting_rand_other_dist)
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_rand_other_width.state:
            await _replace_with_text(callback, "Введите высоту (см):", reply_markup=skip_step_keyboard("rand_height", lang))
            await state.set_state(CreateForm.waiting_rand_other_height)
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_rand_other_length.state:
            await _replace_with_text(callback, "Введите ширину (см):", reply_markup=skip_step_keyboard("rand_width", lang))
            await state.set_state(CreateForm.waiting_rand_other_width)
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_rand_other_season.state:
            await _replace_with_text(callback, "Введите длину (см):", reply_markup=skip_step_keyboard("rand_length", lang))
            await state.set_state(CreateForm.waiting_rand_other_length)
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_rand_other_style.state:
            await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
            await state.set_state(CreateForm.waiting_rand_other_season)
            await _safe_answer(callback)
            return
        elif current_state == CreateForm.waiting_view.state:
             await _replace_with_text(callback, get_string("select_style", lang), reply_markup=style_keyboard(lang))
             await state.set_state(CreateForm.waiting_rand_other_style)
             await _safe_answer(callback)
             return

    # --- Поддержка динамических шагов ---
    current_index = data.get("current_step_index")
    if current_index is not None:
        # [FIX] Устанавливаем флаг возврата назад
        await state.update_data(is_going_back=True)
        
        # Если мы на вводе "Своего варианта" — возвращаемся к исходному вопросу
        waiting_custom_for = data.get("waiting_custom_for")
        if waiting_custom_for:
            cat_db = await db.get_category_by_key(category)
            if cat_db:
                steps = await db.list_steps(cat_db[0])
                for idx, step in enumerate(steps):
                    if step[1] == waiting_custom_for:
                        await state.update_data(waiting_custom_for=None, current_step_index=idx)
                        await _show_next_step(callback, state, db)
                        await _safe_answer(callback)
                        return
        if current_index > 0:
            # Возвращаемся к предыдущему динамическому шагу, пропуская уже заполненные/пропущенные
            new_index = current_index - 1
            
            # Получаем список шагов для проверки условий пропуска в обратном порядке
            cat_db = await db.get_category_by_key(category)
            if cat_db:
                steps = await db.list_steps(cat_db[0])
                if not steps:
                    await _show_main_menu_by_obj(callback, db)
                    await _safe_answer(callback)
                    return
                if new_index >= len(steps):
                    new_index = len(steps) - 1
                while new_index >= 0:
                    step = steps[new_index]
                    s_key = step[1]
                    gender = data.get("gender") or data.get("rand_gender") or data.get("info_gender") or data.get("child_gender")
                    
                    should_skip = False
                    # 1. Возраст для детей
                    if s_key == "age" and gender in ("boy", "girl"):
                        should_skip = True
                    # 2. Ключи пола, если они уже в данных (обычно это первый шаг)
                    elif s_key in ("gender", "rand_gender", "info_gender", "child_gender") and data.get(s_key):
                        # Но если это единственный шаг или мы в самом начале, не скипаем его совсем
                        if new_index > 0:
                            should_skip = True
                    
                    # 3. Условия по локациям
                    loc_group = data.get("rand_loc_group")
                    if loc_group:
                        if loc_group == "indoor" and s_key == "rand_location_outdoor":
                            should_skip = True
                        elif loc_group == "outdoor" and s_key == "rand_location_indoor":
                            should_skip = True
                        elif loc_group == "indoor" and "season" in s_key.lower():
                            should_skip = True

                    # 4. Отсутствие человека
                    person_absent = False
                    for k, v in data.items():
                        if k.endswith("_label") and any(x in str(v).lower() for x in ("без человека", "without person", "нет", "no")):
                            if any(x in k.lower() for x in ("person", "presence", "человек", "присутствие")):
                                person_absent = True; break
                        if isinstance(v, str) and v.lower() in ("person_no", "without_person", "no_person", "no", "нет"):
                            if any(x in k.lower() for x in ("person", "presence", "человек", "присутствие")):
                                person_absent = True; break
                    
                    if person_absent:
                        low_s_key = s_key.lower()
                        if any(x in low_s_key for x in ("age", "pose", "height", "size", "возраст", "поза", "рост", "телосложение")):
                            # Для рандом прочее рост может быть важен, но в целом следуем логике _show_next_step
                            if category not in ("random_other", "infographic_other") or not any(x in low_s_key for x in ("height", "рост")):
                                should_skip = True
                        
                    if should_skip:
                        new_index -= 1
                        continue
                    break
            
            if new_index < 0:
                # Если это пресеты — возвращаемся к выбору моделей
                if data.get("is_preset") and data.get("gender"):
                    await _show_models_for_category(
                        callback, db, 
                        category=data.get("gender"), 
                        cloth=data.get("cloth", "all"), 
                        index=data.get("index", 0), 
                        logic_category="presets"
                    )
                    await _safe_answer(callback)
                    return
                    
                await on_marketplace_menu(callback, db)
                await state.clear()
                await _safe_answer(callback)
                return
                
            # Очищаем значение шага, к которому возвращаемся, чтобы _show_next_step не пропустил его
            # Очищаем значение шага, к которому возвращаемся, чтобы _show_next_step не пропустил его
            if cat_db:
                target_step_key = steps[new_index][1]
                await state.update_data({target_step_key: None})
                
            await state.update_data(current_step_index=new_index)
            await _show_next_step(callback, state, db)
            await _safe_answer(callback)
            return
        else:
            # Мы в начале динамического флоу — возвращаемся в меню или к выбору моделей
            if data.get("is_preset") and data.get("gender"):
                await _show_models_for_category(
                    callback, db, 
                    category=data.get("gender"), 
                    cloth=data.get("cloth", "all"), 
                    index=data.get("index", 0), 
                    logic_category="presets"
                )
                await _safe_answer(callback)
                return
                
            await on_marketplace_menu(callback, db)
            await state.clear()
            await _safe_answer(callback)
            return

    # --- Старая логика (минимальный фолбэк для не-динамических состояний) ---
    if current_state == CreateForm.waiting_prompt.state:
        if data.get("normal_gen_mode"):
            photos = data.get("photos") or []
            if len(photos) > 0:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Далее" if len(photos) < 4 else "Перейти к промпту", callback_data="normal_photos_done")],
                    [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]
                ])
                text = f"📸 Фото {len(photos)}/4 получено.\n\nВы можете отправить еще до {4 - len(photos)} фото или нажмите «Далее», чтобы продолжить."
            else:
                from bot.keyboards import back_main_keyboard
                kb = back_main_keyboard(lang)
                text = "📸 Пришлите до 4 фото (можно по одному или серией)."
            
            await _replace_with_text(callback, text, reply_markup=kb)
            await state.set_state(CreateForm.waiting_view)
            await _safe_answer(callback)
            return

        await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_main_keyboard(lang))
        await state.set_state(CreateForm.waiting_view)
        await _safe_answer(callback)
        return

    if current_state == CreateForm.waiting_edit_text.state:
        await state.set_state(CreateForm.result_ready)
        kb = result_actions_own_keyboard(lang) if (data.get("own_mode") or category == "own_variant") else result_actions_keyboard(lang)
        await _replace_with_text(callback, get_string("gen_ready", lang), reply_markup=kb)
        await _safe_answer(callback)
        return

    # Если ничего не подошло — в главное меню
    await on_marketplace_menu(callback, db)
    await state.clear()
    await _safe_answer(callback)
    return
@router.callback_query(CreateForm.waiting_info_season, F.data.startswith("season:") | F.data.startswith("rand_season:"))
async def on_info_season(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    season = callback.data.split(":")[1]
    season_map = {"summer": "Лето", "winter": "Зима", "autumn": "Осень", "spring": "Весна", "skip": ""}
    await state.update_data(info_season=season_map.get(season, season))
    lang = await db.get_user_language(callback.from_user.id)
    # Далее Праздник
    from bot.keyboards import random_holiday_keyboard
    await _replace_with_text(callback, "Выберите праздник (если есть):", reply_markup=random_holiday_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_holiday)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_info_holiday, F.data.startswith("holiday:") | F.data.startswith("rand_holiday:"))
async def on_info_holiday(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    holiday = callback.data.split(":")[1]
    holiday_map = {
        "wedding": "Свадьба", "bday": "День рождения", "may9": "9 мая",
        "newyear": "Новый год", "christmas": "Рождество", "feb23": "23 февраля",
        "march8": "8 марта", "sale": "Распродажа", "skip": ""
    }
    await state.update_data(info_holiday=holiday_map.get(holiday, holiday))
    lang = await db.get_user_language(callback.from_user.id)
    
    # Теперь для инфографики (прочее) — просим фото в конце
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]])
    await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_kb)
    await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)


async def _build_final_prompt(data: dict, db: Database) -> str:
    category = data.get("category")

    # Маппинг категорий на ключи промптов в app_settings
    category_prompt_map = {
        "storefront": "storefront_prompt",
        "whitebg": "whitebg_prompt",
        "own_variant": "own_variant_prompt",
        "random": "random_prompt",
        "random_other": "random_other_prompt",
        "infographic_clothing": "infographic_clothing_prompt",
        "infographic_other": "infographic_other_prompt",
        "own": "own_prompt",
    }

    prompt_text = ""
    if data.get("random_mode"):
        # Для random_mode промпт формируется ниже в более сложной логике
        prompt_text = ""
    elif category in ("female", "male", "child", "boy", "girl", "presets", "own") and data.get('prompt_id'):
        # Для категорий с моделями - берем промпт модели, затем добавляем общий промпт категории если есть
        pid = data.get('prompt_id')
        model_prompt = await db.get_prompt_text(int(pid)) if pid else ""
        prompt_text = model_prompt
        
        # Добавляем общий промпт категории если есть
        if category == "presets":
            presets_base = await db.get_app_setting("presets_prompt") or ""
            if presets_base:
                prompt_text += "\n\n" + presets_base
        elif category == "own":
            own_base = await db.get_app_setting("own_prompt") or ""
            if own_base:
                prompt_text += "\n\n" + own_base
    elif category in category_prompt_map:
        # Для остальных категорий - используем промпт из app_settings
        prompt_key = category_prompt_map[category]
        prompt_text = await db.get_app_setting(prompt_key) or ""
    else:
        # Fallback - промпт модели если есть
        pid = data.get('prompt_id')
        prompt_text = await db.get_prompt_text(int(pid)) if pid else ""
    
    age_key = data.get('age')
    age_map = {
        "20_26": "Молодая модель возраста 20-26 лет",
        "30_38": "Взрослая модель возраста 30-38 лет",
        "40_48": "Зрелая модель возраста 40-48 лет",
        "55_60": "Пожилая модель возраста 55-60 лет",
    }
    age_text = age_map.get(age_key, age_key or "")
    sleeve_text = data.get('sleeve') or ""
    size_text = data.get('size') or ""
    # Улучшаем описание размера для ИИ
    if size_text and str(size_text).isdigit():
        sz = int(size_text)
        size_text = f"size {sz}"
        
    # --- УНИВЕРСАЛЬНАЯ ЗАМЕНА ПЛЕЙСХОЛДЕРОВ ---
    # Собираем все возможные значения для замены
    
    age_key = data.get('age')
    age_map = {
        "20_26": "Молодая модель возраста 20-26 лет",
        "30_38": "Взрослая модель возраста 30-38 лет",
        "40_48": "Зрелая модель возраста 40-48 лет",
        "55_60": "Пожилая модель возраста 55-60 лет",
    }
    age_text = age_map.get(age_key, age_key or "")
    length_raw = str(data.get("length") or data.get("length_cm") or data.get("own_length") or "")
    length_en = ""
    if length_raw:
        len_en_map = {
            "Короткий топ": "short crop top length",
            "Обычный топ": "regular top length",
            "До талии": "waist length",
            "Ниже талии": "below waist length",
            "До середины ягодиц": "mid-buttocks length",
            "До середины бедра": "mid-thigh length",
            "До колен": "knee length",
            "Ниже колен": "below knee length",
            "Миди": "midi length",
            "До щиколоток": "ankle length",
            "До пола": "floor length"
        }
        length_en = len_en_map.get(length_raw, "")
    
    # Если есть английский эквивалент, добавляем его в скобках для Gemini
    length_final = f"{length_raw} ({length_en})" if length_en else length_raw

    view_key = data.get("view") or data.get("info_angle")
    view_word = {"close": "близкий", "far": "дальний", "medium": "средний", "back": "сзади", "front": "спереди", "side": "сбоку"}.get(view_key, "спереди")
    
    dist_key = data.get("dist") or data.get("info_dist")
    dist_word = {"far": "дальний", "medium": "средний", "close": "близкий"}.get(dist_key, "средний")
    
    gender_val = data.get("gender") or data.get("info_gender") or data.get("rand_gender")
    gender_word = {"male": "мужчина", "female": "женщина", "boy": "мальчик", "girl": "девочка", "unisex": "унисекс"}.get(gender_val, "")
    
    replacements = {
        "{размер}": size_text, "{Размер модели}": size_text, "{Размер тела модели}": size_text,
        "(ТУТ УКАЗЫВАЕМ РАЗМЕР МОДЕЛИ)": size_text, "(ТУТ УКАЗЫВАЕМ Размер модели}": size_text,
        
        "{рост}": str(data.get("height") or data.get("height_cm") or ""), 
        "{Рост модели}": str(data.get("height") or data.get("height_cm") or ""),
        "(ТУТ УКАЗЫВАЕМ РОСТ МОДЕЛИ)": str(data.get("height") or data.get("height_cm") or ""),
        "(ТУТ УКАЗЫВАЕМ Рост модели}": str(data.get("height") or data.get("height_cm") or ""),
        
        "{длина изделия}": length_final, 
        "{длину изделия}": length_final,
        "{Длина изделия}": length_final,
        "(ТУТ УКАЗЫВАЕМ ДЛИНУ ИЗДЕЛИЯ)": length_final,
        "(ТУТ УКАЗЫВАЕМ длину изделия}": length_final,
        
        "{возраст}": age_text, "{Возраст модели}": age_text,
        "(ТУТ УКАЗЫВАЕМ ВОЗРАСТ МОДЕЛИ)": age_text, "(ТУТ УКАЗЫВАЕМ Возраст модели}": age_text,
        
        "{длина рукав}": sleeve_text, "{Тип рукава}": sleeve_text, "{длина рукава}": sleeve_text,
        "(ТУТ УКАЗЫВАЕМ ТИП РУКАВОВ": sleeve_text, "(ТУТ УКАЗЫВАЕМ Тип рукава}": sleeve_text,
        
        "{сзади/спереди}": view_word, "{Угол камеры}": view_word, "{Ракурс}": view_word,
        "{Вид фотографии}": view_word,
        "(ТУТ УКАЗЫВАЕМ ВИД ФОТОГРАФИИ СПЕРЕДИ \СЗАДИ)": view_word, "(ТУТ УКАЗЫВАЕМ Угол камеры}": view_word,
        
        "{ракурс фотографии}": dist_word, "{Дистанция}": dist_word,
        "(ТУТ УКАЗЫВАЕМ РАКУРС ФОТОГРАФИИ)": dist_word, "(ТУТ УКАЗЫВАЕМ ракурс фотографии}": dist_word,
        
        "{Пол модели}": gender_word, "{пол}": gender_word, "{Пол}": gender_word,
        "(ТУТ УКАЗЫВАЕМ УКАЗЫВАЕМ ПОЛ)": gender_word, "(ТУТ УКАЗЫВАЕМ ПОВТОРНО ПОЛ МОДЕЛИ)": gender_word,
        "(ТУТ УКАЗЫВАЕМ ПОВТОРНО Пол модели}": gender_word, "(ТУТ УКАЗЫВАЕМ Пол модели)": gender_word,
        "(ТУТ УКАЗЫВАЕМ  УКАЗЫВАЕМ ПОЛ)": gender_word,
        
        "{Название товара}": str(data.get("product_name") or data.get("info_brand") or ""),
        "{brand}": str(data.get("info_brand") or ""),
        "{Название бренда}": str(data.get("info_brand") or ""),
        "{Укажите название брендатовара}": str(data.get("product_name") or data.get("info_brand") or ""),
        "{Укажите название бренда товара}": str(data.get("product_name") or data.get("info_brand") or ""),
        
        "{Нагруженность}": str(data.get("info_load") or ""),
        "{Нагруженность инфографики}": str(data.get("info_load") or ""),
        "(ТУТ УКАЗЫВАЕМ НАГРУЖЕННОСТЬ)": str(data.get("info_load") or ""),
        "(ТУТ УКАЗЫВАЕМ Нагруженность инфографики}": str(data.get("info_load") or ""),
        
        "{Язык}": str(data.get("info_lang") or ""),
        "{Язык инфографики}": str(data.get("info_lang") or ""),
        "(ТУТ УКАЗЫВАЕМ ЯЗЫК ИНФОГРАФИКИ)": str(data.get("info_lang") or ""),
        
        "{Формат фото}": str(data.get("aspect") or data.get("aspect_label") or ""),
        "{Фото фона}": "AgAC..." if data.get("own_bg_photo_id") else "",
        
        "{Стиль}": str(data.get("style") or ""),
        "{Стиль локации}": str(data.get("style") or ""),
        "(ТУТ УКАЗЫВАЕМ СТИЛЬ)": str(data.get("style") or ""),
        
        "{Сезон}": str(data.get("season") or data.get("info_season") or ""),
        "(ТУТ УКАЗЫВАЕМ СЕЗОН)": str(data.get("season") or data.get("info_season") or ""),
        "(ТУТ УКАЗЫВАЕМ Сезон}": str(data.get("season") or data.get("info_season") or ""),
        
        "{Праздник}": str(data.get("holiday") or data.get("info_holiday") or ""),
        "(ТУТ УКАЗЫВАЕМ Праздник}": str(data.get("holiday") or data.get("info_holiday") or ""),
        
        "{Поза}": str(data.get("pose") or data.get("info_pose") or ""),
        "{Поза модели}": str(data.get("pose") or data.get("info_pose") or ""),
        "(ТУТ УКАЗЫВАЕМ ПОЗУ МОДЕЛИ)": str(data.get("pose") or data.get("info_pose") or ""),
        "(ТУТ УКАЗЫВАЕМ Поза модели}": str(data.get("pose") or data.get("info_pose") or ""),
        
        "{Тип кроя}": str(data.get("pants_style") or ""),
        "{Тип кроя штанов}": str(data.get("pants_style") or ""),
        "(ТУТ УКАЗЫВАЕМ ТИП КРОЯ ШТАНОВ)": str(data.get("pants_style") or ""),
        "(ТУТ УКАЗЫВАЕМ Тип кроя штанов}": str(data.get("pants_style") or ""),
        
        "{Ширина}": str(data.get("width_cm") or ""),
        "(ТУТ УКАЗЫВАЕМ ШИРИНУ)": str(data.get("width_cm") or ""),
        
        "{Высота}": str(data.get("height_cm") or ""),
        "(ТУТ УКАЗЫВАЕМ ВЫСОТУ)": str(data.get("height_cm") or ""),
        
        "{Длина}": str(data.get("length_cm") or ""),
        "(ТУТ УКАЗЫВАЕМ ДЛИНУ)": str(data.get("length_cm") or ""),
        
        "{Человек}": "Yes" if str(data.get("has_person")).lower() == "yes" else "No",
        "{Присутствует ли человек на фото}": "Yes" if str(data.get("has_person")).lower() == "yes" else "No",
        "(ТУТ УКАЗЫВАЕМ Присутствует ли человек на фото)": "Yes" if str(data.get("has_person")).lower() == "yes" else "No",
        
        "{Тип локации}": str(data.get("rand_location") or data.get("rand_location_indoor") or data.get("rand_location_outdoor") or ""),
        "(ТУТ УКАЗЫВАЕМ Тип локации}": str(data.get("rand_location") or data.get("rand_location_indoor") or data.get("rand_location_outdoor") or ""),
    }
    
    # Добавляем преимущества для инфографики
    advs = [data.get("info_adv1"), data.get("info_adv2"), data.get("info_adv3")]
    replacements["{Преимущества}"] = ", ".join([a for a in advs if a])
    replacements["{Преимущество 1}"] = str(data.get("info_adv1") or "")
    replacements["{Преимущество 2}"] = str(data.get("info_adv2") or "")
    replacements["{Преимущество 3}"] = str(data.get("info_adv3") or "")
    replacements["{Топ 1 преимущества товара}"] = str(data.get("info_adv1") or "")
    replacements["{Топ 2 преимущества товара}"] = str(data.get("info_adv2") or "")
    replacements["{Топ 3 преимущества товара}"] = str(data.get("info_adv3") or "")
    replacements["(ТУТ УКАЗЫВАЕМ ПРИМУЩЕСТВО 1)"] = str(data.get("info_adv1") or "")
    replacements["(ТУТ УКАЗЫВАЕМ ПРИМУЩЕСТВО 2)"] = str(data.get("info_adv2") or "")
    replacements["(ТУТ УКАЗЫВАЕМ ПРИМУЩЕСТВО 3)"] = str(data.get("info_adv3") or "")
    replacements["{Доп информация}"] = str(data.get("info_extra") or "")
    replacements["{Дополнительная информация о продукте}"] = str(data.get("info_extra") or "")
    replacements["(ТУТ УКАЗЫВАЕМ ДОП ЧТО УГОДНО О ТОВАРЕ)"] = str(data.get("info_extra") or "")

    def apply_replacements(text: str) -> str:
        if not text: return ""
        res = text
        # Сначала заменяем длинные ключи, потом короткие, чтобы избежать частичных замен
        sorted_keys = sorted(replacements.keys(), key=len, reverse=True)
        for k in sorted_keys:
            v = replacements[k]
            # Регистронезависимая замена для плейсхолдеров в фигурных скобках
            if k.startswith("{") and k.endswith("}"):
                import re
                res = re.sub(re.escape(k), str(v), res, flags=re.IGNORECASE)
            else:
                res = res.replace(k, str(v))
        return res

    # Проверяем, какие параметры были использованы в промпте, чтобы не дублировать их в конце
    used_placeholders = set()
    for k in replacements.keys():
        # Мы проверяем и prompt_text (базовый из БД) и prompt_filled (если он уже частично сформирован)
        pass # Логика ниже

    prompt_filled = ""
    strict_admin_prompt_mode = False
    if data.get("own_mode") or category == "own":
        # Для own ПРИОРИТЕТ — текст из админки (app_settings.own_prompt).
        # Дефолт используем только если в админке и fallback-источниках пусто.
        own_from_admin = (await db.get_app_setting("own_prompt") or "").strip()
        base = own_from_admin or (await db.get_own_prompt() or "") or (await db.get_own_prompt3() or "")
        if not base.strip():
            base = """STRICT FASHION REDRESS TASK:
Generate ONE SINGLE IMAGE. NO COLLAGES. NO SIDE-BY-SIDE. NO REPETITION.

INPUT DATA:
1. [SCENE_AND_MODEL_REFERENCE_IMAGE]: The model, face, pose, and background.
2. [CLOTHING_ITEM_TO_WEAR_IMAGE]: The NEW item to put on the model.

CORE RULES:
- IDENTITY: Keep the EXACT face and body of the person from [SCENE_AND_MODEL_REFERENCE_IMAGE].
- POSE: Keep the EXACT pose from [SCENE_AND_MODEL_REFERENCE_IMAGE].
- BACKGROUND: Keep the EXACT environment from [SCENE_AND_MODEL_REFERENCE_IMAGE].
- TOTAL OUTFIT OVERHAUL: You MUST DISCARD ALL clothing items (tops, bottoms, shoes, accessories) from [SCENE_AND_MODEL_REFERENCE_IMAGE]. 
- NEW STYLING: Put the item from [CLOTHING_ITEM_TO_WEAR_IMAGE] on the person. 
- COMPLETE THE LOOK: If [CLOTHING_ITEM_TO_WEAR_IMAGE] is only a top, you MUST generate NEW matching pants/skirt and shoes that perfectly fit the style of the new item. 
- STYLISH OUTFIT: Avoid making the entire outfit monochromatic or the same color as the new item. Use complementary colors, different materials, and stylish textures for the pants and shoes to create a professional fashion-forward look. DO NOT reuse the pants from the original photo.
- FIDELITY: The new item must look 100% identical to [CLOTHING_ITEM_TO_WEAR_IMAGE] in texture and silhouette.
- HIGH-END QUALITY: The new product must look perfectly ironed, clean, and brand new. Sharp focus on fabric details, textures, and professional cinematic lighting.

FORMAT:
- Aspect Ratio: {aspect}
- Requirement: Fill the frame. ZERO BORDERS.

🎯 TARGET: A high-end, luxury marketplace photo where the model from [SCENE_AND_MODEL_REFERENCE_IMAGE] is wearing a COMPLETELY NEW OUTFIT with superior commercial quality."""
            logger.info("[PROMPT] own: default fallback used (admin prompt is empty)")
        else:
            logger.info("[PROMPT] own: using %s prompt, length=%d", "admin" if own_from_admin else "fallback-db", len(base))
        prompt_filled = apply_replacements(base)
        
    elif category == "own_variant":
        # Для own_variant ПРИОРИТЕТ — текст из админки (app_settings.own_variant_prompt).
        # Дефолт используем только если в админке и fallback-источниках пусто.
        own_variant_from_admin = (await db.get_app_setting("own_variant_prompt") or "").strip()
        base = own_variant_from_admin or (await db.get_own_variant_prompt() or "")
        if not base.strip():
            base = """STRICT PRODUCT-IN-SCENE RECONSTRUCTION:
Place the product from [CLOTHING_ITEM_TO_WEAR_IMAGE] into the exact scene from [SCENE_AND_MODEL_REFERENCE_IMAGE].

CORE RULES:
- PRODUCT FIDELITY: The product from [CLOTHING_ITEM_TO_WEAR_IMAGE] is the ONLY source. Reproduce its color, texture, and silhouette with 100% accuracy.
- SCENE PRESERVATION: Keep the EXACT background, props (hangers, hooks, walls, furniture), and lighting from [SCENE_AND_MODEL_REFERENCE_IMAGE].
- SMART REPLACEMENT: Remove the original clothing item from [SCENE_AND_MODEL_REFERENCE_IMAGE] and put the NEW item from [CLOTHING_ITEM_TO_WEAR_IMAGE] in its place.
- NO EXTRA CLOTHES: Do NOT add any additional clothing items (like pants, shoes, or belts) unless there is a human model in the reference image who explicitly needs them. If the scene is a hanger or flat-lay, ONLY render the item from [CLOTHING_ITEM_TO_WEAR_IMAGE].
- HIGH-END QUALITY: The new product must look perfectly ironed, clean, and professional. Sharp focus on fabric details, 8k resolution, cinematic lighting.
- ONE single holistic image. NO COLLAGES. NO REPETITION.

FORMAT: {aspect}
Fill frame, no borders."""
            logger.info("[PROMPT] own_variant: default fallback used (admin prompt is empty)")
        else:
            logger.info("[PROMPT] own_variant: using %s prompt, length=%d", "admin" if own_variant_from_admin else "fallback-db", len(base))
        prompt_filled = apply_replacements(base)

    elif data.get("random_other_mode"):
        # Для рандома часто промпт строится динамически, но если есть базовый — применяем
        base_random_other = await db.get_app_setting("random_other_prompt") or await db.get_random_other_prompt()
        if base_random_other:
            prompt_filled = apply_replacements(base_random_other)
        else:
            has_person = data.get("has_person")
            load = data.get("info_load")
            product_name = data.get("product_name")
            h_cm = data.get("height_cm"); w_cm = data.get("width_cm"); l_cm = data.get("length_cm")
            season = data.get("season")
            style = data.get("style")
            
            p_parts = ["Professional commercial product photography. High quality, ultra realistic lighting. "]
            p_parts.append(f"Product: {product_name}. ")
            if has_person: p_parts.append(f"A {gender_word} is in the scene with the product. ")
            else: p_parts.append("No people in the shot, focus strictly on the product itself. ")
            p_parts.append(f"Infographic load: {load}/10. ")
            p_parts.append(f"Camera angle: {view_word}, Distance: {dist_word}. ")
            dims = []
            if h_cm: dims.append(f"height {h_cm}cm")
            if w_cm: dims.append(f"width {w_cm}cm")
            if l_cm: dims.append(f"length {l_cm}cm")
            if dims: p_parts.append(f"Product dimensions: {', '.join(dims)}. ")
            if season: p_parts.append(f"Season/Vibe: {season}. ")
            if style: p_parts.append(f"Style: {style}. ")
            p_parts.append("8k resolution, cinematic lighting, sharp focus on product.")
            prompt_filled = "".join(p_parts)

    elif data.get("normal_gen_mode"):
        prompt_filled = data.get("prompt") or ""

    elif data.get("random_mode"):
        # Рандом Одежда и Обувь - используем промпт из app_settings
        base_random = await db.get_app_setting("random_prompt") or await db.get_random_prompt()
        if base_random and "{" in base_random:
            prompt_filled = apply_replacements(base_random)
        else:
            # Старая логика сборки по частям
            p_parts = ["Professional commercial fashion photography. High quality, realistic lighting. "]
            p_parts.append(f"Model: {gender_word or 'person'}. ")
            if data.get("age"): p_parts.append(f"Age: {data.get('age')}. ")
            if size_text: p_parts.append(f"Body type: {size_text}. ")
            h = data.get("height")
            if h: p_parts.append(f"Height: {h}cm. ")
            b_type = data.get("body_type")
            if b_type: p_parts.append(f"Body density score: {b_type}/10. ")
            
            loc = data.get("rand_location") or data.get("rand_location_indoor") or data.get("rand_location_outdoor")
            loc_map = {
                "inside_restaurant":"внутри ресторана", "photo_studio":"в фотостудии", "coffee_shop":"в кофейне",
                "city":"в городе", "building":"у здания", "wall":"у стены", "park":"в парке",
                "coffee_shop_out":"у кофейни", "forest":"в лесу", "car":"у машины", "restaurant": "в ресторане",
                "room": "в комнате", "office": "в офисе", "mall": "в торговом центре", "cafe": "у кофейни"
            }
            if loc:
                if loc == 'custom':
                    custom = (data.get('rand_location_custom') or '').strip()
                    if custom: p_parts.append(f"Location: {custom}. ")
                else:
                    p_parts.append(f"Location: {loc_map.get(loc, loc)}. ")
            
            if data.get("pants_style"): p_parts.append(f"Pants cut: {data.get('pants_style')}. ")
            if data.get("sleeve"): p_parts.append(f"Sleeve type: {data.get('sleeve')}. ")
            L = (data.get("length") or "").strip()
            if L: p_parts.append(f"Garment length: {L}. ")
            if data.get("pose"): p_parts.append(f"Pose: {data.get('pose')}. ")
            p_parts.append(f"Camera distance: {dist_word}. View: {view_word}. ")
            if data.get("season"): p_parts.append(f"Season: {data.get('season')}. ")
            if data.get("holiday"): p_parts.append(f"Occasion/Holiday: {data.get('holiday')}. ")
            p_parts.append("8k resolution, cinematic lighting, professional studio look.")
            prompt_filled = ((base_random or "") + "\n\n" + "".join(p_parts)).strip()

    elif category == "whitebg":
        # Белый фон: отправляем промпт строго как в админке (без автодобавлений).
        base_whitebg = (await db.get_app_setting("whitebg_prompt") or await db.get_whitebg_prompt() or "").strip()
        if base_whitebg:
            prompt_filled = base_whitebg
            strict_admin_prompt_mode = True
        else:
            prompt_filled = "High-end commercial product photography on a pure white background. Perfectly ironed, clean, professional studio lighting, 8k resolution, sharp focus on fabric details and texture."

    elif category == "storefront":
        # Витрина: приоритет у промта выбранной модели из вкладки "Витрина".
        model_prompt = ""
        model_id = data.get("model_id")
        if model_id:
            try:
                async with aiosqlite.connect(db._db_path) as conn:
                    async with conn.execute(
                        """
                        SELECT p.text
                        FROM models m
                        JOIN prompts p ON p.id = m.prompt_id
                        WHERE m.id = ? AND m.category = 'storefront'
                        """,
                        (int(model_id),),
                    ) as cur:
                        row = await cur.fetchone()
                        if row and row[0]:
                            model_prompt = str(row[0]).strip()
            except Exception:
                model_prompt = ""

        # fallback на prompt_id для совместимости старых состояний
        if not model_prompt:
            model_pid = data.get("prompt_id")
            if model_pid:
                try:
                    model_prompt = (await db.get_prompt_text(int(model_pid)) or "").strip()
                except Exception:
                    model_prompt = ""

        storefront_from_admin = (await db.get_app_setting("storefront_prompt") or "").strip()
        base_storefront = model_prompt or storefront_from_admin or (await db.get_storefront_prompt() or "")

        # Нужен строгий режим: текст уходит 1-в-1 как в админке/модели.
        prompt_text = base_storefront

        if not base_storefront.strip():
            base_storefront = """ROLE & TASK: Professional AI system for product showcase photography.
Your task is to take the NEW item from [CLOTHING_ITEM_TO_WEAR_IMAGE] and render it perfectly into the scene from [SCENE_AND_MODEL_REFERENCE_IMAGE].

The [CLOTHING_ITEM_TO_WEAR_IMAGE] is the ONLY source of truth for the item's design, color, and texture.

CORE RULES:
- PRODUCT FIDELITY: 100% exact reproduction of silhouette, print, and texture from [CLOTHING_ITEM_TO_WEAR_IMAGE].
- NO REINTERPRETATION: Do NOT simplify the design. If the product has a specific print (like red flowers), it MUST be rendered exactly as shown, in the same position and scale.
- SCENE RECONSTRUCTION: Maintain the EXACT background, lighting, and environment from [SCENE_AND_MODEL_REFERENCE_IMAGE].
- REPLACEMENT: Identify the original clothing item in [SCENE_AND_MODEL_REFERENCE_IMAGE] (whether it is on a hanger, on a hook, or laid flat on a surface). REMOVE IT COMPLETELY.
- NATURAL PLACEMENT: Place the NEW item from [CLOTHING_ITEM_TO_WEAR_IMAGE] in the exact same spot and orientation.
- HANGER/HOOK INTEGRATION: If the original item was on a hanger or hook, the NEW item must appear naturally hanging from that SAME hanger or hook with realistic gravity-defying folds and shadows.
- QUALITY: 4K Ultra HD, professional high-end commercial look. ZERO human parts.
- PRODUCT ENHANCEMENT: The new product must look flawlessly ironed, impeccably clean, and brand new. Sharp focus on every fabric detail, weave, and texture. Use cinematic, professional studio lighting to accentuate the product's premium quality and silhouette.
- NO HANDS: Do NOT add human hands or any other body parts unless they are already present in [SCENE_AND_MODEL_REFERENCE_IMAGE].

FORMAT:
- Aspect Ratio: {aspect}
- Fill frame. No borders.

🎯 FINAL GOAL: A high-end, luxury marketplace-ready photo where the item from [CLOTHING_ITEM_TO_WEAR_IMAGE] replaces the original item with perfect commercial presentation and superior quality."""
            logger.info("[PROMPT] storefront: default fallback used (model/admin prompts are empty)")
        else:
            src = "model" if model_prompt else ("admin" if storefront_from_admin else "fallback-db")
            logger.info("[PROMPT] storefront: using %s prompt, length=%d", src, len(base_storefront))
        prompt_filled = base_storefront
        strict_admin_prompt_mode = True

    elif data.get("infographic_mode"):
        # Инфографика - используем промпты из app_settings
        if category == "infographic_clothing":
            base_info = await db.get_app_setting("infographic_clothing_prompt") or await db.get_infographic_clothing_prompt()
        else:
            base_info = await db.get_app_setting("infographic_other_prompt") or await db.get_infographic_other_prompt()
        if base_info and "{" in base_info:
            prompt_filled = apply_replacements(base_info)
        else:
            p_parts = ["Professional commercial product photography with infographic elements. High quality, 8k resolution. "]
            brand = data.get("info_brand")
            if brand: p_parts.append(f"Product/Brand name: {brand}. ")
            load = data.get("info_load")
            if load: p_parts.append(f"Infographic design complexity level: {load}/10. ")
            lang_val = data.get("info_lang")
            if lang_val: p_parts.append(f"Text language: {lang_val}. ")
            advs_clean = [a for a in advs if a]
            if advs_clean: p_parts.append(f"Key advantages to highlight: {', '.join(advs_clean)}. ")
            extra = data.get("info_extra")
            if extra: p_parts.append(f"Additional text: {extra}. ")
            p_parts.append(f"Camera angle: {view_word}, Distance: {dist_word}. ")
            
            if data.get("has_person"):
                pose = data.get("info_pose")
                p_parts.append(f"Model: {gender_word or 'person'}, Age: {age_text or 'adult'}. Pose: {pose or 'natural'}. ")
            else:
                p_parts.append("No people in the shot, focus strictly on the product. ")
                
            season = data.get("info_season")
            holiday = data.get("info_holiday")
            if season: p_parts.append(f"Season/Atmosphere: {season}. ")
            if holiday: p_parts.append(f"Occasion/Holiday: {holiday}. ")
            
            if category == "infographic_clothing":
                if size_text: p_parts.append(f"Clothing size: {size_text}. ")
                if data.get("height"): p_parts.append(f"Model height: {data.get('height')}cm. ")
                if data.get("body_type"): p_parts.append(f"Model body type score: {data.get('body_type')}/10. ")
                if data.get("pants_style"): p_parts.append(f"Pants cut: {data.get('pants_style')}. ")
                if sleeve_text: p_parts.append(f"Sleeve type: {sleeve_text}. ")
                if data.get("length"): p_parts.append(f"Garment length: {data.get('length')}. ")

            p_parts.append("Clean composition, commercial lighting, professional studio look.")
            prompt_filled = (base_info + "\n\n" + "".join(p_parts)).strip() if base_info else "".join(p_parts)
    else:
        # Обычный режим / Пресеты
        model_id = data.get("model_id")
        if not model_id and (data.get("is_preset") or category == "presets"):
            # ПРЕСЕТЫ БЕЗ МОДЕЛИ - используем промпт из app_settings
            base_presets = await db.get_app_setting("presets_prompt") or await db.get_random_prompt()
            if base_presets and "{" in base_presets:
                prompt_filled = apply_replacements(base_presets)
            else:
                p_parts = ["Professional commercial fashion photography. High quality, realistic lighting. "]
                p_parts.append(f"Model: {gender_word or 'person'}. ")
                if age_text: p_parts.append(f"Age: {age_text}. ")
                if size_text: p_parts.append(f"Body type: {size_text}. ")
                h = data.get("height")
                if h: p_parts.append(f"Height: {h}cm. ")
                if data.get("pants_style"): p_parts.append(f"Pants cut: {data.get('pants_style')}. ")
                if sleeve_text: p_parts.append(f"Sleeve type: {sleeve_text}. ")
                L = (data.get("length") or "").strip()
                if L: p_parts.append(f"Garment length: {L}. ")
                if data.get("pose"): p_parts.append(f"Pose: {data.get('pose')}. ")
                p_parts.append(f"Camera distance: {dist_word}. View: {view_word}. ")
                if data.get("season"): p_parts.append(f"Season: {data.get('season')}. ")
                p_parts.append("8k resolution, cinematic lighting, professional studio look.")
                prompt_filled = ((base_presets or "") + "\n\n" + "".join(p_parts)).strip()
        else:
            # Обычная модель (из БД по prompt_id)
            if model_id:
                # Если выбрана конкретная модель, усиливаем требование идентичности
                # Используем логику "Свой вариант" (полное переодевание), как просил пользователь
                base = f"""STRICT FASHION REDRESS TASK:
Generate ONE SINGLE IMAGE. NO COLLAGES. NO SIDE-BY-SIDE. NO REPETITION.

INPUT DATA:
1. [SCENE_AND_MODEL_REFERENCE_IMAGE]: The model, face, pose, and background.
2. [CLOTHING_ITEM_TO_WEAR_IMAGE]: The NEW item to put on the model.

CORE RULES:
- IDENTITY: Keep the EXACT face and body of the person from [SCENE_AND_MODEL_REFERENCE_IMAGE].
- POSE: Keep the EXACT pose from [SCENE_AND_MODEL_REFERENCE_IMAGE].
- BACKGROUND: Keep the EXACT environment from [SCENE_AND_MODEL_REFERENCE_IMAGE].
- TOTAL OUTFIT OVERHAUL: You MUST DISCARD ALL clothing items (tops, bottoms, shoes, accessories) from [SCENE_AND_MODEL_REFERENCE_IMAGE]. 
- IGNORE ORIGINAL CLOTHES: Completely ignore any clothing mentioned in the scene description below.
- NEW STYLING: Put the item from [CLOTHING_ITEM_TO_WEAR_IMAGE] on the person. 
- COMPLETE THE LOOK: If [CLOTHING_ITEM_TO_WEAR_IMAGE] is only a top, you MUST generate NEW matching pants/skirt and shoes that perfectly fit the style of the new item. 
- STYLISH OUTFIT: Avoid making the entire outfit monochromatic or the same color as the new item. Use complementary colors, different materials, and stylish textures for the pants and shoes to create a professional fashion-forward look. DO NOT reuse the pants from the original photo.
- FIDELITY: The new item must look 100% identical to [CLOTHING_ITEM_TO_WEAR_IMAGE] in texture and silhouette.
- HIGH-END QUALITY: The new product must look perfectly ironed, clean, and brand new. Sharp focus on fabric details, textures, and professional cinematic lighting.

FORMAT:
- Aspect Ratio: {{aspect}}
- Requirement: Fill the frame. ZERO BORDERS.

🎯 TARGET: A high-end, luxury marketplace photo where the model from [SCENE_AND_MODEL_REFERENCE_IMAGE] is wearing a COMPLETELY NEW OUTFIT with superior commercial quality.

SCENE DESCRIPTION (USE FOR BACKGROUND AND MODEL ONLY, IGNORE CLOTHES): {prompt_text}"""
                prompt_filled = apply_replacements(base)
            else:
                prompt_filled = apply_replacements(prompt_text)
            
            # Добавляем только то, чего нет в плейсхолдерах
            if "{Тип кроя}" not in prompt_text and data.get("pants_style"):
                prompt_filled += f" Cut of pants: {data.get('pants_style')}."
            if "{Поза}" not in prompt_text and data.get("pose"):
                prompt_filled += f" Model pose: {data.get('pose')}."
            if "{ракурс фотографии}" not in prompt_text and "{Дистанция}" not in prompt_text and dist_word:
                prompt_filled += f" Camera distance: {dist_word}."
            if "{Сезон}" not in prompt_text and data.get("season"):
                prompt_filled += f" Season: {data.get('season')}."

    # --- ДОБАВЛЯЕМ ДИНАМИЧЕСКИЕ ПАРАМЕТРЫ ---
    dynamic_parts = []
    # Ключи, которые мы НИКОГДА не добавляем в конец промпта
    exclude_keys = {
        "category", "cloth", "index", "model_id", "prompt_id", 
        "current_step_id", "current_step_key", "current_step_index",
        "is_preset", "random_mode", "random_other_mode", "normal_gen_mode",
        "infographic_mode", "own_mode", "storefront_mode",
        # Служебные значения UI/выбора модели (не должны попадать в промпт)
        "model_select", "model_select_label", "display_category",
        "photos", "downloaded_paths", "own_bg_photo_id", "own_product_photo_id",
        "bg_photo", "photo", "user_photo_id", "result_photo_id", "has_person", "age", "size", "height", "body_type",
        "pants_style", "sleeve", "length", "pose", "dist", "view", "season", "holiday",
        "info_gender", "info_load", "info_lang", "info_brand", "info_extra", "info_angle", "info_pose",
        "info_season", "info_holiday", "aspect", "prompt", "last_photos_msg_id", "last_sent_prompt",
        "gender", "cloth_label", "gender_label", "photo_label", "aspect_label", "height_cm", "width_cm", "length_cm",
        "own_length", "child_gender", "info_dist", "info_adv1", "info_adv2", "info_adv3", "repeat_mode", "own_ref_photo_id",
        "is_going_back", "current_step_id", "current_step_key", "current_step_index", "is_preset", "own_ref_photo_id",
        "own_product_photo_id", "own_bg_photo_id", "bg_photo", "photo", "user_photo_id", "result_photo_id",
        "last_photos_msg_id", "last_sent_prompt", "is_going_back", "current_step_id", "current_step_key", "current_step_index",
        "photo_label", "aspect_label", "height_cm", "width_cm", "length_cm", "own_length", "child_gender",
        "info_dist", "info_adv1", "info_adv2", "info_adv3", "repeat_mode", "own_ref_photo_id"
    }
    
    # Также не добавляем те ключи, которые были использованы как плейсхолдеры в базовом тексте
    prompt_text_lower = (prompt_text or "").lower()
    for k, v in data.items():
        if k in exclude_keys: continue
        if not v: continue
        if isinstance(v, str) and v.startswith("AgAC"): continue # Пропускаем file_id
        
        # Проверяем, нет ли этого ключа в промпте в виде {key} (регистронезависимо)
        if f"{{{k.lower()}}}" in prompt_text_lower: continue
        
        # Проверяем все ключи из replacements (плейсхолдеры)
        is_replaced = False
        for r_key in replacements.keys():
            if r_key.lower() == f"{{{k.lower()}}}" and r_key.lower() in prompt_text_lower:
                is_replaced = True
                break
        if is_replaced: continue

        dynamic_parts.append(f"{k}: {v}")
    
    # Для storefront/whitebg отправляем промпт строго как в админке/модели, без автодобавлений.
    if not strict_admin_prompt_mode:
        if dynamic_parts:
            sep = " " if (prompt_filled and prompt_filled.rstrip().endswith((".", "!", "?"))) else ". "
            prompt_filled = prompt_filled.rstrip() + sep + "Additional details: " + ", ".join(dynamic_parts) + "."

    # Финальная проверка на количество изображений (защита от коллажей)
    # В строгом режиме (storefront/whitebg) НЕ меняем текст из админки.
    if not strict_admin_prompt_mode:
        if "ONE single" not in prompt_filled:
            prompt_filled += " Produce ONE single, high-resolution, photorealistic image. No collages, no split screens, no multiple views in one image."

    # ЧИСТКА ОТ СИСТЕМНОГО ТЕКСТА (Баг: "фото загружено")
    if data.get("infographic_mode"):
        prompt_filled += " ABSOLUTE NEGATIVE RULE: DO NOT write 'фото загружено', 'photo uploaded', or any Telegram-style system messages on the image. ONLY include product information text. No interface elements, no chat bubbles."

    # Финальный акцент на идентичность и отсутствие коллажей для режима Own Model
    if data.get("own_mode") or category == "own":
        prompt_filled += " MANDATORY: Keep the EXACT facial identity, skin tone, and facial features from Photo 1. 100% face match required. DO NOT change the model. DO NOT produce a collage. Dress the model from Photo 1 in the item from Photo 2. Result must be ONE single image."

    return prompt_filled


@router.callback_query(F.data == "form_generate")
async def form_generate(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await _do_generate(callback, state, db)

async def _do_generate(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    user_id = message_or_callback.from_user.id
    if gen_locks[user_id].locked():
        logger.warning(f"[_do_generate] Пропуск: Генерация для {user_id} уже выполняется.")
        if isinstance(message_or_callback, CallbackQuery):
            await _safe_answer(message_or_callback)
        return
    async with gen_locks[user_id]:
        await _do_generate_real(message_or_callback, state, db)

async def _do_generate_real(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    user_id = message_or_callback.from_user.id
    data = await state.get_data()
    logger.info(f"[_do_generate] Начало генерации для пользователя {user_id}. Данные сессии: {data}")
    
    # Определяем объект для ответов и бота
    if isinstance(message_or_callback, CallbackQuery):
        ans_obj = message_or_callback.message
        bot = message_or_callback.bot
    else:
        ans_obj = message_or_callback
        bot = message_or_callback.bot

    # Проверка техработ
    if await db.get_maintenance():
        settings = load_settings()
        if user_id not in (settings.admin_ids or []):
            lang = await db.get_user_language(user_id)
            if isinstance(message_or_callback, CallbackQuery):
                await _safe_answer(message_or_callback, get_string("maintenance_alert", lang), show_alert=True)
            else:
                await ans_obj.answer(get_string("maintenance_alert", lang))
            return

    # Блокировка пользователя
    if await db.get_user_blocked(user_id):
        lang = await db.get_user_language(user_id)
        text = get_string("user_blocked", lang)
        if isinstance(message_or_callback, CallbackQuery):
            await _safe_answer(message_or_callback, text, show_alert=True)
        else:
            await ans_obj.answer(text)
        return

    # Если не обычная генерация и нет фото - просим прислать (для пресетов и т.д.)
    category = data.get("category")
    lang = await db.get_user_language(user_id)

    # Собираем фото для генерации
    input_photos = []
    if data.get("normal_gen_mode"):
        input_photos = data.get("photos", [])
        if not input_photos:
            input_photos = [data.get("user_photo_id") or data.get("photo")]
    elif category == "own_variant":
        # Фото 1 — фон, Фото 2 — товар
        bg = data.get("own_bg_photo_id") or data.get("bg_photo") or data.get("user_photo_id")
        prod = data.get("own_product_photo_id") or data.get("photo")
        input_photos = [bg, prod]
    elif category == "storefront":
        # Витринное фото: отправляем в нейросеть ТОЛЬКО товар + промпт (без фонового фото модели)
        prod = data.get("user_photo_id") or data.get("photo")
        input_photos = [prod]
            
    elif category in ("female", "male", "child") or data.get("is_preset") or category == "presets":
        # Пресеты: Фото 1 — модель, Фото 2 — товар
        # Сначала проверяем, не сохранена ли модель как референс (новый флоу)
        ref = data.get("own_ref_photo_id")
        
        # Если мы в режиме повтора, нам ВАЖНО использовать сохраненную модель
        if not ref:
            model_id = data.get("model_id")
            if model_id:
                async with aiosqlite.connect(db._db_path) as conn:
                    async with conn.execute("SELECT photo_file_id FROM models WHERE id=?", (model_id,)) as cur:
                        row = await cur.fetchone()
                        if row: ref = row[0]
        
        # Товар — это user_photo_id (если загружен после модели) или photo
        prod = data.get("user_photo_id") or data.get("photo")
        
        # Если ref и prod одинаковые, значит юзер еще не загрузил товар
        if ref == prod:
            prod = None
            
        if ref and prod:
            input_photos = [ref, prod]
        elif prod:
            input_photos = [prod]
        elif ref:
            input_photos = [ref]
            
        # Если в режиме пресетов нет второго фото (товара), просим загрузить
        if not prod and (data.get("is_preset") or category == "presets" or data.get("repeat_mode")):
            logger.error(f"[_do_generate] Нет фото товара для пресетов. Ref: {ref}")
            text = get_string("upload_product", lang)
            await state.set_state(CreateForm.waiting_view)
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.message.answer(text)
                await _safe_answer(message_or_callback)
            else:
                await ans_obj.answer(text)
            return

    elif data.get("own_mode") or category == "own":
        # Фото 1 — модель, Фото 2 — товар
        ref = data.get("own_ref_photo_id") or data.get("bg_photo") or data.get("user_photo_id")
        prod = data.get("own_product_photo_id") or data.get("photo")
        input_photos = [ref, prod]
    else:
        input_photos = [data.get("user_photo_id") or data.get("photo")]

    input_photos = [fid for fid in input_photos if fid]
    if not input_photos:
        logger.error(f"[_do_generate] Нет фото для генерации. Category: {category}, Data keys: {list(data.keys())}")
        text = get_string("upload_product", lang)
        await state.set_state(CreateForm.waiting_view)
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.answer(text)
            await _safe_answer(message_or_callback)
        else:
            await message_or_callback.answer(text)
        return

    # Проверка баланса (ВСЕГДА 25 РУБЛЕЙ)
    balance = await db.get_user_balance(user_id)
    price = 25
    
    if balance < price:
        msg = f"❌ Недостаточно средств на балансе.\n\nСтоимость 1 генерации = {price} руб.\nВаш баланс: {balance} руб.\n\nПожалуйста, пополните баланс в профиле."
        if isinstance(message_or_callback, CallbackQuery):
            await _safe_answer(message_or_callback, msg, show_alert=True)
        else:
            await ans_obj.answer(msg)
        return

    try:
        
        quality = 'HD' # По умолчанию HD, так как подписки убрали
        
        if not data:
            logger.error(f"[_do_generate] КРИТИЧЕСКАЯ ОШИБКА: Данные сессии пусты для пользователя {user_id}")
            if isinstance(message_or_callback, CallbackQuery):
                await _safe_answer(message_or_callback, get_string("session_not_found", lang) + " (пустые данные)", show_alert=True)
            else:
                await ans_obj.answer(get_string("session_not_found", lang) + " (пустые данные)")
            return

        prompt_filled = await _build_final_prompt(data, db)
        logger.info(f"[_do_generate] Сформирован финальный промпт (длина: {len(prompt_filled)} симв.)")
        await state.update_data(last_sent_prompt=prompt_filled)

        if quality == '4K':
            prompt_filled += " High quality, 4K resolution, ultra detailed."

        # Отправляем сообщение о начале генерации с анимацией
        process_msg = await ans_obj.answer("🎨 ⚡️ ⏳")
        
        async def animate_gen(msg, lang_code):
            start_time = time.time()
            steps_text = [
                "Изучаю ваш запрос",
                "Обрабатываю детали",
                "Применяю нейронные фильтры",
                "Улучшаю качество",
                "Финализирую"
            ]
            total_steps = 5
            sub_steps = 2
            tick_seconds = 1.2
            try:
                for step in range(1, total_steps + 1):
                    for sub in range(sub_steps):
                        elapsed = int(time.time() - start_time)
                        progress = int(((step - 1) / total_steps + (sub / sub_steps) / total_steps) * 100)
                        if progress > 99: progress = 99
                        filled = int(progress / 10)
                        bar = "🟦" * filled + "⬜️" * (10 - filled)
                        text = (
                            f"🚀 Генерация\n\n"
                            f"{steps_text[step-1]}\n\n"
                            f"{bar} {progress}%\n\n"
                            f"Прошло: {elapsed}с • Шаг {step}/{total_steps}\n\n"
                            f"Результат вас приятно удивит"
                        )
                        await msg.edit_text(text)
                        await asyncio.sleep(tick_seconds)
            except: pass

        anim_task = asyncio.create_task(animate_gen(process_msg, lang))
    
        # Объединяем основные и специальные ключи для режима "Свой вариант"
        api_keys = await db.list_api_keys()
        if category == "own_variant" or data.get("own_mode") or category == "own":
            own_keys = await db.list_own_variant_api_keys()
            # Добавляем только уникальные токены
            existing_tokens = {k[1] for k in api_keys}
            for ok in own_keys:
                if ok[1] not in existing_tokens:
                    api_keys.append(ok)
            
        active_keys = [k for k in api_keys if k[2]] # is_active
        if not active_keys:
            anim_task.cancel()
            try: await process_msg.delete()
            except: pass
            err_text = get_string("api_error_user", lang) + " (нет активных ключей)"
            if isinstance(message_or_callback, CallbackQuery):
                await _replace_with_text(message_or_callback, err_text)
            else:
                await ans_obj.answer(err_text)
            return
            
        import random
        random.shuffle(active_keys)
        preferred_key_id = None
        try:
            preferred_raw = await db.get_app_setting("last_success_api_key_id")
            preferred_key_id = int(preferred_raw) if preferred_raw else None
        except Exception:
            preferred_key_id = None
        if preferred_key_id is not None:
            active_keys.sort(key=lambda k: 0 if int(k[0]) == preferred_key_id else 1)
        
        last_error_msg = ""
        keys_tried = 0
        max_keys_to_try = min(5, len(active_keys))
        for key_tuple in active_keys:
            if keys_tried >= max_keys_to_try:
                break
            
            kid = key_tuple[0]
            token = key_tuple[1]
            ok, limit_err = await db.check_api_key_limits(kid)
            if not ok:
                lim = (limit_err or "").lower()
                if "limit" in lim or "quota" in lim or "429" in lim:
                    try:
                        await db.update_api_key(kid, is_active=0)
                        await db.record_api_error(
                            kid,
                            token[:10],
                            "KeyLimit",
                            limit_err or "API key limit reached",
                            is_proxy_error=False,
                        )
                    except Exception as de:
                        logger.warning(f"Не удалось деактивировать ключ {kid} по лимиту: {de}")
                continue
            
            keys_tried += 1
            try:
                import io
                
                async def download_one(fid):
                    if not fid: return None
                    if str(fid).startswith("data/"):
                        local_path = os.path.join(BASE_DIR, fid)
                        if os.path.exists(local_path):
                            with open(local_path, "rb") as f:
                                return f.read()
                    try:
                        # Скачиваем напрямую в память
                        f_info = await bot.get_file(fid)
                        dest = io.BytesIO()
                        await bot.download_file(f_info.file_path, dest)
                        return dest.getvalue()
                    except Exception as e:
                        logger.error(f"Ошибка загрузки фото {fid}: {e}")
                        return None

                logger.info(f"[_do_generate] Параллельная загрузка {len(input_photos)} фото")
                # Запускаем загрузку всех фото одновременно
                images_data = await asyncio.gather(*[download_one(fid) for fid in input_photos])
                images_data = [d for d in images_data if d] # Убираем пустые
                
                if not images_data:
                    logger.error("[_do_generate] Не удалось загрузить ни одного фото")
                    continue

                logger.info(f"[_do_generate] Запуск генерации (ключ {kid}, фото: {len(images_data)})")
                from bot.gemini import generate_image
                import uuid
                # Исправляем передачу формата: Gemini ожидает 1x1, 9x16 и т.д.
                raw_aspect = data.get("aspect") or "1:1"
                aspect = raw_aspect.replace(":", "x")
                if aspect == "auto": aspect = "1x1"
                
                # Передаем байты напрямую в generate_image без жесткого таймаута.
                try:
                    key_timeout_s = int(os.getenv("GENERATION_KEY_TIMEOUT_SECONDS", "70"))
                except Exception:
                    key_timeout_s = 70
                key_timeout_s = max(20, min(key_timeout_s, 300))
                result_path = await asyncio.wait_for(
                    generate_image(
                        api_key=token,
                        prompt=prompt_filled,
                        images_bytes=images_data,
                        aspect_ratio=aspect,
                        quality=quality,
                        key_id=kid,
                        db_instance=db,
                    ),
                    timeout=key_timeout_s,
                )
                
                if result_path:
                    await db.record_api_usage(kid)
                    try:
                        await db.set_app_setting("last_success_api_key_id", str(kid))
                    except Exception:
                        pass
                    
                    # Списываем стоимость генерации (ВСЕГДА 25 РУБЛЕЙ ДЛЯ ВСЕХ)
                    price = 25
                    await db.subtract_user_balance(user_id, price)
                    
                    anim_task.cancel()
                    from bot.keyboards import result_actions_keyboard, result_actions_own_keyboard
                    
                    kb_res = result_actions_own_keyboard(lang) if (data.get("own_mode") or category == "own_variant") else result_actions_keyboard(lang)

                    history_dir = os.path.join("data", "history")
                    os.makedirs(history_dir, exist_ok=True)
                    
                    pid = await db.generate_pid()
                    db_result_path = f"data/history/result_{pid}.jpg"
                    local_result_path = os.path.join(BASE_DIR, db_result_path)
                    os.makedirs(os.path.dirname(local_result_path), exist_ok=True)

                    # Перемещаем локальный результат сразу в history и отправляем по URL,
                    # чтобы Telegram скачивал сам (без upload через Bot API).
                    src = result_path if os.path.exists(result_path) else os.path.join(BASE_DIR, str(result_path))
                    try:
                        os.replace(src, local_result_path)
                    except Exception:
                        # fallback: копируем
                        import shutil
                        shutil.copyfile(src, local_result_path)
                        try:
                            os.remove(src)
                        except Exception:
                            pass

                    result_url = _public_url_for(db_result_path)
                    await state.update_data(result_photo_id=db_result_path)
                    kb_with_download = _result_keyboard_with_download(kb_res, result_url)
                    await ans_obj.answer(
                        get_string("gen_success", lang),
                        reply_markup=kb_with_download,
                    )

                    try:
                        # Качаем входные фото
                        local_input_paths = []
                        for i, f_id in enumerate(input_photos):
                            if not f_id: continue
                            db_inp_path = f"data/history/input_{pid}_{i}.jpg"
                            local_inp_path = os.path.join(BASE_DIR, db_inp_path)
                            try:
                                f_info = await bot.get_file(f_id)
                                await bot.download_file(f_info.file_path, local_inp_path)
                                local_input_paths.append(db_inp_path)
                            except: pass
                    except Exception as e:
                        logger.error(f"Error downloading images for history: {e}")

                    await db.add_generation_history(
                        pid=pid,
                        user_id=user_id,
                        category=category,
                        params=json.dumps(data),
                        input_photos=json.dumps(input_photos),
                        result_photo_id=db_result_path,
                        input_paths=json.dumps(local_input_paths),
                        result_path=db_result_path,
                        prompt=prompt_filled
                    )
                    
                    try: await process_msg.delete()
                    except: pass
                    if isinstance(message_or_callback, CallbackQuery): await _safe_answer(message_or_callback)
                    return
                else:
                    from bot.gemini import is_proxy_error
                    await db.record_api_error(kid, token[:10], "EmptyResult", "Empty result from API", is_proxy_error=False)
            except asyncio.TimeoutError as e:
                logger.error(f"Таймаут генерации на ключе {kid}: {e}", exc_info=True)
                last_error_msg = "generation_timeout"
                from bot.gemini import is_proxy_error
                await db.record_api_error(kid, token[:10], "TimeoutError", "Generation timed out", is_proxy_error=True)
                # На таймауте переключаемся на следующий ключ.
                continue
            except Exception as e:
                logger.error(f"Ошибка генерации на ключе {kid}: {e}", exc_info=True)
                last_error_msg = str(e)
                from bot.gemini import is_proxy_error, is_fatal_key_error
                await db.record_api_error(kid, token[:10], type(e).__name__, str(e), is_proxy_error=is_proxy_error(e))
                err_type = str(getattr(e, "error_type", "") or "").lower()
                status_code = getattr(e, "status_code", None)
                msg_l = str(e).lower()
                if is_fatal_key_error(e):
                    try:
                        await db.update_api_key(kid, is_active=0)
                        logger.warning(f"Ключ {kid} деактивирован (fatal key error), переключаемся на следующий.")
                    except Exception as de:
                        logger.warning(f"Не удалось деактивировать ключ {kid} после fatal key error: {de}")
                    continue
                if status_code == 429 or err_type in ("429", "quota") or "quota" in msg_l or "rate limit" in msg_l:
                    try:
                        await db.update_api_key(kid, is_active=0)
                        logger.warning(f"Ключ {kid} деактивирован из-за лимита/квоты, переключаемся на следующий.")
                    except Exception as de:
                        logger.warning(f"Не удалось деактивировать ключ {kid} после 429/quota: {de}")
                    continue
                # Для временных timeout/network ошибок даем шанс следующему ключу.
                if "timeout" in str(e).lower() or "connection reset by peer" in str(e).lower():
                    continue
        
        anim_task.cancel()
        try: await process_msg.delete()
        except: pass
        
        # Если была конкретная ошибка — показываем более точную причину вместо общего fallback.
        msg_l = (last_error_msg or "").lower()
        if last_error_msg and ("safety" in msg_l or "blocked" in msg_l):
            err_text = f"⚠️ Запрос отклонен нейросетью по соображениям безопасности или из-за содержимого фото."
        elif "503" in msg_l or "high demand" in msg_l or "unavailable" in msg_l:
            err_text = "⚠️ Сейчас сервис генерации перегружен. Попробуйте повторить через 1-2 минуты."
        elif "generation_total_timeout" in msg_l:
            err_text = "⚠️ Генерация превысила лимит времени. Попробуйте еще раз с менее сложным промптом/фото."
        elif "timed out" in msg_l or "timeout" in msg_l or "proxy/network error" in msg_l:
            use_proxy_mode = str(os.getenv("GEMINI_USE_PROXY", "")).lower() in ("1", "true", "yes")
            if use_proxy_mode:
                err_text = "⚠️ Временная сетевая ошибка сервиса генерации. Попробуйте еще раз через 20-60 секунд."
            else:
                err_text = "⚠️ Временная сетевая ошибка сервиса генерации. Попробуйте еще раз через 10-30 секунд."
        else:
            err_text = get_string("api_error_user", lang)
            
        if isinstance(message_or_callback, CallbackQuery): await _replace_with_text(message_or_callback, err_text)
        else: await ans_obj.answer(err_text)
            
    except Exception as e:
        logger.error(f"Критическая ошибка в _do_generate: {e}")
        if 'anim_task' in locals(): anim_task.cancel()
        err_text = get_string("gen_error_contact_support", lang)
        if isinstance(message_or_callback, CallbackQuery): await _replace_with_text(message_or_callback, err_text)
        else: await ans_obj.answer(err_text)

@router.callback_query(F.data == "result_edit")
async def on_result_edit(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Сохраняем текущее состояние перед правками
    await state.set_state(CreateForm.waiting_edit_text)
    lang = await db.get_user_language(callback.from_user.id)
    await callback.message.answer(get_string("enter_edit_description", lang))
    await _safe_answer(callback)


@router.message(CreateForm.waiting_edit_text)
async def on_result_edit_text(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.from_user.id
    if gen_locks[user_id].locked():
        await message.answer("Пожалуйста, подождите, выполняется обработка ваших правок.")
        return
    async with gen_locks[user_id]:
        await on_result_edit_text_real(message, state, db)

async def on_result_edit_text_real(message: Message, state: FSMContext, db: Database) -> None:
    edit_text = (message.text or "").strip()
    data = await state.get_data()
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    
    logger.info(f"[on_result_edit_text] Пользователь {user_id} ввел правки: {edit_text}")
    
    if not data:
        await message.answer(get_string("session_not_found", lang))
        await state.clear()
        return

    # Проверка баланса (ПРАВКИ ВСЕГДА 25 РУБЛЕЙ)
    balance = await db.get_user_balance(user_id)
    price = 25
    
    if balance < price:
        await message.answer(f"❌ Недостаточно средств на балансе для правок.\n\nСтоимость правки = {price} руб.\nВаш баланс: {balance} руб.")
        return

    category = data.get("category", "female")

    # Строим базовый промпт и добавляем правки
    base_prompt = await _build_final_prompt(data, db)
    prompt_filled = f"{base_prompt}\n\nПравки: {edit_text}"
    
    # Качество из подписки
    sub = await db.get_user_subscription(user_id)
    quality = 'HD'
    if sub and '4K' in sub[0].upper():
        quality = '4K'

    # Собираем фото
    if data.get("normal_gen_mode"):
        input_photos = data.get("photos", [])
        if not input_photos:
            input_photos = [data.get("user_photo_id") or data.get("photo")]
    elif category == "own_variant":
        input_photos = [data.get("own_bg_photo_id"), data.get("own_product_photo_id")]
    elif data.get("own_mode"):
        input_photos = [data.get("own_product_photo_id")]
        # Для "Свой вариант модели" нам нужно еще фото модели (референс)
        # Оно должно быть в user_photo_id, если загружалось ранее
        ref_photo = data.get("user_photo_id") or data.get("photo")
        if ref_photo:
            input_photos.insert(0, ref_photo)
    else:
        # Для пресетов и других динамических режимов
        input_photos = [data.get("user_photo_id") or data.get("photo")]
    
    input_photos = [fid for fid in input_photos if fid]
    if not input_photos:
        logger.error(f"[on_result_edit_text] Фото не найдены в данных сессии: {data}")
        await message.answer("Не найдены исходные фото. Начните заново.")
        return

    # Анимация
    process_msg = await message.answer("🎨 ⚡️ ⏳")
    async def animate_gen(msg):
        start_time = time.time()
        steps_text = [
            "Понимаю, что изменить",
            "Сверяю с оригиналом",
            "Вношу корректировки",
            "Фокусирую детали",
            "Финализирую"
        ]
        total_steps = 5
        sub_steps = 2
        tick_seconds = 1.0
        try:
            for step in range(1, total_steps + 1):
                # Плавная имитация прогресса
                for sub in range(sub_steps):
                    elapsed = int(time.time() - start_time)
                    progress = int(((step - 1) / total_steps + (sub / sub_steps) / total_steps) * 100)
                    if progress > 99: progress = 99
                    
                    filled = int(progress / 10)
                    bar = "🟦" * filled + "⬜️" * (10 - filled)
                    
                    text = (
                        f"✏️ Редактирование\n\n"
                        f"{steps_text[step-1]}\n\n"
                        f"{bar} {progress}%\n\n"
                        f"Прошло: {elapsed}с • Шаг {step}/{total_steps}\n\n"
                        f"Результат вас приятно удивит"
                    )
                    await msg.edit_text(text)
                    await asyncio.sleep(tick_seconds)
        except: pass
    anim_task = asyncio.create_task(animate_gen(process_msg))

    try:
        # Скачиваем фото
        downloaded_paths = []
        import uuid, os
        for fid in input_photos:
            if not fid: continue
            try:
                # Если это локальный путь
                if str(fid).startswith("data/"):
                    local_path = os.path.join(BASE_DIR, fid)
                    if os.path.exists(local_path):
                        ext = local_path.split('.')[-1]
                        p = f"data/temp_edit_{uuid.uuid4()}.{ext}"
                        import shutil
                        shutil.copy2(local_path, p)
                        downloaded_paths.append(p)
                        logger.info(f"[Edit] Added local file: {fid}")
                        continue

                f_info = await message.bot.get_file(fid)
                # Логируем размер файла из инфо Телеграма
                logger.info(f"[Edit] File {fid} size from Telegram: {f_info.file_size} bytes")
                
                ext = f_info.file_path.split('.')[-1]
                p = f"data/temp_edit_{uuid.uuid4()}.{ext}"
                await message.bot.download_file(f_info.file_path, p)
                
                # Проверяем реальный размер на диске
                if os.path.exists(p):
                    sz = os.path.getsize(p)
                    logger.info(f"[Edit] Real file size on disk: {sz} bytes")
                
                downloaded_paths.append(p)
            except Exception as e:
                logger.error(f"[Edit] Ошибка загрузки фото {fid}: {e}")

        # Выбор API ключей
        # Всегда используем основные API ключи (Pro версия)
        api_keys = await db.list_api_keys()
        
        active_keys = [k for k in api_keys if k[2]]
        import random
        random.shuffle(active_keys)
        preferred_key_id = None
        try:
            preferred_raw = await db.get_app_setting("last_success_api_key_id")
            preferred_key_id = int(preferred_raw) if preferred_raw else None
        except Exception:
            preferred_key_id = None
        if preferred_key_id is not None:
            active_keys.sort(key=lambda k: 0 if int(k[0]) == preferred_key_id else 1)
        
        result_path = None
        kid_used = None
        
        from bot.gemini import generate_image
        raw_aspect = data.get("aspect") or "1:1"
        aspect = raw_aspect.replace(":", "x")
        if aspect == "auto": aspect = "1x1"
        
        max_keys_to_try = min(5, len(active_keys))
        keys_tried = 0
        for key_tuple in active_keys:
            if keys_tried >= max_keys_to_try:
                break
            kid, token = key_tuple[0], key_tuple[1]
            ok, limit_err = await db.check_api_key_limits(kid)
            if not ok:
                lim = (limit_err or "").lower()
                if "limit" in lim or "quota" in lim or "429" in lim:
                    try:
                        await db.update_api_key(kid, is_active=0)
                        await db.record_api_error(
                            kid,
                            token[:10],
                            "KeyLimit",
                            limit_err or "API key limit reached",
                            is_proxy_error=False,
                        )
                    except Exception as de:
                        logger.warning(f"[Edit] Не удалось деактивировать ключ {kid} по лимиту: {de}")
                continue
            
            keys_tried += 1
            try:
                try:
                    key_timeout_s = int(os.getenv("GENERATION_KEY_TIMEOUT_SECONDS", "70"))
                except Exception:
                    key_timeout_s = 70
                key_timeout_s = max(20, min(key_timeout_s, 300))
                result_path = await asyncio.wait_for(
                    generate_image(
                        api_key=token,
                        prompt=prompt_filled,
                        image_paths=downloaded_paths,
                        aspect_ratio=aspect,
                        quality=quality,
                        key_id=kid,
                        db_instance=db,
                    ),
                    timeout=key_timeout_s,
                )
                if result_path:
                    kid_used = kid
                break
            except asyncio.TimeoutError as e:
                logger.error(f"Edit timeout key {kid}: {e}")
                continue
            except Exception as e:
                logger.error(f"Edit error key {kid}: {e}")
                from bot.gemini import is_fatal_key_error
                err_type = str(getattr(e, "error_type", "") or "").lower()
                status_code = getattr(e, "status_code", None)
                msg_l = str(e).lower()
                if is_fatal_key_error(e):
                    try:
                        await db.update_api_key(kid, is_active=0)
                        logger.warning(f"[Edit] Ключ {kid} деактивирован (fatal key error), переключаемся на следующий.")
                    except Exception as de:
                        logger.warning(f"[Edit] Не удалось деактивировать ключ {kid} после fatal key error: {de}")
                    continue
                if status_code == 429 or err_type in ("429", "quota") or "quota" in msg_l or "rate limit" in msg_l:
                    try:
                        await db.update_api_key(kid, is_active=0)
                        logger.warning(f"[Edit] Ключ {kid} деактивирован из-за лимита/квоты, переключаемся на следующий.")
                    except Exception as de:
                        logger.warning(f"[Edit] Не удалось деактивировать ключ {kid} после 429/quota: {de}")
                continue

        # Чистим временные фото
        for p in downloaded_paths:
            try: os.remove(p)
            except: pass

        anim_task.cancel()
        try: await process_msg.delete()
        except: pass

        if result_path:
            # Успех
            await db.record_api_usage(kid_used)
            try:
                await db.set_app_setting("last_success_api_key_id", str(kid_used))
            except Exception:
                pass
            
            # Списываем баланс (ВСЕГДА 25 РУБЛЕЙ)
            await db.subtract_user_balance(user_id, 25)
            
            await db.update_daily_usage(user_id)

            from bot.keyboards import result_actions_keyboard, result_actions_own_keyboard
            kb = result_actions_keyboard(lang)
            if category == "own_variant" or data.get("own_mode"):
                kb = result_actions_own_keyboard(lang)
                
            # Сохраняем в историю
            pid = await db.generate_pid()
            history_dir = os.path.join("data", "history")
            os.makedirs(history_dir, exist_ok=True)
            
            db_result_path = f"data/history/result_{pid}.jpg"
            local_result_path = os.path.join(BASE_DIR, db_result_path)
            os.makedirs(os.path.dirname(local_result_path), exist_ok=True)

            try:
                # Перемещаем результат в history и отправляем по URL (без upload через Bot API)
                src = result_path if os.path.exists(result_path) else os.path.join(BASE_DIR, str(result_path))
                try:
                    os.replace(src, local_result_path)
                except Exception:
                    import shutil
                    shutil.copyfile(src, local_result_path)
                    try:
                        os.remove(src)
                    except Exception:
                        pass
                
                # Качаем входные фото
                local_input_paths = []
                for i, f_id in enumerate(input_photos):
                    if not f_id: continue
                    db_inp_path = f"data/history/input_{pid}_{i}.jpg"
                    local_inp_path = os.path.join(BASE_DIR, db_inp_path)
                    try:
                        f_info = await message.bot.get_file(f_id)
                        await message.bot.download_file(f_info.file_path, local_inp_path)
                        local_input_paths.append(db_inp_path)
                    except: pass
            except Exception as e:
                logger.error(f"Error downloading images for history in edit: {e}")

            result_url = _public_url_for(db_result_path)
            kb_with_download = _result_keyboard_with_download(kb, result_url)
            await message.answer(
                f"✅ Правки применены!\n\nТекст правок: {edit_text}",
                reply_markup=kb_with_download,
            )

            await db.add_generation_history(
                pid=pid,
                user_id=user_id,
                category=category,
                params=json.dumps(data),
                input_photos=json.dumps(input_photos),
                result_photo_id=db_result_path,
                input_paths=json.dumps(local_input_paths),
                result_path=db_result_path,
                prompt=prompt_filled
            )

            # Не очищаем стейт полностью, чтобы можно было еще раз править или повторить
            await state.set_state(CreateForm.result_ready)
        else:
            await message.answer(get_string("gen_error", lang))

    except Exception as e:
        logger.error(f"Critical error in on_result_edit_text: {e}")
        anim_task.cancel()
        try: await process_msg.delete()
        except: pass
        await message.answer(get_string("gen_error", lang))


@router.callback_query(F.data == "result_repeat")
async def on_result_repeat(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if not data:
        await _safe_answer(callback, get_string("session_not_found", lang), show_alert=True)
        return

    # Оставляем все параметры (включая aspect), но очищаем фото
    remove_keys = [
        "photo", "photo_id", "user_photo_id", "own_product_photo_id",
        "last_pid", "user_photo_count", "photos", "normal_gen_prompt_msg",
        "result_photo_id", "photo_label"
    ]
    
    new_data = {k: v for k, v in data.items() if k not in remove_keys}
    new_data["repeat_mode"] = True
    
    # ВАЖНО: Убеждаемся, что модель сохранена как референс
    if "own_ref_photo_id" not in new_data and "model_id" in new_data:
        # Если почему-то нет ID фото в сессии, попробуем его найти
        pass
    
    await state.clear()
    await state.update_data(**new_data)
    await state.set_state(CreateForm.waiting_view)
    
    await callback.message.answer(get_string("repeat_photo_prompt", lang), reply_markup=back_step_keyboard(lang))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("model_nav:"))
async def on_model_nav(callback: CallbackQuery, db: Database) -> None:
    try:
        parts = callback.data.split(":")
        category = parts[1]
        cloth = parts[2]
        index = int(parts[3])
        logic_category = parts[4] if len(parts) > 4 else None
    except Exception:
        await _safe_answer(callback)
        return
    
    await _show_models_for_category(callback, db, category, cloth, index, logic_category=logic_category)
    await _safe_answer(callback)


@router.callback_query(F.data == "presets_back")
async def on_presets_back(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    data = await state.get_data()
    logic_cat = data.get("category")
    
    if logic_cat == "storefront":
        await on_marketplace_menu(callback, db)
    else:
        await on_ready_presets(callback, db, state)
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("model_search:"))
async def on_model_search(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    parts = callback.data.split(":")
    category = parts[1]
    cloth = parts[2]
    logic_category = parts[3] if len(parts) > 3 else None
    
    await state.update_data(search_cat=category, search_cloth=cloth, search_logic=logic_category)
    await state.set_state(CreateForm.waiting_model_search)
    
    lang = await db.get_user_language(callback.from_user.id)
    await callback.message.answer("🔍 Введите номер модели для быстрого перехода (например: 10):")
    await _safe_answer(callback)

@router.message(CreateForm.waiting_model_search)
async def on_model_search_input(message: Message, state: FSMContext, db: Database) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ Пожалуйста, введите только число.")
        return
        
    requested_index = int(text) - 1 # Чел вводит 1, это индекс 0
    if requested_index < 0:
        requested_index = 0
        
    data = await state.get_data()
    category = data.get("search_cat")
    cloth = data.get("search_cloth")
    logic_category = data.get("search_logic")
    
    await state.set_state(None)
    
    total = await db.count_models(category, cloth)
    if total <= 0:
        await message.answer("Модели не найдены.")
        return
        
    if requested_index >= total:
        requested_index = total - 1
        
    # Показываем модель
    header_text = _model_header(requested_index, total)
    model = await db.get_model_by_index(category, cloth, requested_index)
    
    lang = await db.get_user_language(message.from_user.id)
    kb = model_select_keyboard(category, cloth, requested_index, total, lang, logic_category=logic_category)
    
    if model and model[3]:
        photo = model[3]
        if photo.startswith("AgAC"):
            await message.answer_photo(photo=photo, caption=header_text, reply_markup=kb)
        else:
            from aiogram.types import FSInputFile
            import os
            file_path = photo if os.path.exists(photo) else os.path.join("/app", photo)
            if os.path.exists(file_path):
                await message.answer_photo(photo=FSInputFile(file_path), caption=header_text, reply_markup=kb)
            else:
                await message.answer(header_text, reply_markup=kb)
    else:
        await message.answer(header_text, reply_markup=kb)


@router.callback_query(F.data == "menu_profile")
async def on_menu_profile(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    balance = await db.get_user_balance(callback.from_user.id)
    price = await db.get_user_generation_price(callback.from_user.id)
    text = get_string("profile_info", lang, id=callback.from_user.id, balance=balance, price=price)
    
    await _replace_with_text(callback, text, reply_markup=profile_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data == "menu_subscription")
async def on_sub_menu(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    balance = await db.get_user_balance(callback.from_user.id)
    price = await db.get_user_generation_price(callback.from_user.id)
    text = get_string("top_up_info", lang, id=callback.from_user.id, balance=balance, price=price)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_string("contact_admin", lang), url="https://t.me/bnbslow")],
        [InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_profile")]
    ])
    
    await _replace_with_text(callback, text, reply_markup=kb)
    await _safe_answer(callback)

@router.callback_query(F.data == "menu_history")
async def on_history(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    history = await db.list_user_generations(callback.from_user.id, limit=20)
    
    if not history:
        await callback.answer(get_string("history_empty", lang), show_alert=True)
        return
        
    await callback.message.answer(get_string("history_title", lang))
    
    # Показываем только итоговые фото
    for i, item in enumerate(history, 1):
        pid, result_photo_id, created_at = item
        # created_at может быть строкой или datetime
        date_str = created_at if isinstance(created_at, str) else created_at.strftime("%Y-%m-%d %H:%M")
        
        caption = get_string("history_item", lang, num=i, pid=pid, date=date_str)
        try:
            if result_photo_id.startswith("AgAC"): # Telegram file_id (photo)
                await callback.message.answer_photo(photo=result_photo_id, caption=caption, parse_mode="Markdown")
            elif result_photo_id.startswith("BQAC"): # Telegram file_id (document)
                await callback.message.answer_document(document=result_photo_id, caption=caption, parse_mode="Markdown")
            else:
                # Если это путь к файлу из истории — показываем фото и кнопку скачивания оригинала.
                import os
                file_path = result_photo_id if os.path.exists(result_photo_id) else os.path.join("/app", result_photo_id)
                url = _public_url_for(result_photo_id)
                kb_download = _result_keyboard_with_download(None, url)
                if os.path.exists(file_path):
                    await callback.message.answer_photo(
                        photo=FSInputFile(file_path),
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=kb_download,
                    )
                else:
                    await callback.message.answer(caption, parse_mode="Markdown", reply_markup=kb_download)
        except Exception as e:
            logger.error(f"Error sending history item {pid}: {e}")
            await callback.message.answer(caption, parse_mode="Markdown")
        
        # Небольшая задержка, чтобы не спамить
        await asyncio.sleep(0.1)

    await _safe_answer(callback)


@router.callback_query(F.data == "menu_settings")
async def on_menu_settings(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import settings_keyboard
    await _replace_with_text(callback, get_string("menu_settings", lang), reply_markup=settings_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data == "settings_lang")
async def on_settings_lang(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import language_keyboard
    await _replace_with_text(callback, get_string("select_lang", lang), reply_markup=language_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("lang:"))
async def on_set_lang(callback: CallbackQuery, db: Database) -> None:
    new_lang = callback.data.split(":")[1]
    await db.set_user_language(callback.from_user.id, new_lang)
    await on_menu_settings(callback, db)

@router.callback_query(F.data == "menu_howto")
async def on_menu_howto(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    text = await db.get_howto_text() or "Инструкция в процессе наполнения."
    await _replace_with_text(callback, text, reply_markup=back_main_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data == "menu_proxy")
async def on_menu_proxy(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    import subprocess
    import base64
    
    # Проверяем статус MTProxy напрямую через БД
    try:
        # Получаем статус из БД
        running_str = await db.get_app_setting("mtproxy_running")
        running = running_str == "1"
        
        # Получаем секрет и порт из БД
        secret = await db.get_app_setting("mtproxy_secret")
        port_str = await db.get_app_setting("mtproxy_port")
        port = int(port_str) if port_str else 8888
        
        if secret and running:
            # Формируем ссылку
            server_ip = os.getenv("MTPROXY_SERVER_IP", "130.49.148.147")
            secret_hex = secret.replace("-", "").replace("dd", "")
            if len(secret_hex) == 32:
                link = f"tg://proxy?server={server_ip}&port={port}&secret=dd{secret_hex}"
                text = f"{get_string('proxy_title', lang)}\n\n{get_string('proxy_info', lang)}\n\n`{link}`"
                from bot.keyboards import InlineKeyboardMarkup, InlineKeyboardButton, back_main_keyboard
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_string("proxy_get_link", lang), url=link)],
                    [InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_settings")]
                ])
            else:
                text = get_string("proxy_not_available", lang)
                from bot.keyboards import back_main_keyboard
                kb = back_main_keyboard(lang)
        else:
            text = get_string("proxy_not_available", lang)
            from bot.keyboards import back_main_keyboard
            kb = back_main_keyboard(lang)
    except Exception as e:
        import logging
        logging.error(f"MTProxy error: {e}")
        text = get_string("proxy_not_available", lang)
        from bot.keyboards import back_main_keyboard
        kb = back_main_keyboard(lang)
    
    await _replace_with_text(callback, text, reply_markup=kb)
    await _safe_answer(callback)


@router.callback_query(F.data == "menu_agreement")
async def on_menu_agreement(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    text = await db.get_agreement_text()
    if not text or text.strip() == "":
        text = get_string("agreement_not_set", lang)
    
    # Если мы пришли из клавиатуры принятия условий, возвращаемся к ней, а не в главное меню
    user_accepted = await db.get_user_accepted_terms(callback.from_user.id)
    from bot.keyboards import terms_keyboard, back_main_keyboard
    
    reply_markup = back_main_keyboard(lang) if user_accepted else terms_keyboard(lang)
    
    await _replace_with_text(callback, text, reply_markup=reply_markup)
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("buy_plan:"))
async def on_buy_plan(callback: CallbackQuery, db: Database) -> None:
    plan_id = int(callback.data.split(":")[1])
    lang = await db.get_user_language(callback.from_user.id)
    plan = await db.get_subscription_plan(plan_id)
    if not plan:
        await _safe_answer(callback, "План не найден.", show_alert=True)
        return
    
    # plan structure: (id, name_ru, name_en, name_vi, desc_ru, desc_en, desc_vi, price, duration, limit, active)
    name = plan[1] if lang == "ru" else (plan[2] if lang == "en" else plan[3])
    desc = plan[4] if lang == "ru" else (plan[5] if lang == "en" else plan[6])
    price = plan[7]
    
    text = get_string("buy_sub_text", lang, name=name, desc=desc, price=price, id=callback.from_user.id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_string("contact_admin", lang), url="https://t.me/bnbslow")],
        [InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_subscription")]
    ])
    
    await _replace_with_text(callback, text, reply_markup=kb)
    await _safe_answer(callback)


