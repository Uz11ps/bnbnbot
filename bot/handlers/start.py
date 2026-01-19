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
    form_age_keyboard,
    form_size_keyboard,
    random_vibe_keyboard,
    random_season_keyboard,
    random_decor_keyboard,
    random_skip_keyboard,
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
from aiogram.enums import ChatAction
import logging

logger = logging.getLogger(__name__)


router = Router()

 
class CreateForm(StatesGroup):
    waiting_age = State()
    waiting_child_gender = State()
    waiting_info_gender = State()
    waiting_size = State()
    waiting_height = State()
    waiting_length = State()
    waiting_view = State()
    waiting_prompt = State()
    waiting_aspect = State()
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
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest:
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
    sleeve_map = {
        "normal": "Обычный",
        "long": "Длинные",
        "three_quarter": "Три четверти",
        "elbow": "До локтей",
        "short": "Короткие",
        "none": "Без рукав",
        "skip": "",
    }
    sleeve_text = sleeve_map.get(val, "")
    await state.update_data(own_sleeve=sleeve_text)
    # Далее длина изделия
    await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)

async def _ask_garment_length(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    """Вспомогательная функция для запроса длины изделия с фото-гайдом"""
    lang = await db.get_user_language(message_or_callback.from_user.id)
    photo_path = "garment_length_guide.jpeg"
    text = get_string("select_garment_length", lang)
    kb = garment_length_keyboard(lang)
    
    await state.set_state(CreateForm.waiting_length)
    
    if isinstance(message_or_callback, CallbackQuery):
        try:
            await message_or_callback.message.delete()
        except Exception:
            pass
        await message_or_callback.message.answer_photo(
            FSInputFile(photo_path),
            caption=text,
            reply_markup=kb
        )
    else:
        await message_or_callback.answer_photo(
            FSInputFile(photo_path),
            caption=text,
            reply_markup=kb
        )


async def _run_generation_progress(bot, chat_id: int, message_id: int, stop_event: asyncio.Event) -> None:
    frames = [
        "⏳ Генерация изображения…",
        "🔄 Генерация изображения…",
        "✨ Генерация изображения…",
    ]
    i = 0
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=frames[i % len(frames)])
        except TelegramBadRequest:
            pass
        except Exception:
            pass
        i += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2.5)
        except asyncio.TimeoutError:
            continue


async def _answer_model_photo(callback: CallbackQuery, photo: str, caption: str, reply_markup=None) -> None:
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    
    try:
        if photo.startswith("AgAC"): # Telegram file_id
            await callback.message.answer_photo(photo=photo, caption=caption, reply_markup=reply_markup)
        else: # Локальный файл
            from aiogram.types import FSInputFile
            import os
            # Пробуем найти файл в корне или в /app/
            file_path = photo if os.path.exists(photo) else os.path.join("/app", photo)
            if os.path.exists(file_path):
                await callback.message.answer_photo(photo=FSInputFile(file_path), caption=caption, reply_markup=reply_markup)
            else:
                logger.error(f"Файл фото модели не найден: {photo}")
                await callback.message.answer(caption, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка отправки фото модели: {e}")
        await callback.message.answer(caption, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("child_gender:"))
async def on_child_gender_select(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    gender = callback.data.split(":")[1]
    # gender is 'boy' or 'girl'
    await state.clear()
    await state.update_data(child_gender=gender, category="child", cloth=gender, is_preset=True)
    lang = await db.get_user_language(callback.from_user.id)
    
    # Для детей ПРОПУСКАЕМ возраст, сразу к телосложению
    from bot.keyboards import form_size_keyboard
    await _replace_with_text(callback, get_string("select_body_type", lang), reply_markup=form_size_keyboard(gender, lang))
    await state.set_state(CreateForm.waiting_size)
    await _safe_answer(callback)
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
        logger.debug(f"Subscription check for {user_id} in {channel_id}: {member.status} (is_subbed: {is_subbed})")
        return is_subbed
    except Exception as e:
        logger.error(f"Error checking subscription for {user_id} in {channel_id}: {e}")
        # Если бот не в канале или канал не найден — разрешаем работу, чтобы не блокировать всех
        return True

async def _ensure_access(message_or_callback, db: Database, bot: Bot) -> bool:
    """Проверяет условия доступа (соглашение и подписка) и выводит нужный экран"""
    user_id = message_or_callback.from_user.id
    lang = await db.get_user_language(user_id)
    from bot.keyboards import terms_keyboard, subscription_check_keyboard
    
    # 1. Сначала Соглашение
    accepted = await db.get_user_accepted_terms(user_id)
    if not accepted:
        text = get_string("start_welcome", lang)
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(text, reply_markup=terms_keyboard(lang))
        else:
            await _replace_with_text(message_or_callback, text, reply_markup=terms_keyboard(lang))
        return False
        
    # 2. Потом Подписка
    channel_id = await db.get_app_setting("required_channel_id")
    if channel_id:
        is_subbed = await _check_subscription(user_id, bot, db)
        if not is_subbed:
            channel_url = await db.get_app_setting("required_channel_url", "https://t.me/bnbslow")
            text = get_string("subscribe_channel", lang)
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(text, reply_markup=subscription_check_keyboard(channel_url, lang))
            else:
                await _replace_with_text(message_or_callback, text, reply_markup=subscription_check_keyboard(channel_url, lang))
            return False
            
    return True

@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    user = message.from_user
    await db.upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    lang = await db.get_user_language(user.id)
    await message.answer(get_string("main_menu_title", lang), reply_markup=main_menu_keyboard(lang))


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
    # Блокировка пользователя
    if await db.get_user_blocked(callback.from_user.id):
        await _safe_answer(callback, get_string("maintenance_alert", lang), show_alert=True)
        return
    if balance <= 0:
        await _safe_answer(callback, get_string("limit_rem_zero", lang), show_alert=True)
        return
    
    # Обычная генерация теперь сразу просит фото
    await state.clear()
    await state.update_data(category="random", random_mode=True, normal_gen_mode=True)
    # Устанавливаем дефолтные параметры для обычной генерации
    await state.update_data(
        rand_gender="unisex",
        height="170",
        age="25",
        view="front",
        aspect="auto"
    )
    
    text = get_string("upload_photo", lang)
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
    if balance <= 0:
        await _safe_answer(callback, get_string("limit_rem_zero", lang), show_alert=True)
        return
    
    statuses = await db.list_categories_enabled()
    from bot.keyboards import marketplace_menu_keyboard
    await _replace_with_text(callback, get_string("marketplace_menu", lang), reply_markup=marketplace_menu_keyboard(statuses, lang))
    await _safe_answer(callback)


@router.callback_query(F.data == "create_cat:presets")
async def on_ready_presets(callback: CallbackQuery, db: Database) -> None:
    enabled = await db.list_categories_enabled()
    logger.info(f"Presets menu accessed. Categories status: {enabled}") # Отладочный лог
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import ready_presets_keyboard
    await _replace_with_text(callback, get_string("cat_presets", lang), reply_markup=ready_presets_keyboard(enabled, lang))
    await _safe_answer(callback)

@router.callback_query(F.data == "create_cat:female")
async def on_female_category(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
    if not await db.get_category_enabled("female"):
        await _safe_answer(callback, get_string("no_models_in_category_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
        return
    
    await state.clear()
    await state.update_data(category="female", cloth="all", is_preset=True)
    lang = await db.get_user_language(callback.from_user.id)
    
    # СРАЗУ к возрасту (п. 1.1)
    from bot.keyboards import form_age_keyboard
    await _replace_with_text(callback, get_string("select_age", lang), reply_markup=form_age_keyboard(lang))
    await state.set_state(CreateForm.waiting_age)
    await _safe_answer(callback)

@router.callback_query(F.data == "create_cat:male")
async def on_male_category(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
    if not await db.get_category_enabled("male"):
        await _safe_answer(callback, get_string("no_models_in_category_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
        return
    
    await state.clear()
    await state.update_data(category="male", cloth="all", is_preset=True)
    lang = await db.get_user_language(callback.from_user.id)
    
    # СРАЗУ к возрасту (п. 1.1)
    from bot.keyboards import form_age_keyboard
    await _replace_with_text(callback, get_string("select_age", lang), reply_markup=form_age_keyboard(lang))
    await state.set_state(CreateForm.waiting_age)
    await _safe_answer(callback)

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
        await _answer_model_photo(callback, model[3], text, kb)
    else:
        await _replace_with_text(callback, text, reply_markup=kb)

@router.callback_query(F.data == "create_cat:child")
async def on_child_category(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
    if not await db.get_category_enabled("child"):
        await _safe_answer(callback, get_string("no_models_in_category_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
        return
    await state.update_data(category="child")
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=child_gender_keyboard(lang))
    await _safe_answer(callback)
@router.callback_query(F.data == "create_random")
async def on_create_random(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    # Проверка, что категория включена
    if not await db.get_category_enabled("random"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    await state.clear()
    await state.update_data(random_mode=True, category="random")
    lang = await db.get_user_language(callback.from_user.id)
    
    # 1. Тип локации
    from bot.keyboards import random_loc_group_keyboard
    await _replace_with_text(callback, get_string("select_loc_group", lang), reply_markup=random_loc_group_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_loc_group)
    await _safe_answer(callback)

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
    await state.set_state(None) # Обработает rand_gender:
    await _safe_answer(callback)

@router.message(CreateForm.waiting_custom_location)
async def on_random_location_custom_msg(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    await state.update_data(rand_location_custom=text, rand_location="custom")
    lang = await db.get_user_language(message.from_user.id)
    # 2. Пол
    await message.answer(get_string("select_model_gender", lang), reply_markup=random_gender_keyboard(lang))
    await state.set_state(None)

@router.callback_query(F.data.startswith("rand_gender:"))
async def on_random_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    gender = callback.data.split(":")[1]
    await state.update_data(rand_gender=gender)
    lang = await db.get_user_language(callback.from_user.id)
    
    # 2.1 Если юзер выбирает Женский/Мужской то мы уточняем возраст
    if gender in ("male", "female"):
        from bot.keyboards import form_age_keyboard
        await _replace_with_text(callback, get_string("select_age", lang), reply_markup=form_age_keyboard(lang))
        await state.set_state(CreateForm.waiting_age)
    else:
        # Для мальчик/девочка сразу к размеру
        from bot.keyboards import form_size_keyboard
        await _replace_with_text(callback, get_string("select_body_type", lang), reply_markup=form_size_keyboard(gender, lang))
        await state.set_state(CreateForm.waiting_size)
    await _safe_answer(callback)


@router.callback_query(F.data == "create_random_other")
async def on_create_random_other(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
    # Проверка, что категория включена
    if not await db.get_category_enabled("random_other"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    await state.clear()
    await state.update_data(random_other_mode=True, category="random_other")
    lang = await db.get_user_language(callback.from_user.id)
    
    # Сначала спрашиваем Присутствие человека
    await _replace_with_text(callback, get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_has_person)
    await _safe_answer(callback)

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
async def on_rand_other_name(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if not text or len(text) > 50:
        await message.answer("⚠️ Название слишком длинное (максимум 50 символов). Попробуйте еще раз:")
        return
    await state.update_data(product_name=text)
    from bot.keyboards import form_view_keyboard
    await message.answer("Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
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
        from bot.keyboards import aspect_ratio_keyboard
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_rand_other_style_custom)
async def on_rand_other_style_custom(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    await state.update_data(style=text)
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    await state.set_state(CreateForm.waiting_aspect)


@router.callback_query(F.data == "create_cat:storefront")
async def on_storefront_category(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
    if not await db.get_category_enabled("storefront"):
        await _safe_answer(callback, get_string("no_models_in_category_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
        return
    await state.clear()
    await state.update_data(category="storefront", storefront_mode=True)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import gender_selection_keyboard
    await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=gender_selection_keyboard("storefront", lang, back_data="menu_market"))
    await _safe_answer(callback)


@router.callback_query(F.data == "create_cat:whitebg")
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
    # Если их нет — показываем модели из соответствующей общей категории (женская/мужская/детская)
    if category == "storefront":
        total_sf = await db.count_models("storefront", gender)
        if total_sf > 0:
            await _show_models_for_category(callback, db, "storefront", gender)
        else:
            # Fallback к общей категории пола (женская/мужская/детская), но logic_category остается storefront
            display_cat = "child" if gender in ("boy", "girl") else gender
            cloth_val = gender if display_cat == "child" else "all"
            await _show_models_for_category(callback, db, display_cat, cloth_val, logic_category="storefront")
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


@router.callback_query(F.data.startswith("create_cat:infographic_"))
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
        # Для одежды спрашиваем пол (подразумеваем наличие человека)
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
    data = await state.get_data()
    
    if data.get("random_mode"):
        # Одежда и обувь РАНДОМ: сразу к локации
        from bot.keyboards import random_loc_group_keyboard
        await _replace_with_text(callback, get_string("select_loc_group", lang), reply_markup=random_loc_group_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_loc_group)
    else:
        # Для всей инфографики (и одежда, и прочее) — спрашиваем возраст (п. 2)
        await _replace_with_text(callback, "🔢 Введите возраст модели:", reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_age)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_info_age)
async def on_info_age(message: Message, state: FSMContext, db: Database) -> None:
    age_text = (message.text or "").strip()
    await state.update_data(age=age_text)
    lang = await db.get_user_language(message.from_user.id)
    # Далее Нагруженность инфографики (п. 3)
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

    if data.get("random_mode"):
        # Если это режим Рандом (одежда) — далее локация
        from bot.keyboards import random_loc_group_keyboard
        await message.answer(get_string("select_loc_group", lang), reply_markup=random_loc_group_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_loc_group)
    elif data.get("random_other_mode"):
        # Рандом для остальных товаров — Название продукта (п. 3)
        await message.answer(get_string("enter_product_name", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_name)
    else:
        # Для инфографики (и одежда, и прочее) — выбор языка (п. 4 в списке пользователя)
        from bot.keyboards import info_lang_keyboard
        await message.answer(get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_lang)

@router.callback_query(F.data == "info_load:skip")
async def on_infographic_load_skip_btn(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.update_data(info_load="")
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    if data.get("random_mode"):
        from bot.keyboards import random_loc_group_keyboard
        await _replace_with_text(callback, get_string("select_loc_group", lang), reply_markup=random_loc_group_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_loc_group)
    elif data.get("random_other_mode"):
        # Рандом для остальных товаров — Название продукта
        await _replace_with_text(callback, get_string("enter_product_name", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_name)
    else:
        # Выбор языка
        from bot.keyboards import info_lang_keyboard
        await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_lang)
    await _safe_answer(callback)


@router.callback_query(F.data == "back_step", CreateForm.waiting_info_age)
async def on_back_from_info_age(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    # Возврат к выбору пола
    from bot.keyboards import infographic_gender_keyboard
    back_data = "create_cat:infographics" if data.get("category") == "infographic_clothing" else None
    await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang, back_data=back_data))
    await state.set_state(CreateForm.waiting_info_gender)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_load)
async def on_back_from_info_load(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Возврат к вводу возраста
    await _replace_with_text(callback, "🔢 Введите возраст модели:", reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_age)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_lang)
async def on_back_from_info_lang(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Возврат к нагрузке (load)
    await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=skip_step_keyboard("info_load", lang))
    await state.set_state(CreateForm.waiting_info_load)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_lang_custom)
@router.callback_query(F.data == "back_step", CreateForm.waiting_info_brand)
async def on_back_from_info_brand(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Возврат к выбору языка
    from bot.keyboards import info_lang_keyboard
    await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_lang)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_loc_group)
async def on_back_from_rand_loc_group(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Возвращаемся к нагрузке инфографики
    from bot.keyboards import skip_step_keyboard
    await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=skip_step_keyboard("info_load", lang))
    await state.set_state(CreateForm.waiting_info_load)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_adv1)
async def on_back_from_info_adv1(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_info_brand", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_brand)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_adv2)
async def on_back_from_info_adv2(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_adv1_skip", lang), reply_markup=skip_step_keyboard("info_adv1", lang))
    await state.set_state(CreateForm.waiting_info_adv1)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_adv3)
async def on_back_from_info_adv3(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_adv2_skip", lang), reply_markup=skip_step_keyboard("info_adv2", lang))
    await state.set_state(CreateForm.waiting_info_adv2)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_extra)
async def on_back_from_info_extra(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_adv3_skip", lang), reply_markup=skip_step_keyboard("info_adv3", lang))
    await state.set_state(CreateForm.waiting_info_adv3)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_angle)
async def on_back_from_info_angle(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    if data.get("category") == "infographic_clothing":
        from bot.keyboards import sleeve_length_keyboard
        # Для одежды возврат к рукаву
        await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))
        await state.set_state(CreateForm.waiting_sleeve)
        await _safe_answer(callback)
        return

    await _replace_with_text(callback, get_string("enter_extra_info_skip", lang), reply_markup=skip_step_keyboard("info_extra", lang))
    await state.set_state(CreateForm.waiting_info_extra)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_pose)
async def on_back_from_info_pose(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Возврат к ракурсу (dist)
    from bot.keyboards import angle_keyboard
    await _replace_with_text(callback, "Выберите ракурс фотографии (Дальний/Средний/Близкий):", reply_markup=angle_keyboard(lang))
    await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_season)
async def on_back_from_info_season(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Возврат к ракурсу (dist) или позе (если есть)
    from bot.keyboards import angle_keyboard
    await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=angle_keyboard(lang))
    await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_holiday)
async def on_back_from_info_holiday(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    # Возврат к сезону
    from bot.keyboards import random_season_keyboard
    await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_season)
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
        from bot.keyboards import form_size_keyboard
        gender = data.get("info_gender") or data.get("category") or "female"
        await message.answer(get_string("select_body_type", lang), reply_markup=form_size_keyboard(gender, lang))
        await state.set_state(CreateForm.waiting_size)

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
        from bot.keyboards import form_size_keyboard
        gender = data.get("info_gender") or data.get("category") or "female"
        await _replace_with_text(callback, get_string("select_body_type", lang), reply_markup=form_size_keyboard(gender, lang))
        await state.set_state(CreateForm.waiting_size)
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
@router.callback_query(F.data == "create_cat:own")
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
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("upload_model_photo", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_ref_photo)
    await _safe_answer(callback)


# Own Background Variant Flow
@router.callback_query(F.data == "create_cat:own_variant")
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
    # СРАЗУ к параметрам (рукава), а фото переносим в конец
    await _ask_sleeve_length(callback, state, db)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_own_bg_photo, F.photo)
async def on_own_bg_photo(message: Message, state: FSMContext, db: Database) -> None:
    photo_id = message.photo[-1].file_id
    await state.update_data(own_bg_photo_id=photo_id)
    lang = await db.get_user_language(message.from_user.id)
    # После фото фона просим фото ТОВАРА
    await message.answer(get_string("upload_product", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_own_product_photo)

@router.message(CreateForm.waiting_own_product_photo, F.photo)
async def on_own_variant_product_photo(message: Message, state: FSMContext, db: Database) -> None:
    photo_id = message.photo[-1].file_id
    await state.update_data(own_product_photo_id=photo_id)
    lang = await db.get_user_language(message.from_user.id)
    # Финальный шаг — ФОРМАТ
    from bot.keyboards import aspect_ratio_keyboard
    await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    await state.set_state(CreateForm.waiting_aspect)


@router.message(CreateForm.waiting_prompt, F.text)
async def on_prompt_input(message: Message, state: FSMContext, db: Database) -> None:
    prompt = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if len(prompt) > 1000:
        await message.answer(get_string("enter_prompt_error", lang), reply_markup=back_step_keyboard(lang))
        return
    
    await state.update_data(prompt=prompt)
    await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    await state.set_state(CreateForm.waiting_aspect)


@router.callback_query(F.data == "back_step", CreateForm.waiting_prompt)
async def on_back_from_prompt(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_main_keyboard(lang))
    await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_aspect, F.data.startswith("form_aspect:"))
@router.callback_query(CreateForm.waiting_aspect, F.data.startswith("form_aspect:"))
async def on_aspect_selected(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    aspect = callback.data.split(":", 1)[1]
    await state.update_data(aspect=aspect)
    
    data = await state.get_data()
    category = data.get("category")
    lang = await db.get_user_language(callback.from_user.id)
    parts = ["📋 Проверьте выбранные параметры:\n\n"]
    
    if data.get("normal_gen_mode"):
        parts.append("📦 **Категория**: ✨ ОБЫЧНАЯ ГЕНЕРАЦИЯ\n")
        parts.append(f"📝 **Промпт**: {data.get('prompt', '—')}\n")
    
    elif category == "own_variant" or data.get("category") == "own_variant":
        parts.append("📦 **Категория**: 🖼️ Свой вариант ФОНА\n")
        parts.append(f"🧥 **Длина рукав**: {data.get('own_sleeve', '—')}\n")
        parts.append(f"📏 **Длина изделия**: {data.get('own_length', '—')}\n")
    
    elif category == "random_other" or data.get("random_other_mode"):
        parts.append("📦 **Категория**: 📦 Рандом для остальных видов товара\n")
        has_person = "Да" if data.get("has_person") else "Нет"
        parts.append(f"👤 **Человек**: {has_person}\n")
        if data.get("has_person"):
            parts.append(f"📊 **Нагруженность**: {data.get('info_load', '—')}\n")
            parts.append(f"📝 **Название**: {data.get('product_name', '—')}\n")
            view_map = {"front": "Спереди", "back": "Сзади"}
            parts.append(f"👀 **Угол**: {view_map.get(data.get('view'), '—')}\n")
            dist_map = {"close": "Близкий", "far": "Дальний", "medium": "Средний"}
            parts.append(f"📏 **Ракурс**: {dist_map.get(data.get('dist'), '—')}\n")
            dims = f"{data.get('height_cm', '—')}x{data.get('width_cm', '—')}x{data.get('length_cm', '—')}"
            parts.append(f"📐 **ВxШxД**: {dims} см\n")
            parts.append(f"⏳ **Сезон**: {data.get('season', '—')}\n")
            parts.append(f"🎨 **Стиль**: {data.get('style', '—')}\n")
    
    elif category == "own" or data.get("own_mode"):
        parts.append("📦 **Категория**: ✨ Свой вариант МОДЕЛИ\n")
        parts.append(f"🧥 **Длина рукав**: {data.get('own_sleeve', '—')}\n")
        parts.append(f"📏 **Длина изделия**: {data.get('own_length', '—')}\n")
        
    elif data.get("infographic_mode"):
        parts.append(f"📦 **Категория**: 📊 Инфографика ({category})\n")
        
        has_person = "Да" if data.get("has_person") else "Нет"
        parts.append(f"👤 **Человек**: {has_person}\n")
        if data.get("has_person"):
            parts.append(f"🚻 **Пол**: {data.get('info_gender', '—')}\n")
            parts.append(f"🔢 **Возраст**: {data.get('age', '—')}\n")
            parts.append(f"🧘 **Поза**: {data.get('info_pose', '—')}\n")

        parts.append(f"📊 **Нагруженность**: {data.get('info_load', '—')}/10\n")
        parts.append(f"🌐 **Язык**: {data.get('info_lang', '—')}\n")
        parts.append(f"📝 **Бренд/Название**: {data.get('info_brand', '—')}\n")
        adv = f"{data.get('info_adv1', '')} {data.get('info_adv2', '')} {data.get('info_adv3', '')}".strip() or "—"
        parts.append(f"✨ **Преимущества**: {adv}\n")
        parts.append(f"➕ **Доп. инфо**: {data.get('info_extra', '—')}\n")
        
        view_map = {"front": "Спереди", "back": "Сзади"}
        parts.append(f"👀 **Угол**: {view_map.get(data.get('info_angle'), '—')}\n")
        parts.append(f"📏 **Ракурс**: {data.get('info_dist', '—')}\n")
        
        if category == "infographic_clothing":
            parts.append(f"📐 **Телосложение**: {data.get('size', '—')}\n")
            parts.append(f"📏 **Рост**: {data.get('height', '—')} см\n")
            parts.append(f"✂️ **Крой**: {data.get('pants_style', '—')}\n")
            parts.append(f"🧥 **Рукав**: {data.get('sleeve', '—')}\n")
            parts.append(f"👗 **Длина**: {data.get('length', '—')}\n")
        
        if category == "infographic_other":
            parts.append(f"⏳ **Сезон**: {data.get('info_season', '—')}\n")
            parts.append(f"🎉 **Праздник**: {data.get('info_holiday', '—')}\n")
        
    elif category == "whitebg":
        parts.append("📦 **Категория**: ⚪ На белом фоне\n")
    
    elif category == "storefront":
        parts.append("📦 **Категория**: 📸 Витринное фото\n")
        view_map = {"front": "Спереди", "back": "Сзади"}
        parts.append(f"👀 **Угол**: {view_map.get(data.get('view'), '—')}\n")
        parts.append(f"📏 **Ракурс**: {data.get('dist', '—')}\n")
        parts.append(f"👗 **Длина**: {data.get('own_length', '—')}\n")
            
    elif data.get("random_mode"):
        parts.append("📦 **Категория**: 🎨 Рандом (Одежда)\n")
        gender_map = {"male":"Мужчина","female":"Женщина","boy":"Мальчик","girl":"Девочка"}
        parts.append(f"🚻 **Пол**: {gender_map.get(data.get('rand_gender'), '—')}\n")
        
        loc_map = {"inside_restaurant":"В ресторане","photo_studio":"В фотостудии","coffee_shop":"В кофейне","city":"В городе","building":"У здания","wall":"У стены","park":"В парке","coffee_shop_out":"У кофейни","forest":"В лесу","car":"У машины"}
        location = data.get("rand_location")
        if location == "custom":
            parts.append(f"📍 **Локация**: {data.get('rand_location_custom', '—')}\n")
        else:
            parts.append(f"📍 **Локация**: {loc_map.get(location, location or '—')}\n")

        parts.append(f"🎂 **Возраст**: {data.get('age', '—')}\n")
        parts.append(f"📏 **Рост**: {data.get('height', '—')} см\n")
        parts.append(f"📐 **Телосложение**: {data.get('size', '—')}\n")
        parts.append(f"✂️ **Крой**: {data.get('pants_style', '—')}\n")
        parts.append(f"🧥 **Рукав**: {data.get('sleeve', '—')}\n")
        parts.append(f"👗 **Длина**: {data.get('length', '—')}\n")
        parts.append(f"🧘 **Поза**: {data.get('pose', '—')}\n")
        parts.append(f"📏 **Ракурс**: {data.get('dist', '—')}\n")
        parts.append(f"👀 **Вид**: {data.get('view', '—')}\n")
        parts.append(f"⏳ **Сезон**: {data.get('season', '—')}\n")
        parts.append(f"🎉 **Праздник**: {data.get('holiday', '—')}\n")
            
        vibe_map = {"summer":"Лето","winter":"Зима","autumn":"Осень","spring":"Весна"}
        parts.append(f"🎞 **Вайб**: {vibe_map.get(data.get('rand_vibe'), data.get('rand_vibe', '—'))}\n")
        
        view_map = {"close": "Близкий", "far": "Дальний", "medium": "Средний", "front": "Спереди", "back": "Сзади", "side": "Сбоку"}
        parts.append(f"👀 **Ракурс**: {view_map.get(data.get('view'), 'Средний')}\n")

    else:
        # Обычная модель (Пресеты)
        cat_name = "Женская" if category == "female" else "Мужская" if category == "male" else "Детская" if category == "child" else category
        parts.append(f"📦 **Категория**: {cat_name}\n")
        
        if not data.get("is_preset"):
            parts.append(f"👕 **Тип одежды**: {data.get('cloth', '—')}\n")
        
        age_map = {"20_26": "20-26 лет", "30_38": "30-38 лет", "40_48": "40-48 лет", "55_60": "55-60 лет"}
        if data.get("age"):
            parts.append(f"🎂 **Возраст**: {age_map.get(data.get('age'), data.get('age', '—'))}\n")
            
        parts.append(f"📐 **Телосложение**: {data.get('size', '—')}\n")
        parts.append(f"📏 **Рост**: {data.get('height', '—')} см\n")
        parts.append(f"✂️ **Крой**: {data.get('pants_style', '—')}\n")
        parts.append(f"🧥 **Рукав**: {data.get('sleeve', '—')}\n")
        parts.append(f"👗 **Длина**: {data.get('length', '—')}\n")
        parts.append(f"🧘 **Поза**: {data.get('pose', '—')}\n")
        parts.append(f"📏 **Ракурс**: {data.get('dist', '—')}\n")
        parts.append(f"👀 **Вид**: {data.get('view', '—')}\n")
        parts.append(f"⏳ **Сезон**: {data.get('season', '—')}\n")

    parts.append(f"🖼️ **Формат**: {aspect.replace('x', ':')}\n\n")
    parts.append("Все верно? Нажмите кнопку ниже для генерации.")
    
    await _replace_with_text(callback, "".join(parts), reply_markup=form_generate_keyboard())
    await _safe_answer(callback)


@router.message(CreateForm.waiting_ref_photo, F.photo)
async def on_own_ref_photo(message: Message, state: FSMContext, db: Database) -> None:
    ref_id = message.photo[-1].file_id
    await state.update_data(own_ref_photo_id=ref_id)
    lang = await db.get_user_language(message.from_user.id)
    await state.set_state(CreateForm.waiting_product_photo)
    await message.answer(get_string("upload_product", lang), reply_markup=back_step_keyboard(lang))


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
    await _replace_with_text(callback, "Введите возраст модели (числом лет) или нажмите 'Пропустить':", reply_markup=random_skip_keyboard())
    await state.set_state(CreateForm.random_dummy)
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
        await _answer_model_photo(
            callback,
            model[3],
            text,
            model_select_keyboard(category, cloth, 0, total, lang),
        )
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
    
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    # Витринное фото (НОВЫЙ ФЛОУ)
    if category == "storefront" or data.get("storefront_mode"):
        await _replace_with_text(callback, get_string("select_camera_angle", lang), reply_markup=form_view_keyboard(lang))
        await state.set_state(CreateForm.waiting_preset_view)
        await _safe_answer(callback)
        return

    # 1. Возраст (для обычных пресетов)
    if category in ("female", "male"):
        await _replace_with_text(callback, get_string("select_age", lang), reply_markup=form_age_keyboard(lang))
        await state.set_state(CreateForm.waiting_age)
    else:
        # Для детей пропускаем возраст, сразу к телосложению
        await _replace_with_text(callback, get_string("select_body_type", lang), reply_markup=form_size_keyboard(category, lang))
        await state.set_state(CreateForm.waiting_size)
        
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
            await _replace_with_text(callback, get_string("select_body_type", lang), reply_markup=form_size_keyboard(category, lang))
            await state.set_state(CreateForm.waiting_size)
    
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
async def on_plus_vibe(callback: CallbackQuery, state: FSMContext) -> None:
    vibe = callback.data.split(":", 1)[1]
    await state.update_data(plus_vibe=vibe)
    # после вайба — возраст для взрослых
    await _replace_with_text(callback, "🎂 Пожалуйста выберите возраст модели:", reply_markup=form_age_keyboard())
    await state.set_state(CreateForm.waiting_age)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_age, F.data.startswith("form_age:"))
async def form_set_age(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    if not data:
        await _safe_answer(callback)
        return
    
    age_key = callback.data.split(":", 1)[1]
    await state.update_data(age=age_key)
    
    # 2. Телосложение (Размер)
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")
    await _replace_with_text(callback, get_string("select_body_type", lang), reply_markup=form_size_keyboard(category, lang))
    await state.set_state(CreateForm.waiting_size)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_age)
async def form_set_age_message(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    if not data:
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите возраст числом, например: 7")
        return
    category = data.get("category")
    if category == "child":
        if text.lower() in ("пропустить", "skip"):
            await state.update_data(age="")
        else:
            digits = ''.join(ch for ch in text if ch.isdigit())
            if not digits:
                await message.answer("Введите возраст числом, например: 7 или отправьте 'Пропустить'")
                return
            await state.update_data(age=f"{digits} лет")
        # После возраста — для детской одежды тоже спрашиваем длину изделия (кроме обуви)
        cloth = data.get("cloth")
        lang = await db.get_user_language(message.from_user.id)
        if cloth == "shoes":
            await state.set_state(CreateForm.waiting_view)
            await message.answer(get_string("select_camera_dist", lang), reply_markup=form_view_keyboard(lang))
        else:
            await _ask_garment_length(message, state, db)
    else:
        # Взрослые: после возраста — к выбору телосложения
        await state.set_state(CreateForm.waiting_size)
        await message.answer("Выберите телосложение:", reply_markup=form_size_keyboard(data.get("category")))


@router.callback_query(CreateForm.waiting_size, F.data.startswith("form_size:"))
async def form_set_size(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    category = data.get("category")
    gender = data.get("info_gender") or category
    
    # Маппинг телосложения
    size_map = {
        "thin": "Худая и стройная",
        "curvy": "Телосложение пышное и полные ноги пухлое лицо.",
        "plus": "Size Plus очень крупное и пышное телосложение полные ноги и круглое и пухлое лицо.",
    }
    if gender == "male":
        size_map = {
            "thin": "Худой и стройный",
            "curvy": "Телосложение пышное и полные ноги, пухлое лицо.",
            "plus": "Size Plus очень крупное и пышное телосложение, полные ноги и круглое пухлое лицо.",
        }
    elif gender == "boy":
        size_map = {
            "thin": "Худой и стройный мальчик",
            "curvy": "Крепкий и пышный мальчик",
            "plus": "Крупный мальчик",
        }
    elif gender == "girl":
        size_map = {
            "thin": "Худая и стройная девочка",
            "curvy": "Пышная девочка",
            "plus": "Крупная девочка",
        }
    
    await state.update_data(size=size_map.get(val, ""))
    
    lang = await db.get_user_language(callback.from_user.id)
    # После телосложения — к РОСТУ (п. 4)
    await _replace_with_text(callback, get_string("enter_height", lang))
    await state.set_state(CreateForm.waiting_height)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_height)
async def form_set_height(message: Message, state: FSMContext, db: Database) -> None:
    text = message.text.strip()
    # простая валидация числа
    digits = ''.join(ch for ch in text if ch.isdigit())
    if not digits:
        await message.answer("Введите число, например: 170")
        return
    height = int(digits)
    await state.update_data(height=height)
    data = await state.get_data()
    lang = await db.get_user_language(message.from_user.id)
    
    # 5. Тип кроя штанов
    from bot.keyboards import pants_style_keyboard
    await message.answer(get_string("select_pants_style", lang), reply_markup=pants_style_keyboard(lang))
    await state.set_state(CreateForm.waiting_pants_style)


@router.callback_query(F.data.startswith("garment_len:"))
async def on_garment_len_callback(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    
    if val == "custom":
        await _replace_with_text(callback, get_string("enter_length_custom", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_length)
        await _safe_answer(callback)
        return

    # Маппинг значений для промпта
    len_map = {
        "short_top": "Короткий топ", "regular_top": "Обычный топ",
        "to_waist": "До талии", "below_waist": "Ниже талии",
        "mid_thigh": "До середины бедра", "to_knees": "До колен",
        "below_knees": "Ниже колен", "midi": "Миди",
        "to_ankles": "До щиколоток", "to_floor": "До пола",
        "skip": ""
    }
    
    length_text = len_map.get(val, "")
    await state.update_data(length=length_text)
    
    # Фолбэк для own_mode или own_variant или storefront или инфографика
    if data.get("own_mode") or data.get("category") == "own_variant" or data.get("category") == "storefront" or data.get("infographic_mode"):
        await state.update_data(own_length=length_text)

        # Для всех (включая Свой вариант фона) теперь только ОДНО фото товара в конце
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]])
        await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_kb)
        await state.set_state(CreateForm.waiting_view)
        await _safe_answer(callback)
        return

    # Для пресетов и Рандом Одежда: после длины — к позе (п. 9)
    if (data.get("category") in ("female", "male", "child") or data.get("random_mode")) and not data.get("infographic_mode"):
        await state.set_state(CreateForm.waiting_preset_pose)
        await _replace_with_text(callback, "Выберите тип позы:", reply_markup=pose_keyboard(lang))
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
    sleeve_map = {
        "normal": "Обычный",
        "long": "Длинные",
        "three_quarter": "Три четверти",
        "elbow": "До локтей",
        "short": "Короткие",
        "none": "Без рукав",
        "skip": "",
    }
    sleeve_text = sleeve_map.get(val, "")
    await state.update_data(sleeve=sleeve_text)
    
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    
    # Для всех режимов "Свой вариант" после рукава переходим к ракурсу или сразу к формату
    if data.get("own_mode") or data.get("category") == "own_variant":
        await state.update_data(own_sleeve=sleeve_text)
        # Для "Своего варианта" тоже можно спросить ракурс (Близкий/Дальний/Средний)
        await state.set_state(CreateForm.waiting_view)
        await _replace_with_text(callback, "👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard(lang))
        await _safe_answer(callback)
        return

    # Инфографика одежда (п. 11)
    if data.get("infographic_mode") and data.get("category") == "infographic_clothing":
        await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_angle)
        await _safe_answer(callback)
        return

    # Пресеты (Готовые модели) - ПЕРЕХОД К ДЛИНЕ ИЗДЕЛИЯ
    if data.get("category") in ("female", "male", "child") and not data.get("random_mode") and not data.get("infographic_mode"):
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
    current_state = await state.get_state()

    # Если мы в промежуточном состоянии выбора ракурса (для инфографики)
    if current_state == CreateForm.waiting_info_angle.state:
        await state.update_data(info_angle=view)
        # Далее Ракурс (Дальний/Средний/Близкий) - angle_keyboard
        await _replace_with_text(callback, "Выберите ракурс (Дальний/Средний/Близкий):", reply_markup=angle_keyboard(lang))
        await state.set_state(CreateForm.waiting_view)
        await _safe_answer(callback)
        return

    # Для "Своего варианта"
    if data.get("own_mode") or data.get("category") == "own_variant":
        await state.update_data(view=view)
        # Если это первый выбор ракурса в начале флоу
        if current_state == CreateForm.waiting_view.state and not data.get("own_product_photo_id"):
            if data.get("category") == "own_variant":
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

    # Стандартная логика: сохраняем ракурс и сразу просим фото
    await state.update_data(view=view)
    text = (
        "📸 Пожалуйста пришлите фотографию вашего товара.\n\n"
        "⚠️ Обратите внимание: фотография должна быть четкой без лишних бликов и размытостей.\n\n"
        "Если остались вопросы - пишите в поддержку @bnbslow"
    )
    
    # Проверка на дубликат сообщения (чтобы не отправлять дважды)
    if callback.message.text and "📸 Пожалуйста пришлите фотографию" in callback.message.text:
        await _safe_answer(callback)
        return

    await state.set_state(CreateForm.waiting_view)
    await _replace_with_text(callback, text)
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

@router.callback_query(CreateForm.waiting_preset_dist, F.data.startswith("form_dist:") | F.data.startswith("angle:"))
@router.callback_query(CreateForm.waiting_view, F.data.startswith("form_dist:") | F.data.startswith("angle:"))
@router.callback_query(CreateForm.waiting_rand_other_dist, F.data.startswith("form_dist:") | F.data.startswith("angle:"))
async def on_dist_selected(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    dist_map = {"far": "Дальний", "medium": "Средний", "close": "Близкий", "skip": ""}
    dist_val = dist_map.get(val, val)
    
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    current_state = await state.get_state()

    # Инфографика (waiting_view + infographic_mode)
    if data.get("infographic_mode") and current_state == CreateForm.waiting_view.state:
        await state.update_data(info_dist=dist_val)
        
        # Для всей инфографики (и одежда, и прочее): Поза (если есть человек)
        if data.get("has_person"):
            from bot.keyboards import pose_keyboard
            await _replace_with_text(callback, "Выберите позу модели:", reply_markup=pose_keyboard(lang))
            await state.set_state(CreateForm.waiting_info_pose)
        else:
            # Если нет человека:
            if data.get("category") == "infographic_other":
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

    # Остальные (Пресеты, Витрина и т.д.)
    await state.update_data(dist=dist_val)
    
    # Витринное фото
    if data.get("category") == "storefront":
        await _ask_garment_length(callback, state, db)
        await _safe_answer(callback)
        return

    # Готовые пресеты -> Вид (Спереди/Сзади)
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
    
    # Теперь для всех (Пресеты, Рандом) — просим фото в конце (п. 1.1)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]])
    await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_kb)
    await state.set_state(CreateForm.waiting_view)
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
    
    # Праздник — финальный шаг в Рандоме. Теперь просим фото (п. 1.1)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]])
    await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_kb)
    await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_info_pose, F.data.startswith("pose:"))
async def on_info_pose(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    pose = callback.data.split(":", 1)[1]
    await state.update_data(info_pose=pose)
    lang = await db.get_user_language(callback.from_user.id)
    
    data = await state.get_data()
    if data.get("infographic_mode") and data.get("category") == "infographic_clothing":
        # Для инфографики одежда: после позы — к длине изделия (п. 14)
        await _ask_garment_length(callback, state, db)
    elif data.get("infographic_mode") and data.get("category") == "infographic_other":
        # Для инфографики прочее: после позы — к сезону
        from bot.keyboards import random_season_keyboard
        await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_season)
    elif data.get("category") in ("female", "male", "child") and not data.get("random_mode") and not data.get("infographic_mode"):
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



@router.message(CreateForm.waiting_view, F.photo)
async def handle_user_photo(message: Message, state: FSMContext, db: Database) -> None:
    # Защита от двойного срабатывания при отправке альбомов
    data = await state.get_data()
    if not data:
        return
    
    # Проверяем, не перешли ли мы уже в другое состояние
    current_state = await state.get_state()
    if current_state != CreateForm.waiting_view.state:
        return
            
    photo_id = message.photo[-1].file_id
    await state.update_data(user_photo_id=photo_id)
    lang = await db.get_user_language(message.from_user.id)

    # ДЛЯ ВСЕХ РЕЖИМОВ: фото — это ПОСЛЕДНИЙ шаг перед форматом
    from bot.keyboards import aspect_ratio_keyboard
    await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    await state.set_state(CreateForm.waiting_aspect)


@router.callback_query(F.data == "back_step", CreateForm.waiting_size)
async def on_back_from_size(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    
    if data.get("random_mode"):
        # Рандом: возврат к возрасту (для м/ж) или к полу (для детей)
        gender = data.get("rand_gender")
        if gender in ("male", "female"):
            from bot.keyboards import form_age_keyboard
            await _replace_with_text(callback, get_string("select_age", lang), reply_markup=form_age_keyboard(lang))
            await state.set_state(CreateForm.waiting_age)
        else:
            await _replace_with_text(callback, get_string("select_model_gender", lang), reply_markup=random_gender_keyboard(lang))
            await state.set_state(None)
        await _safe_answer(callback)
        return

    if data.get("infographic_mode"):
        # Для инфографики возврат к доп. инфо
        await _replace_with_text(callback, get_string("enter_extra_info_skip", lang), reply_markup=skip_step_keyboard("info_extra", lang))
        await state.set_state(CreateForm.waiting_info_extra)
        await _safe_answer(callback)
        return

    if data.get("is_preset"):
        category = data.get("category")
        if category == "child":
            # Для детей назад к выбору пола в пресетах
            await on_ready_presets(callback, db)
            return
        else:
            # Для м/ж назад к возрасту
            from bot.keyboards import form_age_keyboard
            await _replace_with_text(callback, get_string("select_age", lang), reply_markup=form_age_keyboard(lang))
            await state.set_state(CreateForm.waiting_age)
            await _safe_answer(callback)
            return

    category = data.get("category")
    cloth = data.get("cloth")
    index = data.get("index", 0)
    await _show_models_for_category(callback, db, category, cloth, index)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_age)
async def on_back_from_age(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    category = data.get("category")
    lang = await db.get_user_language(callback.from_user.id)
    
    if data.get("random_mode"):
        # Рандом: возврат к выбору пола
        await _replace_with_text(callback, get_string("select_model_gender", lang), reply_markup=random_gender_keyboard(lang))
        await state.set_state(None)
        await _safe_answer(callback)
        return

    if data.get("is_preset"):
        # Для пресетов назад к выбору пола
        await on_ready_presets(callback, db)
        return

    if data.get("plus_mode"):
        await _replace_with_text(callback, "Выберите вайб:", reply_markup=plus_vibe_keyboard(lang))
        await state.set_state(CreateForm.plus_vibe)
    else:
        # Фолбэк к моделям
        cloth = data.get("cloth")
        index = data.get("index", 0)
        await _show_models_for_category(callback, db, category, cloth, index)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_height)
async def on_back_from_height(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    
    if data.get("random_mode"):
        # Рандом: возврат к размеру
        await _replace_with_text(callback, get_string("select_body_type", lang), reply_markup=form_size_keyboard(data.get("rand_gender"), lang))
        await state.set_state(CreateForm.waiting_size)
        await _safe_answer(callback)
        return

    if data.get("infographic_mode"):
        from bot.keyboards import form_size_keyboard
        # Для инфографики возврат к телосложению
        await _replace_with_text(callback, get_string("select_body_type", lang), reply_markup=form_size_keyboard(data.get("info_gender", "female"), lang))
        await state.set_state(CreateForm.waiting_size)
        await _safe_answer(callback)
        return

    if data.get("category") == "child":
        await _replace_with_text(callback, "Введите возраст ребенка (в годах):")
        await state.set_state(CreateForm.waiting_age)
    else:
        await _replace_with_text(callback, "🎂 Пожалуйста выберите возраст модели:", reply_markup=form_age_keyboard(lang))
        await state.set_state(CreateForm.waiting_age)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_length)
async def on_back_from_length(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")
    
    if category == "own_variant" or data.get("own_mode"):
        await _ask_sleeve_length(callback, state, db)
    elif category == "storefront":
        await on_marketplace_menu(callback, db)
    elif data.get("infographic_mode") and category == "infographic_clothing":
        await _replace_with_text(callback, "Выберите позу модели:", reply_markup=pose_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_pose)
    elif data.get("random_mode"):
        # Рандом: возврат к рукавам
        await state.set_state(CreateForm.waiting_sleeve)
        await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))
    else:
        # Для пресетов и остальных — к росту
        await _replace_with_text(callback, "📏 Введите рост модели в см (например: 170):")
        await state.set_state(CreateForm.waiting_height)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_own_sleeve)
@router.callback_query(F.data == "back_step", CreateForm.waiting_sleeve)
async def on_back_from_sleeve(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")
    
    if data.get("infographic_mode"):
        from bot.keyboards import pants_style_keyboard
        # Для инфографики возврат к крою штанов
        await _replace_with_text(callback, get_string("select_pants_style", lang), reply_markup=pants_style_keyboard(lang))
        await state.set_state(CreateForm.waiting_pants_style)
        await _safe_answer(callback)
        return

    if data.get("random_mode"):
        # Рандом: возврат к крою штанов
        from bot.keyboards import pants_style_keyboard
        await _replace_with_text(callback, get_string("select_pants_style", lang), reply_markup=pants_style_keyboard(lang))
        await state.set_state(CreateForm.waiting_pants_style)
        await _safe_answer(callback)
        return

    if category == "own_variant":
        await _replace_with_text(callback, get_string("upload_product", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_own_product_photo)
    elif data.get("own_mode"):
        await _replace_with_text(callback, get_string("upload_product", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_product_photo)
    elif category == "male":
        # male has no garment length sometimes? check flow
        await _ask_garment_length(callback, state, db)
    else:
        # Default back to garment length
        await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_view)
async def on_back_from_view(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    
    if data.get("infographic_mode"):
        from bot.keyboards import form_view_keyboard
        # Для инфографики возврат к углу камеры
        await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_angle)
        await _safe_answer(callback)
        return

    if data.get("random_mode") or data.get("cloth") == "shoes":
        # Check previous steps for random/shoes
        if data.get("category") == "child" and data.get("cloth") == "shoes":
            await _replace_with_text(callback, "Введите размер ноги ребенка (например: 31) или отправьте 'Пропустить':")
            await state.set_state(CreateForm.waiting_foot)
        else:
            await _ask_garment_length(callback, state, db)
    else:
        await state.set_state(CreateForm.waiting_sleeve)
        await _replace_with_text(callback, "Выберите тип рукава (или пропустите):", reply_markup=sleeve_length_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_foot)
async def on_back_from_foot(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await _replace_with_text(callback, "📏 Введите рост модели в см (например: 170):")
    await state.set_state(CreateForm.waiting_height)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.plus_loc)
async def on_back_from_plus_loc(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    await _show_models_for_category(callback, db, data.get("category"), data.get("cloth"), data.get("index", 0))
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.plus_season)
async def on_back_from_plus_season(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "Выберите локацию:", reply_markup=plus_location_keyboard(lang))
    await state.set_state(CreateForm.plus_loc)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.plus_vibe)
async def on_back_from_plus_vibe(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "Выберите время года:", reply_markup=plus_season_keyboard(lang))
    await state.set_state(CreateForm.plus_season)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_loc_group)
async def on_back_from_rand_locgroup(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_marketplace_menu(callback, db)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_loc)
async def on_back_from_rand_loc(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import random_loc_group_keyboard
    await _replace_with_text(callback, get_string("select_loc_group", lang), reply_markup=random_loc_group_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_loc_group)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_custom_location)
async def on_back_from_custom_loc(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    group = data.get("rand_loc_group", "outdoor")
    from bot.keyboards import random_location_keyboard
    await _replace_with_text(callback, get_string("select_location", lang), reply_markup=random_location_keyboard(group, lang))
    await state.set_state(CreateForm.waiting_rand_loc)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_has_person)
async def on_back_from_has_person(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_create_photo(callback, db, state)

@router.callback_query(F.data == "back_step", CreateForm.waiting_child_gender)
async def on_back_from_child_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    await _show_models_for_category(callback, db, data.get("category"), data.get("cloth"), data.get("index", 0))
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_pants_style)
async def on_back_from_pants_style(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    
    if data.get("infographic_mode"):
        # Для инфографики возврат к росту
        await _replace_with_text(callback, get_string("enter_height", lang))
        await state.set_state(CreateForm.waiting_height)
        await _safe_answer(callback)
        return

    if data.get("random_mode"):
        await state.set_state(CreateForm.waiting_sleeve)
        await _replace_with_text(callback, "Выберите длину рукава:", reply_markup=sleeve_length_keyboard(lang))
    else:
        await _show_models_for_category(callback, db, data.get("category"), data.get("cloth"), data.get("index", 0))
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_lang_custom)
async def on_back_from_info_lang_custom(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
    await state.set_state(None)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_has_person)
async def on_back_from_rand_other_person(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Теперь возвращаемся в меню инфографики, так как эта кнопка теперь там
    await on_infographics_menu(callback, db)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_has_person)
async def on_back_from_rand_other_person(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_marketplace_menu(callback, db)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_gender)
async def on_back_from_rand_other_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import yes_no_keyboard
    await _replace_with_text(callback, get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_has_person)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_name)
async def on_back_from_rand_other_name(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=skip_step_keyboard("info_load", lang))
    await state.set_state(CreateForm.waiting_info_load)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_angle)
async def on_back_from_rand_other_angle(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_product_name", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_name)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_dist)
async def on_back_from_rand_other_dist(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import form_view_keyboard
    await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_angle)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_height)
async def on_back_from_rand_other_height(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import camera_dist_keyboard
    await _replace_with_text(callback, "Выберите ракурс фотографии (Дальний/Средний/Близкий):", reply_markup=camera_dist_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_dist)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_width)
async def on_back_from_rand_other_width(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "Введите высоту (см):", reply_markup=skip_step_keyboard("rand_height", lang))
    await state.set_state(CreateForm.waiting_rand_other_height)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_length)
async def on_back_from_rand_other_length(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "Введите ширину (см):", reply_markup=skip_step_keyboard("rand_width", lang))
    await state.set_state(CreateForm.waiting_rand_other_width)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_season)
async def on_back_from_rand_other_season(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "Введите длину (см):", reply_markup=skip_step_keyboard("rand_length", lang))
    await state.set_state(CreateForm.waiting_rand_other_length)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_style)
async def on_back_from_rand_other_style(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import random_season_keyboard
    await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_season)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_style_custom)
async def on_back_from_rand_other_style_custom(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import style_keyboard
    await _replace_with_text(callback, get_string("select_style", lang), reply_markup=style_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_style)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_dist)
async def on_back_from_rand_other_dist(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=form_view_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_angle)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_height)
async def on_back_from_rand_other_height(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import angle_keyboard
    await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=angle_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_dist)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_width)
async def on_back_from_rand_other_width(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_height_cm", lang), reply_markup=skip_step_keyboard("rand_height", lang))
    await state.set_state(CreateForm.waiting_rand_other_height)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_length)
async def on_back_from_rand_other_length(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_width_cm", lang), reply_markup=skip_step_keyboard("rand_width", lang))
    await state.set_state(CreateForm.waiting_rand_other_width)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_season)
async def on_back_from_rand_other_season(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_length_cm", lang), reply_markup=skip_step_keyboard("rand_length", lang))
    await state.set_state(CreateForm.waiting_rand_other_length)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_style)
async def on_back_from_rand_other_style(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_vibe", lang), reply_markup=plus_season_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_season)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_style_custom)
async def on_back_from_rand_other_style_custom(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import style_keyboard
    await _replace_with_text(callback, get_string("select_style", lang), reply_markup=style_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_style)
    await _safe_answer(callback)

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

@router.callback_query(F.data == "back_step", CreateForm.waiting_own_bg_photo)
async def on_back_from_own_bg(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_marketplace_menu(callback, db)

@router.callback_query(F.data == "back_step", CreateForm.waiting_own_product_photo)
async def on_back_from_own_product(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_create_own_variant(callback, state, db)

@router.callback_query(F.data == "back_step", CreateForm.waiting_ref_photo)
async def on_back_from_ref_photo(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    if data.get("own_mode"):
        await on_marketplace_menu(callback, db)
    else:
        await on_create_photo(callback, db, state)

@router.callback_query(F.data == "back_step", CreateForm.waiting_product_photo)
async def on_back_from_product_photo(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    if data.get("own_mode"):
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, get_string("upload_model_photo", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_ref_photo)
    else:
        await on_create_photo(callback, db, state)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_own_cut)
async def on_back_from_own_cut(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    if data.get("own_mode"):
        await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_aspect)
async def on_back_from_aspect(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    category = data.get("category")

    # 1. Свой вариант ФОНА
    if category == "own_variant":
        await _ask_garment_length(callback, state, db)
    # 2. Свой вариант МОДЕЛИ
    elif data.get("own_mode"):
        await _ask_garment_length(callback, state, db)
    # 3. Инфографика
    elif data.get("infographic_mode"):
        if category == "infographic_clothing":
            await _ask_garment_length(callback, state, db)
        else:
            await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=form_view_keyboard(lang))
            await state.set_state(CreateForm.waiting_view)
    # 4. Рандом одежда
    elif data.get("random_mode"):
        from bot.keyboards import random_holiday_keyboard
        await _replace_with_text(callback, "Выберите праздник (если есть):", reply_markup=random_holiday_keyboard(lang))
        await state.set_state(CreateForm.waiting_preset_holiday)
    # 5. Пресеты
    elif data.get("is_preset"):
        from bot.keyboards import random_season_keyboard
        await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
        await state.set_state(CreateForm.waiting_preset_season)
    # 5. Рандом для прочих товаров
    elif data.get("random_other_mode"):
        if data.get("has_person"):
            from bot.keyboards import style_keyboard
            await _replace_with_text(callback, get_string("select_style", lang), reply_markup=style_keyboard(lang))
            await state.set_state(CreateForm.waiting_rand_other_style)
        else:
            from bot.keyboards import yes_no_keyboard
            await _replace_with_text(callback, get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))
            await state.set_state(CreateForm.waiting_rand_other_has_person)
    # 5. Рандом (Одежда)
    elif data.get("random_mode"):
        if data.get("rand_location") == "photo_studio":
            from bot.keyboards import random_decor_keyboard
            await _replace_with_text(callback, "Декор фотостудии:", reply_markup=random_decor_keyboard(lang))
        else:
            from bot.keyboards import random_shot_keyboard
            await _replace_with_text(callback, get_string("select_view", lang), reply_markup=random_shot_keyboard(lang))
    # 6. На белом фоне
    elif category == "whitebg":
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_market")]])
        await _replace_with_text(callback, get_string("upload_photo", lang), reply_markup=back_kb)
        await state.set_state(CreateForm.waiting_view)
    # 7. Витринное фото
    elif category == "storefront":
        await _ask_garment_length(callback, state, db)
    # 8. Пресеты
    elif category in ("female", "male", "child"):
        from bot.keyboards import random_season_keyboard
        await state.set_state(CreateForm.waiting_preset_season)
        await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
    else:
        await on_create_photo(callback, db, state)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_size)
async def on_back_from_size(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    category = data.get("category")
    if category in ("female", "male"):
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, get_string("select_age", lang), reply_markup=form_age_keyboard(lang))
        await state.set_state(CreateForm.waiting_age)
    else:
        # Child -> go back to model selection
        await _show_models_for_category(callback, db, category, data.get("cloth", "all"), data.get("index", 0))
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_pants_style)
async def on_back_from_pants_style(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_height", lang))
    await state.set_state(CreateForm.waiting_height)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_preset_holiday)
async def on_back_from_preset_holiday(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import random_season_keyboard
    await _replace_with_text(callback, "Выберите сезон:", reply_markup=random_season_keyboard(lang))
    await state.set_state(CreateForm.waiting_preset_season)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_preset_season)
async def on_back_from_preset_season(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(CreateForm.waiting_preset_view)
    await _replace_with_text(callback, "Выберите вид фотографии (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_preset_dist)
async def on_back_from_preset_dist(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    if data.get("category") == "storefront":
        await state.set_state(CreateForm.waiting_preset_view)
        await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
    else:
        await state.set_state(CreateForm.waiting_preset_pose)
        await _replace_with_text(callback, "Выберите тип позы:", reply_markup=pose_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_preset_view)
async def on_back_from_preset_view(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    
    if data.get("category") == "storefront":
        # Назад к выбору модели
        await _show_models_for_category(callback, db, "storefront", data.get("cloth", "all"), data.get("index", 0))
    else:
        await state.set_state(CreateForm.waiting_preset_dist)
        await _replace_with_text(callback, "Выберите ракурс фотографии:", reply_markup=angle_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_preset_pose)
async def on_back_from_preset_pose(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_edit_text)
async def on_back_from_edit_text(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Возвращаемся к просмотру результата
    await state.set_state(CreateForm.result_ready)
    lang = await db.get_user_language(callback.from_user.id)
    # Показываем кнопки действий с результатом
    data = await state.get_data()
    if data.get("own_mode") or data.get("category") == "own_variant":
        kb = result_actions_own_keyboard(lang)
    else:
        kb = result_actions_keyboard(lang)
    await _replace_with_text(callback, get_string("gen_ready", lang), reply_markup=kb)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_length)
async def on_back_from_length(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if data.get("category") == "own_variant" or data.get("own_mode"):
        await _ask_sleeve_length(callback, state, db)
    elif data.get("category") == "storefront":
        await state.set_state(CreateForm.waiting_preset_dist)
        from bot.keyboards import angle_keyboard
        await _replace_with_text(callback, "Выберите ракурс фотографии (Дальний/Средний/Близкий):", reply_markup=angle_keyboard(lang))
    else:
        await _replace_with_text(callback, "📏 Введите рост модели в см (например: 170):")
        await state.set_state(CreateForm.waiting_height)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_own_sleeve)
async def on_back_from_own_sleeve(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("upload_product", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_own_product_photo)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_own_product_photo)
async def on_back_from_own_product(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if data.get("category") == "own_variant":
        await _replace_with_text(callback, get_string("upload_background", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_own_bg_photo)
    else:
        await _replace_with_text(callback, get_string("upload_model_photo", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_ref_photo)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_own_bg_photo)
async def on_back_from_own_bg(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_marketplace_menu(callback, db)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step")
async def on_back_step_fallback(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Если ни один стейт-специфичный хендлер не сработал
    await on_back_main(callback, state, db)


async def _build_final_prompt(data: dict, db: Database) -> str:
    category = data.get("category")
    
    prompt_text = ""
    if data.get("random_mode"):
        prompt_text = ""
    elif category == "own_variant":
        base = await db.get_own_variant_prompt() or "Professional fashion photography. Place the product from the second image onto the background from the first image. Maintain natural lighting, shadows, and perspective. High quality, 8k resolution."
        prompt_text = base
    else:
        if category == "whitebg":
            base = await db.get_whitebg_prompt()
            prompt_text = base or ""
        else:
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
        
    prompt_filled = ""
    if data.get("own_mode"):
        own_length = (data.get("own_length") or "")
        own_sleeve = (data.get("own_sleeve") or "")
        view_key = data.get("view")
        view_word = {"close": "close shot", "far": "far shot", "medium": "medium shot"}.get(view_key, "medium shot")
        
        base = await db.get_own_prompt3() or "Professional fashion photography. Place the product from the second image on the model from the first image, maintaining the same pose, lighting, and background style. High quality, realistic, natural lighting."
        prompt_filled = base
        if own_length: prompt_filled += f" Garment length: {own_length}."
        if own_sleeve: prompt_filled += f" Sleeve length: {own_sleeve}."
        if view_word: prompt_filled += f" Camera distance: {view_word}."
    elif category == "own_variant":
        own_length = (data.get("own_length") or "")
        own_sleeve = (data.get("own_sleeve") or "")
        
        prompt_filled = prompt_text
        if own_length: prompt_filled += f" Garment length: {own_length}."
        if own_sleeve: prompt_filled += f" Sleeve length: {own_sleeve}."
    elif data.get("random_other_mode"):
        has_person = data.get("has_person")
        gender = data.get("gender")
        load = data.get("info_load")
        product_name = data.get("product_name")
        view_key = data.get("view")
        dist = data.get("dist")
        h_cm = data.get("height_cm"); w_cm = data.get("width_cm"); l_cm = data.get("length_cm")
        season = data.get("season")
        style = data.get("style")
        
        view_word = {"close": "близкий", "far": "дальний", "medium": "средний", "back": "сзади", "front": "спереди", "side": "сбоку"}.get(view_key, "спереди")
        dist_word = {"far": "дальний", "medium": "средний", "close": "близкий"}.get(dist, "средний")
        gender_word = {"male": "Мужчина", "female": "Женщина", "boy": "Мальчик", "girl": "Девочка"}.get(gender, "")
        
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
        # Рандом Одежда и Обувь (полный флоу из 13 шагов)
        gender = data.get("rand_gender")
        gender_map = {"male":"мужчина","female":"женщина","boy":"мальчик","girl":"девочка"}
        
        loc = data.get("rand_location")
        loc_map = {"inside_restaurant":"внутри ресторана","photo_studio":"в фотостудии","coffee_shop":"в кофейне","city":"в городе","building":"у здания","wall":"у стены","park":"в парке","coffee_shop_out":"у кофейни","forest":"в лесу","car":"у машины"}
        
        p_parts = ["Professional commercial fashion photography. High quality, realistic lighting. "]
        p_parts.append(f"Model: {gender_map.get(gender, 'person')}. ")
        if age_text: p_parts.append(f"Age: {age_text}. ")
        if size_text: p_parts.append(f"Body type: {size_text}. ")
        h = data.get("height")
        if h: p_parts.append(f"Height: {h}cm. ")
        
        if loc:
            if loc == 'custom':
                custom = (data.get('rand_location_custom') or '').strip()
                if custom: p_parts.append(f"Location: {custom}. ")
            else:
                p_parts.append(f"Location: {loc_map.get(loc, loc)}. ")
        
        pants = data.get("pants_style")
        if pants: p_parts.append(f"Pants cut: {pants}. ")
        sleeve = data.get("sleeve")
        if sleeve: p_parts.append(f"Sleeve type: {sleeve}. ")
        L = (data.get("length") or "").strip()
        if L: p_parts.append(f"Garment length: {L}. ")
        
        pose = data.get("pose")
        if pose: p_parts.append(f"Pose: {pose}. ")
        
        dist = data.get("dist")
        view = data.get("view")
        if dist: p_parts.append(f"Camera distance: {dist}. ")
        if view: p_parts.append(f"View: {view}. ")
        
        season = data.get("season")
        if season: p_parts.append(f"Season: {season}. ")
        holiday = data.get("holiday")
        if holiday: p_parts.append(f"Occasion/Holiday: {holiday}. ")
        
        p_parts.append("8k resolution, cinematic lighting, professional studio look.")
        base_random = await db.get_random_prompt() or ""
        prompt_filled = (base_random + "\n\n" + "".join(p_parts)).strip()
    elif category == "whitebg":
        prompt_filled = prompt_text or "Professional commercial product photography on a pure white background. High resolution, studio lighting, sharp focus on the product."
    elif category == "storefront":
        view_key = data.get("view")
        view_word = {"front": "спереди", "back": "сзади"}.get(view_key, "спереди")
        dist = data.get("dist") or "средний"
        length = data.get("own_length") or ""
        
        replacements = {
            "{Угол камеры}": view_word,
            "{ракурс фотографии}": dist,
            "{Длина изделия}": length,
        }
        prompt_filled = prompt_text or "Professional fashion photography. Model showing the product from {Угол камеры} at {ракурс фотографии} distance. {Длина изделия}"
        for placeholder, value in replacements.items():
            prompt_filled = prompt_filled.replace(placeholder, str(value))
    elif data.get("infographic_mode"):
        # Инфографика (Одежда и Прочее)
        p_parts = ["Professional commercial product photography with infographic elements. High quality, 8k resolution. "]
        
        brand = data.get("info_brand")
        if brand: p_parts.append(f"Product/Brand name: {brand}. ")
        
        load = data.get("info_load")
        if load: p_parts.append(f"Infographic design complexity level: {load}/10. ")
        
        lang = data.get("info_lang")
        if lang: p_parts.append(f"Text language: {lang}. ")
        
        advs = [data.get("info_adv1"), data.get("info_adv2"), data.get("info_adv3")]
        advs = [a for a in advs if a]
        if advs: p_parts.append(f"Key advantages to highlight: {', '.join(advs)}. ")
        
        extra = data.get("info_extra")
        if extra: p_parts.append(f"Additional text: {extra}. ")
        
        angle = data.get("info_angle")
        dist = data.get("info_dist")
        if angle: p_parts.append(f"Camera angle: {angle}. ")
        if dist: p_parts.append(f"Distance: {dist}. ")
        
        if data.get("has_person"):
            gender = data.get("info_gender")
            age = data.get("age")
            pose = data.get("info_pose")
            p_parts.append(f"Model: {gender or 'person'}, Age: {age or 'adult'}. Pose: {pose or 'natural'}. ")
        else:
            p_parts.append("No people in the shot, focus strictly on the product. ")
            
        season = data.get("info_season")
        holiday = data.get("info_holiday")
        if season: p_parts.append(f"Season/Atmosphere: {season}. ")
        if holiday: p_parts.append(f"Occasion/Holiday: {holiday}. ")
        
        if category == "infographic_clothing":
            # Доп. параметры для одежды
            size = data.get("size")
            height = data.get("height")
            cut = data.get("pants_style")
            sleeve = data.get("sleeve")
            length = data.get("length")
            if size: p_parts.append(f"Clothing size: {size}. ")
            if height: p_parts.append(f"Model height: {height}cm. ")
            if cut: p_parts.append(f"Pants cut: {cut}. ")
            if sleeve: p_parts.append(f"Sleeve type: {sleeve}. ")
            if length: p_parts.append(f"Garment length: {length}. ")

        p_parts.append("Clean composition, commercial lighting, professional studio look.")
        prompt_filled = "".join(p_parts)
    else:
        # Обычный режим (Пресеты)
        model_id = data.get("model_id")
        
        if not model_id and data.get("is_preset"):
            # ПРЕСЕТЫ БЕЗ МОДЕЛИ (п. 1)
            gender_map = {"male":"мужчина","female":"женщина","boy":"мальчик","girl":"девочка"}
            actual_gender = data.get("child_gender") or category
            
            p_parts = ["Professional commercial fashion photography. High quality, realistic lighting. "]
            p_parts.append(f"Model: {gender_map.get(actual_gender, 'person')}. ")
            if age_text: p_parts.append(f"Age: {age_text}. ")
            if size_text: p_parts.append(f"Body type: {size_text}. ")
            h = data.get("height")
            if h: p_parts.append(f"Height: {h}cm. ")
            
            pants = data.get("pants_style")
            if pants: p_parts.append(f"Pants cut: {pants}. ")
            sleeve = data.get("sleeve")
            if sleeve: p_parts.append(f"Sleeve type: {sleeve}. ")
            L = (data.get("length") or "").strip()
            if L: p_parts.append(f"Garment length: {L}. ")
            
            pose = data.get("pose")
            if pose: p_parts.append(f"Pose: {pose}. ")
            
            dist = data.get("dist")
            view = data.get("view")
            if dist: p_parts.append(f"Camera distance: {dist}. ")
            if view: p_parts.append(f"View: {view}. ")
            
            season = data.get("season")
            if season: p_parts.append(f"Season: {season}. ")
            
            p_parts.append("8k resolution, cinematic lighting, professional studio look.")
            base_random = await db.get_random_prompt() or ""
            prompt_filled = (base_random + "\n\n" + "".join(p_parts)).strip()
        else:
            # Обычная модель (если ID есть)
            view_key = data.get("view")
            view_word = {"close": "близкий", "far": "дальний", "medium": "средний", "back": "сзади", "front": "спереди", "side": "сбоку"}.get(view_key, "спереди")
            
            replacements = {
                "{размер}": size_text, "{Размер модели}": size_text, "{Размер тела модели}": size_text,
                "{рост}": str(data.get("height", "")), "{Рост модели}": str(data.get("height", "")),
                "{длина изделия}": str(data.get("length", "")), "{Длина изделия}": str(data.get("length", "")),
                "{возраст}": age_text, "{Возраст модели}": age_text,
                "{длина рукав}": sleeve_text, "{Тип рукава}": sleeve_text,
                "{сзади/спереди}": view_word, "{Угол камеры}": view_word,
                "{Пол модели}": "мужчина" if category == "male" else "женщина" if category == "female" else "ребенок",
            }
            prompt_filled = prompt_text or ""
            for placeholder, value in replacements.items():
                prompt_filled = prompt_filled.replace(placeholder, str(value))
                
            if data.get("pants_style"): prompt_filled += f" Cut of pants: {data.get('pants_style')}."
            if data.get("pose"): prompt_filled += f" Model pose: {data.get('pose')}."
            if data.get("dist"): prompt_filled += f" Camera distance: {data.get('dist')}."
            if data.get("season"): prompt_filled += f" Season: {data.get('season')}."

    # Добавляем брендинг
    prompt_filled = db.add_ai_room_branding(prompt_filled)
    return prompt_filled


@router.callback_query(F.data == "form_generate")
async def form_generate(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    user_id = callback.from_user.id
    data = await state.get_data()
    logger.info(f"[form_generate] Начало генерации для пользователя {user_id}. Данные сессии: {data}")
    
    # Проверка техработ
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return

    # Если не обычная генерация и нет фото - просим прислать (для пресетов и т.д.)
    category = data.get("category")
    if not data.get("normal_gen_mode"):
        if category == "own_variant":
            if not data.get("own_bg_photo_id") or not data.get("own_product_photo_id"):
                await _safe_answer(callback, "Сначала загрузите все необходимые фотографии.", show_alert=True)
                return
        elif data.get("own_mode"):
            if not data.get("own_ref_photo_id") or not data.get("own_product_photo_id"):
                await _safe_answer(callback, "Сначала загрузите все необходимые фотографии.", show_alert=True)
                return
        else:
            if not data.get("user_photo_id"):
                text = (
                    "📸 Пожалуйста пришлите фотографию вашего товара.\n\n"
                    "⚠️ Обратите внимание: фотография должна быть четкой без лишних бликов и размытостей.\n\n"
                    "Если остались вопросы - пишите в поддержку @bnbslow"
                )
                await state.set_state(CreateForm.waiting_view)
                await callback.message.answer(text)
                await _safe_answer(callback)
                return

    try:
        sub = await db.get_user_subscription(user_id)
        lang = await db.get_user_language(user_id)
        if not sub:
            await _safe_answer(callback, get_string("limit_rem_zero", lang), show_alert=True)
            return
        
        # sub structure: (plan_type, expires_at, daily_limit, daily_usage, ind_key)
        plan_type, expires_at, daily_limit, daily_usage, ind_key = sub
        if daily_usage >= daily_limit:
            await _safe_answer(callback, get_string("limit_rem_zero", lang), show_alert=True)
            return
        
        quality = '4K' if '4K' in plan_type.upper() else 'HD'

        if not data:
            logger.error(f"[form_generate] КРИТИЧЕСКАЯ ОШИБКА: Данные сессии пусты для пользователя {user_id}")
            await _safe_answer(callback, get_string("session_not_found", lang) + " (пустые данные)", show_alert=True)
            return

        category = data.get("category")
        
        # Баланс в десятых долях токена
        balance = await db.get_user_balance(user_id)
        frac = await db.get_user_fraction(user_id)
        total_tenths = balance * 10 + frac
        price_tenths = await db.get_category_price(category)
        
        if total_tenths < price_tenths:
            await _safe_answer(callback, "Недостаточно средств на балансе.", show_alert=True)
            return

        prompt_filled = await _build_final_prompt(data, db)
        lang = await db.get_user_language(user_id)

        if quality == '4K':
            prompt_filled += " High quality, 4K resolution, ultra detailed."

        # Добавляем брендинг
        prompt_filled = db.add_ai_room_branding(prompt_filled)
        
        # Отправляем сообщение о начале генерации с анимацией
        process_msg = await callback.message.answer("🎨 ⚡️ ⏳")
        
        async def animate_gen(msg, lang_code):
            frames = [
                "🎨 ⏳ Генерируем...",
                "🎨 ⌛️ Почти готово...",
                "🎨 ✨ Магия нейросетей...",
                "🎨 🔄 Улучшаем детали..."
            ]
            try:
                for i in range(20):
                    await asyncio.sleep(1.5)
                    await msg.edit_text(frames[i % len(frames)])
            except: pass

        anim_task = asyncio.create_task(animate_gen(process_msg, lang))

        # Выбор API ключа
        category = data.get("category")
        is_own_variant = (category == "own_variant")
        
        # Если normal_gen_mode, используем обычные ключи Gemini
        if data.get("normal_gen_mode"):
            is_own_variant = False
            
        if is_own_variant:
            api_keys = await db.list_own_variant_api_keys()
        else:
            api_keys = await db.list_api_keys()
            
        # Фильтруем только активные
        active_keys = [k for k in api_keys if k[2]] # is_active
        if not active_keys:
            await _replace_with_text(callback, get_string("api_error_user", lang))
            return
            
        # Перебираем ключи пока не найдем рабочий (rotate)
        result_url = None
        error_msg = None
        
        import random
        random.shuffle(active_keys)
        
        for key_tuple in active_keys:
            kid = key_tuple[0]
            token = key_tuple[1]
            
            # Проверка лимитов ключа
            if is_own_variant:
                ok, limit_err = await db.check_own_variant_rate_limit(kid)
            else:
                ok, limit_err = await db.check_api_key_limits(kid)
                
            if not ok:
                logger.warning(f"Key {kid} reached limit: {limit_err}")
                continue
                
            # Пробуем генерацию
            from bot.gemini import generate_image
            
            input_photos = data.get("photos", [])
            # Если это не обычная генерация, берем user_photo_id
            if not data.get("normal_gen_mode"):
                if category == "own_variant":
                    input_photos = [data.get("own_bg_photo_id"), data.get("own_product_photo_id")]
                elif data.get("own_mode"):
                    input_photos = [data.get("own_ref_photo_id"), data.get("own_product_photo_id")]
                else:
                    input_photos = [data.get("user_photo_id")]
            
            try:
                bot = callback.bot
                
                downloaded_paths = []
                import uuid
                for fid in input_photos:
                    if not fid: continue
                    f_info = await bot.get_file(fid)
                    ext = f_info.file_path.split('.')[-1]
                    p = f"data/temp_{uuid.uuid4()}.{ext}"
                    await bot.download_file(f_info.file_path, p)
                    downloaded_paths.append(p)
                
                # Aspect ratio
                aspect = data.get("aspect", "1:1").replace(":", "x")
                
                # Вызываем генерацию
                result_path = await generate_image(
                    api_key=token,
                    prompt=prompt_filled,
                    image_paths=downloaded_paths,
                    aspect_ratio=aspect,
                    quality=quality
                )
                
                # Чистим временные файлы
                import os
                for p in downloaded_paths:
                    try: os.remove(p)
                    except: pass
                
                if result_path:
                    # Успех! Записываем использование
                    if is_own_variant:
                        await db.record_own_variant_usage(kid)
                    else:
                        await db.record_api_usage(kid)
                        
                    # Отправляем результат
                    from aiogram.types import FSInputFile
                    from bot.keyboards import result_actions_keyboard, result_actions_own_keyboard
                    
                    # Останавливаем анимацию и удаляем сообщение о загрузке
                    anim_task.cancel()
                    try: await process_msg.delete()
                    except: pass

                    res_msg = await bot.send_photo(
                        chat_id=user_id,
                        photo=FSInputFile(result_path),
                        caption=get_string("gen_success", lang),
                        reply_markup=result_actions_keyboard(lang) if not is_own_variant else result_actions_own_keyboard(lang)
                    )
                    
                    # Сохраняем в историю
                    import json
                    import os
                    pid = await db.generate_pid()
                    
                    # Создаем папку для истории
                    history_dir = os.path.join("data", "history")
                    os.makedirs(history_dir, exist_ok=True)
                    
                    # Сохраняем локальные пути для админки
                    local_input_paths = []
                    local_result_path = os.path.join(history_dir, f"result_{pid}.jpg")
                    
                    try:
                        # Качаем результат
                        file_info = await bot.get_file(res_msg.photo[-1].file_id)
                        await bot.download_file(file_info.file_path, local_result_path)
                        
                        # Качаем входные фото
                        for i, f_id in enumerate(input_photos):
                            if not f_id: continue
                            inp_path = os.path.join(history_dir, f"input_{pid}_{i}.jpg")
                            try:
                                f_info = await bot.get_file(f_id)
                                await bot.download_file(f_info.file_path, inp_path)
                                local_input_paths.append(inp_path)
                            except: pass
                    except Exception as e:
                        logger.error(f"Error downloading images for history: {e}")

                    await db.add_generation_history(
                        pid=pid,
                        user_id=user_id,
                        category=category,
                        params=json.dumps(data),
                        input_photos=json.dumps(input_photos),
                        result_photo_id=res_msg.photo[-1].file_id,
                        input_paths=json.dumps(local_input_paths),
                        result_path=local_result_path
                    )
                    
                    # Списываем баланс
                    await db.increment_user_balance(user_id, -(price_tenths // 10))
                    # Остаток в фракции
                    rem = price_tenths % 10
                    if rem > 0:
                        cur_frac = await db.get_user_fraction(user_id)
                        new_frac = cur_frac - rem
                        if new_frac < 0:
                            await db.increment_user_balance(user_id, -1)
                            new_frac += 10
                        await db.set_user_fraction(user_id, new_frac)
                    
                    # Инкрементируем daily_usage подписки
                    await db.update_daily_usage(user_id)
                    
                    try: os.remove(result_path)
                    except: pass
                    
                    await state.set_state(CreateForm.result_ready)
                    await state.update_data(last_pid=pid)
                    return
                    
            except Exception as e:
                logger.error(f"Generation error with key {kid}: {e}")
                
                # Останавливаем анимацию при ошибке
                anim_task.cancel()
                try: await process_msg.delete()
                except: pass

                from bot.gemini import is_proxy_error
                await db.record_api_error(
                    key_id=kid,
                    api_key_preview=token[:10],
                    error_type=type(e).__name__,
                    error_message=str(e),
                    is_proxy_error=is_proxy_error(e)
                )
                error_msg = str(e)
                continue
        
        # Если дошли сюда, значит все ключи не сработали
        await _replace_with_text(callback, get_string("api_error_user", lang))
        
    except Exception as e:
        logger.exception(f"Critical error in form_generate: {e}")
        await _safe_answer(callback, get_string("internal_error", lang), show_alert=True)
    
    await _safe_answer(callback)


@router.callback_query(F.data == "result_edit")
async def on_result_edit(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Сохраняем текущее состояние перед правками
    await state.set_state(CreateForm.waiting_edit_text)
    lang = await db.get_user_language(callback.from_user.id)
    await callback.message.answer(get_string("enter_edit_description", lang))
    await _safe_answer(callback)


@router.message(CreateForm.waiting_edit_text)
async def on_result_edit_text(message: Message, state: FSMContext, db: Database) -> None:
    edit_text = (message.text or "").strip()
    data = await state.get_data()
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    
    logger.info(f"[on_result_edit_text] Пользователь {user_id} ввел правки: {edit_text}")
    
    if not data:
        await message.answer(get_string("session_not_found", lang))
        await state.clear()
        return

    # Проверка баланса
    balance = await db.get_user_balance(user_id)
    frac = await db.get_user_fraction(user_id)
    total_tenths = balance * 10 + frac
    category = data.get("category", "female")
    price_tenths = await db.get_category_price(category)
    
    if total_tenths < price_tenths:
        await message.answer("Недостаточно средств на балансе для правок.")
        return

    # Строим базовый промпт и добавляем правки
    base_prompt = await _build_final_prompt(data, db)
    prompt_filled = f"{base_prompt}\n\nПравки: {edit_text}"
    
    # Качество из подписки
    sub = await db.get_user_subscription(user_id)
    quality = 'HD'
    if sub and '4K' in sub[0].upper():
        quality = '4K'

    # Собираем фото
    input_photos = data.get("photos", [])
    if not data.get("normal_gen_mode"):
        if category == "own_variant":
            input_photos = [data.get("own_bg_photo_id"), data.get("own_product_photo_id")]
        elif data.get("own_mode"):
            input_photos = [data.get("own_ref_photo_id"), data.get("own_product_photo_id")]
        else:
            input_photos = [data.get("user_photo_id")]
    
    input_photos = [fid for fid in input_photos if fid]
    if not input_photos:
        logger.error(f"[on_result_edit_text] Фото не найдены в данных сессии: {data}")
        await message.answer("Не найдены исходные фото. Начните заново.")
        return

    # Анимация
    process_msg = await message.answer("🎨 ⚡️ ⏳")
    async def animate_gen(msg):
        frames = ["🎨 ⏳ Применяем правки...", "🎨 ⌛️ Перерисовываем...", "🎨 ✨ Магия нейросетей...", "🎨 🔄 Финализируем..."]
        try:
            for i in range(20):
                await asyncio.sleep(1.5)
                await msg.edit_text(frames[i % len(frames)])
        except: pass
    anim_task = asyncio.create_task(animate_gen(process_msg))

    try:
        # Скачиваем фото
        downloaded_paths = []
        import uuid, os
        for fid in input_photos:
            f_info = await message.bot.get_file(fid)
            ext = f_info.file_path.split('.')[-1]
            p = f"data/temp_edit_{uuid.uuid4()}.{ext}"
            await message.bot.download_file(f_info.file_path, p)
            downloaded_paths.append(p)

        # Выбор API ключей
        is_own_variant = (category == "own_variant")
        if is_own_variant: api_keys = await db.list_own_variant_api_keys()
        else: api_keys = await db.list_api_keys()
        
        active_keys = [k for k in api_keys if k[2]]
        import random
        random.shuffle(active_keys)
        
        result_path = None
        kid_used = None
        
        from bot.gemini import generate_image
        aspect = data.get("aspect", "1:1").replace(":", "x")
        if aspect == "auto": aspect = "1x1" # Для Gemini лучше передать конкретный формат

        for key_tuple in active_keys:
            kid, token = key_tuple[0], key_tuple[1]
            if is_own_variant: ok, _ = await db.check_own_variant_rate_limit(kid)
            else: ok, _ = await db.check_api_key_limits(kid)
            if not ok: continue
            
            try:
                result_path = await generate_image(
                    api_key=token, prompt=prompt_filled, image_paths=downloaded_paths,
                    aspect_ratio=aspect, quality=quality, key_id=kid, db_instance=db
                )
                if result_path:
                    kid_used = kid
                    break
            except Exception as e:
                logger.error(f"Edit error key {kid}: {e}")
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
            if is_own_variant: await db.record_own_variant_usage(kid_used)
            else: await db.record_api_usage(kid_used)
            
            # Списываем баланс
            await db.increment_user_balance(user_id, -(price_tenths // 10))
            rem = price_tenths % 10
            if rem > 0:
                cur_frac = await db.get_user_fraction(user_id)
                new_frac = cur_frac - rem
                if new_frac < 0:
                    await db.increment_user_balance(user_id, -1)
                    new_frac += 10
                await db.set_user_fraction(user_id, new_frac)
            
            await db.update_daily_usage(user_id)

            from bot.keyboards import result_actions_keyboard, result_actions_own_keyboard
            kb = result_actions_keyboard(lang)
            if category == "own_variant" or data.get("own_mode"):
                kb = result_actions_own_keyboard(lang)
                
            res_msg = await message.answer_photo(
                photo=FSInputFile(result_path),
                caption=f"✅ Правки применены!\n\nТекст правок: {edit_text}",
                reply_markup=kb
            )

            # Сохраняем в историю
            import json
            import os
            pid = await db.generate_pid()
            history_dir = os.path.join("data", "history")
            os.makedirs(history_dir, exist_ok=True)
            local_input_paths = []
            local_result_path = os.path.join(history_dir, f"result_{pid}.jpg")

            try:
                # Качаем результат
                file_info = await message.bot.get_file(res_msg.photo[-1].file_id)
                await message.bot.download_file(file_info.file_path, local_result_path)
                # Качаем входные фото
                for i, f_id in enumerate(input_photos):
                    if not f_id: continue
                    inp_path = os.path.join(history_dir, f"input_{pid}_{i}.jpg")
                    try:
                        f_info = await message.bot.get_file(f_id)
                        await message.bot.download_file(f_info.file_path, inp_path)
                        local_input_paths.append(inp_path)
                    except: pass
            except Exception as e:
                logger.error(f"Error downloading images for history in edit: {e}")

            await db.add_generation_history(
                pid=pid,
                user_id=user_id,
                category=category,
                params=json.dumps(data),
                input_photos=json.dumps(input_photos),
                result_photo_id=res_msg.photo[-1].file_id,
                input_paths=json.dumps(local_input_paths),
                result_path=local_result_path
            )

            try: os.remove(result_path)
            except: pass
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

    # Сохраняем ТОЛЬКО категорию и базовые режимы для чистого старта по требованию пользователя
    # Это гарантирует, что каждый запрос будет абсолютно новым и не "испортит" результат
    keep_keys = ["category", "random_mode", "random_other_mode", "infographic_mode", "own_mode", "plus_mode"]
    
    # Специальная обработка для "Своего варианта": сохраняем фото референса/фона
    if data.get("own_mode") and data.get("own_ref_photo_id"):
        keep_keys.append("own_ref_photo_id")
    if data.get("category") == "own_variant" and data.get("own_bg_photo_id"):
        keep_keys.append("own_bg_photo_id")

    new_data = {k: v for k, v in data.items() if k in keep_keys}
    # Мы НЕ устанавливаем repeat_mode=True, чтобы пользователь прошел весь опрос заново
    
    # Сбрасываем текущее состояние и данные полностью
    await state.clear()
    await state.update_data(**new_data)
    
    # Отправляем пользователя в начало текущей категории
    cat = new_data.get("category")
    if new_data.get("infographic_mode"):
        callback.data = f"create_cat:{cat}"
        await on_infographic_category(callback, state, db)
    elif new_data.get("random_mode"):
        await on_create_random(callback, state, db)
    elif new_data.get("random_other_mode"):
        await on_create_random_other(callback, state, db)
    elif new_data.get("own_mode"):
        await on_create_own(callback, state, db)
    elif cat == "own_variant":
        from bot.handlers.start import on_create_own_variant
        await on_create_own_variant(callback, state, db)
    elif cat == "storefront":
        await on_storefront_category(callback, db, state)
    elif cat == "whitebg":
        await on_whitebg_category(callback, db, state)
    else:
        await on_ready_presets(callback, db)
    
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
    sub = await db.get_user_subscription(callback.from_user.id)
    if sub:
        # sub structure: (plan_type, expires_at, daily_limit, daily_usage, ind_key)
        plan, expires, limit, usage, _indiv_key = sub
        # Форматируем дату (expires может быть строкой или объектом datetime)
        if isinstance(expires, str):
            # Если в БД хранится 'YYYY-MM-DD HH:MM:SS'
            expires_dt = expires[:16].replace('T', ' ')
        else:
            expires_dt = expires.strftime("%Y-%m-%d %H:%M")
            
        daily_rem = max(0, limit - usage)
        text = get_string("profile_info", lang, id=callback.from_user.id, sub=plan, expires=expires_dt, daily_rem=daily_rem)
    else:
        text = get_string("profile_info", lang, id=callback.from_user.id, sub=get_string("sub_none", lang), expires="—", daily_rem=0)
    
    await _replace_with_text(callback, text, reply_markup=profile_keyboard(lang))
    await _safe_answer(callback)

@router.callback_query(F.data == "menu_subscription")
async def on_sub_menu(callback: CallbackQuery, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    plans = await db.list_subscription_plans()
    text = "Выберите план подписки:"
    await _replace_with_text(callback, text, reply_markup=plans_keyboard(plans, lang))
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
            if result_photo_id.startswith("AgAC"): # Telegram file_id
                await callback.message.answer_photo(photo=result_photo_id, caption=caption, parse_mode="Markdown")
            else:
                # Если это путь к файлу
                from aiogram.types import FSInputFile
                import os
                file_path = result_photo_id if os.path.exists(result_photo_id) else os.path.join("/app", result_photo_id)
                if os.path.exists(file_path):
                    await callback.message.answer_photo(photo=FSInputFile(file_path), caption=caption, parse_mode="Markdown")
                else:
                    await callback.message.answer(caption, parse_mode="Markdown")
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
    price = plan[7]
    duration = plan[8]
    limit = plan[9]
    
    # Для теста выдаем сразу. В реальности тут должен быть платежный шлюз.
    await db.grant_subscription(callback.from_user.id, plan_id, name, duration, limit, amount=price)
    
    # Получаем информацию о подписке для отображения даты окончания
    sub = await db.get_user_subscription(callback.from_user.id)
    if sub:
        plan_type, expires_at, daily_limit, daily_usage, ind_key = sub
        # Форматируем дату и время окончания
        from datetime import datetime
        try:
            # Парсим ISO формат даты (может быть с Z или без)
            expires_str = expires_at.replace('Z', '') if 'Z' in expires_at else expires_at
            if 'T' in expires_str:
                expires_dt = datetime.fromisoformat(expires_str)
            else:
                # Если только дата без времени
                expires_dt = datetime.fromisoformat(expires_str + "T00:00:00")
            expires_date = expires_dt.strftime("%d.%m.%Y")
            expires_time = expires_dt.strftime("%H:%M")
        except Exception as e:
            # Fallback форматирование
            if 'T' in expires_at:
                parts = expires_at.split('T')
                date_part = parts[0]
                time_part = parts[1][:5] if len(parts[1]) >= 5 else "00:00"
                expires_date = ".".join(reversed(date_part.split("-")))
                expires_time = time_part
            else:
                expires_date = expires_at[:10] if len(expires_at) >= 10 else expires_at
                expires_time = "00:00"
        
        text = get_string("sub_success_congrats", lang, 
                         plan_name=name,
                         expires_date=expires_date,
                         expires_time=expires_time,
                         daily_limit=daily_limit)
        
        if "4K" in name.upper():
            text += "\n\n⚠️ " + get_string("missing_4k_key", lang)
    else:
        # Fallback если не удалось получить подписку
        text = f"✅ {get_string('sub_success_alert', lang)}\n\n📋 {get_string('menu_subscription', lang)}: {name}\n📊 Лимит: {limit}"
        
    # Отправляем новое сообщение пользователю с поздравлением
    await callback.message.answer(text, reply_markup=back_main_keyboard(lang))
    await _safe_answer(callback)


