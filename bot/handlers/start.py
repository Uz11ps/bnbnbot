from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
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
    random_decor_keyboard,
    random_skip_keyboard,
    random_shot_keyboard,
    plus_location_keyboard,
    plus_season_keyboard,
    plus_vibe_keyboard,
    plus_gender_keyboard,
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
    category = State()
    cloth = State()
    # Infographic flow
    waiting_info_load = State()
    waiting_info_lang_custom = State()
    waiting_info_brand = State()
    waiting_info_adv1 = State()
    waiting_info_adv2 = State()
    waiting_info_adv3 = State()
    waiting_info_extra = State()
    waiting_info_angle = State()
    waiting_info_pose = State()
    # Random Other flow
    waiting_rand_other_has_person = State()
    waiting_rand_other_gender = State()
    waiting_rand_other_load = State()
    waiting_rand_other_name = State()
    waiting_rand_other_angle = State()
    waiting_rand_other_dist = State()
    waiting_rand_other_height = State()
    waiting_rand_other_width = State()
    waiting_rand_other_length = State()
    waiting_rand_other_season = State()
    waiting_rand_other_style = State()
    waiting_rand_other_style_custom = State()
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


async def _answer_model_photo(callback: CallbackQuery, file_id: str, caption: str, reply_markup=None) -> None:
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    try:
        await callback.message.answer_photo(photo=file_id, caption=caption, reply_markup=reply_markup)
    except TelegramBadRequest:
        # file_id может быть от другого бота — падаем в текстовый фолбэк
        try:
            await callback.message.answer(caption, reply_markup=reply_markup)
        except TelegramBadRequest:
            pass


@router.callback_query(F.data.startswith("child_gender:"))
async def on_child_gender_select(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    gender = callback.data.split(":")[1]
    # gender is 'boy' or 'girl'
    await state.update_data(child_gender=gender, category="child", cloth=gender)
    await _show_models_for_category(callback, db, "child", gender)
    await _safe_answer(callback)


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
    await message.answer(get_string("start_welcome", lang), reply_markup=terms_keyboard(lang))


@router.callback_query(F.data == "accept_terms")
async def on_accept_terms(callback: CallbackQuery, db: Database) -> None:
    await db.set_terms_acceptance(callback.from_user.id, True)
    lang = await db.get_user_language(callback.from_user.id)
    await callback.message.answer(get_string("main_menu_title", lang), reply_markup=main_menu_keyboard(lang))
    await _safe_answer(callback)


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
        await _safe_answer(callback)


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
    await state.update_data(category="female", cloth="all")
    await _show_models_for_category(callback, db, "female", "all")
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
    await state.update_data(category="male", cloth="all")
    await _show_models_for_category(callback, db, "male", "all")
    await _safe_answer(callback)

async def _show_models_for_category(callback: CallbackQuery, db: Database, category: str, cloth: str) -> None:
    total = await db.count_models(category, cloth)
    if total <= 0:
        await _safe_answer(callback, "Модели не найдены", show_alert=True)
        return
    text = _model_header(0, total)
    model = await db.get_model_by_index(category, cloth, 0)
    if model and model[3]:
        await _answer_model_photo(
            callback,
            model[3],
            text,
            model_select_keyboard(category, cloth, 0, total),
            )
        else:
        await _replace_with_text(callback, text, reply_markup=model_select_keyboard(category, cloth, 0, total))

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
    await _replace_with_text(callback, get_string("select_model_gender", lang), reply_markup=random_gender_keyboard(lang))
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
    # В рандоме для прочих товаров сначала спрашиваем о присутствии человека
    from bot.keyboards import yes_no_keyboard
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
        # Если есть человек — спрашиваем пол
        from bot.keyboards import random_other_gender_keyboard
        await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=random_other_gender_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_gender)
    else:
        # Если нет — переходим к нагруженности инфографики (шаг 3 в списке пользователя, но по логике шаг 2 без человека)
        await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_load)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_rand_other_gender, F.data.startswith("rand_other_gender:"))
async def on_rand_other_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_load)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_rand_other_load)
async def on_rand_other_load(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if text.isdigit() and 1 <= int(text) <= 10:
        await state.update_data(info_load=text)
        await message.answer(get_string("enter_product_name", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_name)
    else:
        await message.answer(get_string("enter_info_load_error", lang))

@router.message(CreateForm.waiting_rand_other_name)
async def on_rand_other_name(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if not text or len(text) > 50:
        await message.answer(get_string("enter_product_name_error", lang))
        return
    await state.update_data(product_name=text)
    await message.answer("Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_angle)

@router.callback_query(CreateForm.waiting_rand_other_angle, F.data.startswith("form_view:"))
async def on_rand_other_angle(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    view = callback.data.split(":")[1]
    await state.update_data(view=view)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import angle_keyboard
    await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=angle_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_dist)
    await _safe_answer(callback)

@router.callback_query(CreateForm.waiting_rand_other_dist, F.data.startswith("angle:"))
async def on_rand_other_dist(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    dist = callback.data.split(":")[1]
    await state.update_data(dist=dist)
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_height_cm", lang), reply_markup=skip_step_keyboard("rand_height", lang))
    await state.set_state(CreateForm.waiting_rand_other_height)
    await _safe_answer(callback)

@router.message(CreateForm.waiting_rand_other_height)
@router.callback_query(F.data == "rand_height:skip")
async def on_rand_other_height(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    if isinstance(message_or_callback, Message):
        text = (message_or_callback.text or "").strip()
        await state.update_data(height_cm=text)
        lang = await db.get_user_language(message_or_callback.from_user.id)
        await message_or_callback.answer(get_string("enter_width_cm", lang), reply_markup=skip_step_keyboard("rand_width", lang))
    else:
        await state.update_data(height_cm="")
        lang = await db.get_user_language(message_or_callback.from_user.id)
        await _replace_with_text(message_or_callback, get_string("enter_width_cm", lang), reply_markup=skip_step_keyboard("rand_width", lang))
    await state.set_state(CreateForm.waiting_rand_other_width)

@router.message(CreateForm.waiting_rand_other_width)
@router.callback_query(F.data == "rand_width:skip")
async def on_rand_other_width(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    if isinstance(message_or_callback, Message):
        text = (message_or_callback.text or "").strip()
        await state.update_data(width_cm=text)
        lang = await db.get_user_language(message_or_callback.from_user.id)
        await message_or_callback.answer(get_string("enter_length_cm", lang), reply_markup=skip_step_keyboard("rand_length", lang))
    else:
        await state.update_data(width_cm="")
        lang = await db.get_user_language(message_or_callback.from_user.id)
        await _replace_with_text(message_or_callback, get_string("enter_length_cm", lang), reply_markup=skip_step_keyboard("rand_length", lang))
    await state.set_state(CreateForm.waiting_rand_other_length)

@router.message(CreateForm.waiting_rand_other_length)
@router.callback_query(F.data == "rand_length:skip")
async def on_rand_other_length(message_or_callback: Message | CallbackQuery, state: FSMContext, db: Database) -> None:
    if isinstance(message_or_callback, Message):
        text = (message_or_callback.text or "").strip()
        await state.update_data(length_cm=text)
        lang = await db.get_user_language(message_or_callback.from_user.id)
        await message_or_callback.answer(get_string("select_vibe", lang), reply_markup=plus_season_keyboard(lang))
    else:
        await state.update_data(length_cm="")
        lang = await db.get_user_language(message_or_callback.from_user.id)
        await _replace_with_text(message_or_callback, get_string("select_vibe", lang), reply_markup=plus_season_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_season)

@router.callback_query(CreateForm.waiting_rand_other_season, F.data.startswith("plus_season:"))
async def on_rand_other_season(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    season = callback.data.split(":")[1]
    await state.update_data(season=season)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import style_keyboard
    await _replace_with_text(callback, get_string("select_style", lang), reply_markup=style_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_style)
    await _safe_answer(callback)

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
    await state.update_data(category="storefront")
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
    from bot.keyboards import gender_selection_keyboard
    await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=gender_selection_keyboard("whitebg", lang, back_data="menu_market"))
    await _safe_answer(callback)

@router.callback_query(F.data.startswith("gender_select:"))
async def on_generic_gender_select(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    parts = callback.data.split(":")
    category = parts[1]
    gender = parts[2]
    
    # Сохраняем данные
    await state.update_data(category=category, gender=gender, cloth="all")
    
    # Если это категория child, дополнительно помечаем child_gender для совместимости
    if category == "child":
        await state.update_data(child_gender=gender)
        
    # Сразу показываем модели для этой категории и пола
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
        # Для одежды спрашиваем пол
        await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang, back_data="create_cat:infographics"))
    else: # infographic_other
        # Для остальных товаров сразу переходим к нагруженности
        await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_load)
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("info_gender:"))
async def on_infographic_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    g = callback.data.split(":")[1]
    await state.update_data(info_gender=g)
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_info_style", lang), reply_markup=infographic_style_keyboard(lang))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("info_style:"))
async def on_infographic_style(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":")[1]
    await state.update_data(info_style=val)
    lang = await db.get_user_language(callback.from_user.id)
    # Запрашиваем нагруженность как текстовый ввод от 1 до 10
    await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_load)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_info_load)
async def on_infographic_load_input(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    
    # Проверка на пропуск
    if text.lower() in ("пропустить", "skip", "пропустить"):
        await state.update_data(info_load="")
        await message.answer(get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
        return
    
    # Извлекаем только цифры
    digits = ''.join(ch for ch in text if ch.isdigit())
    if not digits:
        await message.answer(get_string("enter_info_load_error", lang))
        return
    
    load_value = int(digits)
    
    # Валидация: от 1 до 10
    if load_value < 1 or load_value > 10:
        await message.answer(get_string("enter_info_load_error", lang))
        return
    
    await state.update_data(info_load=str(load_value))
    await message.answer(get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))


@router.callback_query(F.data.startswith("info_load:"))
async def on_infographic_load_skip(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Обработка пропуска через кнопку (если осталась где-то)
    await state.update_data(info_load="")
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("info_load:"))
async def on_infographic_load_skip(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Обработка пропуска через кнопку (если осталась где-то)
    await state.update_data(info_load="")
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
    await _safe_answer(callback)


@router.callback_query(F.data == "back_step", CreateForm.waiting_info_load)
async def on_back_from_info_load(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    cat = data.get("category")
    if cat == "infographic_clothing":
        await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang, back_data="create_cat:infographics"))
    else:
        await on_infographics_menu(callback, db)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_lang_custom)
@router.callback_query(F.data == "back_step", CreateForm.waiting_info_brand)
async def on_back_from_info_brand(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import info_lang_keyboard
    await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
    await state.set_state(None) # Callback handles state transition
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
    await _replace_with_text(callback, get_string("enter_info_extra_skip", lang), reply_markup=skip_step_keyboard("info_extra", lang))
    await state.set_state(CreateForm.waiting_info_extra)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_pose)
async def on_back_from_info_pose(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_angle)
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("info_lang:"))
async def on_infographic_lang(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    
    if val == "custom":
        await _replace_with_text(callback, get_string("enter_info_lang_custom", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_info_lang_custom)
        await _safe_answer(callback)
        return
        
    await state.update_data(info_lang=val)
    # Далее Название бренда/товара
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
        await message.answer(get_string("enter_info_brand_too_long", lang))
        return
    await state.update_data(info_brand=text)
    await message.answer(get_string("enter_adv1_skip", lang), reply_markup=skip_step_keyboard("info_adv1", lang))
    await state.set_state(CreateForm.waiting_info_adv1)


@router.message(CreateForm.waiting_info_adv1)
async def on_infographic_adv1(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if len(text) > 100:
        await message.answer(get_string("enter_info_adv_too_long", lang))
        return
    await state.update_data(info_adv1=text)
    await message.answer(get_string("enter_adv2_skip", lang), reply_markup=skip_step_keyboard("info_adv2", lang))
    await state.set_state(CreateForm.waiting_info_adv2)


@router.callback_query(F.data == "info_adv1:skip")
async def on_infographic_adv1_skip(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(info_adv1="")
    await _replace_with_text(callback, get_string("enter_adv2_skip", lang), reply_markup=skip_step_keyboard("info_adv2", lang))
    await state.set_state(CreateForm.waiting_info_adv2)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_info_adv2)
async def on_infographic_adv2(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if len(text) > 100:
        await message.answer(get_string("enter_info_adv_too_long", lang))
        return
    await state.update_data(info_adv2=text)
    await message.answer(get_string("enter_adv3_skip", lang), reply_markup=skip_step_keyboard("info_adv3", lang))
    await state.set_state(CreateForm.waiting_info_adv3)


@router.callback_query(F.data == "info_adv2:skip")
async def on_infographic_adv2_skip(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(info_adv2="")
    await _replace_with_text(callback, get_string("enter_adv3_skip", lang), reply_markup=skip_step_keyboard("info_adv3", lang))
    await state.set_state(CreateForm.waiting_info_adv3)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_info_adv3)
async def on_infographic_adv3(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    lang = await db.get_user_language(message.from_user.id)
    if len(text) > 100:
        await message.answer(get_string("enter_info_adv_too_long", lang))
        return
    await state.update_data(info_adv3=text)
    await message.answer(get_string("enter_extra_info_skip", lang), reply_markup=skip_step_keyboard("info_extra", lang))
    await state.set_state(CreateForm.waiting_info_extra)


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
        await message.answer(get_string("enter_info_extra_too_long", lang))
        return
    await state.update_data(info_extra=text)
    
    data = await state.get_data()
    if data.get("category") == "infographic_other":
        # Для прочих товаров переходим к формату
        await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)
    else:
        # Для одежды продолжаем выбор параметров модели
        await message.answer("Выберите телосложение модели:", reply_markup=form_size_keyboard("female")) # По умолчанию female
        await state.set_state(CreateForm.waiting_size)


@router.callback_query(F.data == "info_extra:skip")
async def on_infographic_extra_skip(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(info_extra="")
    
    data = await state.get_data()
    if data.get("category") == "infographic_other":
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)
    else:
        await _replace_with_text(callback, "Выберите телосложение модели:", reply_markup=form_size_keyboard("female"))
        await state.set_state(CreateForm.waiting_size)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_has_person, F.data.startswith("yes_no:"))
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
    await state.update_data(own_mode=True)
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
    await _replace_with_text(callback, get_string("upload_background", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_own_bg_photo)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_own_bg_photo, F.photo)
async def on_own_bg_photo(message: Message, state: FSMContext, db: Database) -> None:
    photo_id = message.photo[-1].file_id
    await state.update_data(own_bg_photo_id=photo_id)
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(get_string("upload_product", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_own_product_photo)


@router.message(CreateForm.waiting_own_product_photo, F.photo)
async def on_own_product_photo(message: Message, state: FSMContext, db: Database) -> None:
    photo_id = message.photo[-1].file_id
    await state.update_data(own_product_photo_id=photo_id)
    lang = await db.get_user_language(message.from_user.id)
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
async def on_aspect_selected(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    aspect = callback.data.split(":", 1)[1]
    await state.update_data(aspect=aspect)
    
    data = await state.get_data()
    category = data.get("category")
    
    if data.get("normal_gen_mode"):
        parts = [
            "📋 Проверьте выбранные параметры:\n\n",
            "📦 **Категория**: ✨ ОБЫЧНАЯ ГЕНЕРАЦИЯ\n",
            f"📝 **Промпт**: {data.get('prompt', '—')}\n",
            f"🖼️ **Формат**: {aspect.replace('x', ':')}\n\n",
            "Все верно? Нажмите кнопку ниже для генерации."
        ]
    elif category == "own_variant":
        parts = [
            "📋 Проверьте выбранные параметры:\n\n",
            "📦 **Категория**: 🖼️ Свой вариант ФОНА\n",
            f"🖼️ **Формат**: {aspect.replace('x', ':')}\n\n",
            "Все верно? Нажмите кнопку ниже для генерации."
        ]
    elif data.get("random_other_mode"):
        has_person = "Да" if data.get("has_person") else "Нет"
        location = data.get("rand_location") or "—"
        vibe = data.get("rand_vibe") or "—"
        parts = [
            "📋 Проверьте выбранные параметры:\n\n",
            "📦 **Категория**: ✨ Рандом для прочих товаров\n",
            f"👤 **Присутствие человека**: {has_person}\n",
            f"📍 **Локация**: {location}\n",
            f"🎞 **Вайб**: {vibe}\n",
            f"🖼️ **Формат**: {aspect.replace('x', ':')}\n\n",
            "Все верно? Нажмите кнопку ниже для генерации."
        ]
    elif data.get("own_mode"):
        length = data.get("own_length") or "—"
        sleeve = data.get("own_sleeve") or "—"
        cut = data.get("own_cut") or "—"
        lang = await db.get_user_language(callback.from_user.id)
        parts = [
            "📋 Проверьте выбранные параметры:\n\n",
            "📦 **Категория**: ✨ Свой вариант МОДЕЛИ\n",
            f"📏 **Длина изделия**: {length}\n",
            f"✂️ **Тип кроя штанов**: {cut}\n",
            f"🧥 **Длина рукава**: {sleeve}\n",
            f"🖼️ **Формат**: {aspect.replace('x', ':')}\n\n",
            "Все верно? Нажмите кнопку ниже для генерации."
        ]
    elif data.get("infographic_mode"):
        style = data.get("info_style") or "—"
        load = data.get("info_load") or "—"
        lang_code = data.get("info_lang") or "—"
        parts = [
            "📋 Проверьте выбранные параметры:\n\n",
            f"📦 **Категория**: 🖼️ Инфографика ({category})\n",
            f"🎨 **Стиль**: {style}\n",
            f"📊 **Нагруженность**: {load}\n",
            f"🌐 **Язык**: {lang_code}\n",
            f"🖼️ **Формат**: {aspect.replace('x', ':')}\n\n",
            "Все верно? Нажмите кнопку ниже для генерации."
        ]
    else:
        # Универсальная сборка параметров для остальных категорий
        cloth = data.get("cloth")
        height = data.get("height")
        age_key = data.get("age")
        age_map = {
            "20_26": "20-26 лет",
            "30_38": "30-38 лет",
            "40_48": "40-48 лет",
            "55_60": "55-60 лет",
        }
        age = age_map.get(age_key, age_key or "—")
        view_key = data.get("view")
        view_map = {"front": "Спереди", "back": "Сзади", "side": "Сбоку"}
        view = view_map.get(view_key, "Спереди")
        sleeve = data.get("sleeve") or "—"
        length = data.get("length") or "—"
        size = data.get("size") or "—"
        
        cat_name = "Женская" if category == "female" else "Мужская" if category == "male" else "Детская" if category == "child" else category
        
        parts = [
            "📋 Проверьте выбранные параметры:\n\n",
            f"📦 **Категория**: {cat_name}\n",
            f"👕 **Тип одежды**: {cloth}\n",
            f"📏 **Рост**: {height} см\n",
            f"🎂 **Возраст**: {age}\n",
            f"📏 **Длина изделия**: {length}\n",
            f"📐 **Телосложение**: {size}\n",
            f"🧥 **Рукав**: {sleeve}\n",
            f"👀 **Ракурс**: {view}\n",
            f"🖼️ **Формат**: {aspect.replace('x', ':')}\n\n",
            "Все верно? Нажмите кнопку ниже для генерации."
        ]
        
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
async def on_own_product_photo(message: Message, state: FSMContext, db: Database) -> None:
    prod_id = message.photo[-1].file_id
    await state.update_data(own_product_photo_id=prod_id)
    # Переходим к длине изделия с фотографией и кнопками
    await _ask_garment_length(message, state, db)


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
async def on_own_length(message: Message, state: FSMContext) -> None:
    length_text = (message.text or "").strip()
    if not length_text:
        await message.answer("Длина не может быть пустой. Укажите числом (см) или словами.")
        return
    await state.update_data(own_length=length_text)
    await state.set_state(CreateForm.waiting_own_sleeve)
    await message.answer("Выберите длину рукава:", reply_markup=sleeve_length_keyboard())


@router.callback_query(CreateForm.waiting_own_sleeve, F.data.startswith("form_sleeve:"))
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
    current = await state.get_data()
    if current.get("own_mode"):
        await state.update_data(own_sleeve=sleeve_map.get(val, ""))
        # Переходим к выбору формата
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)
        await _safe_answer(callback)
        return
    await _safe_answer(callback)


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


@router.callback_query(F.data.startswith("rand_gender:"))
async def on_random_gender(callback: CallbackQuery, state: FSMContext) -> None:
    g = callback.data.split(":", 1)[1]
    await state.update_data(rand_gender=g)
    await _replace_with_text(callback, "Где снимать?", reply_markup=random_loc_group_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("rand_locgroup:"))
async def on_random_locgroup(callback: CallbackQuery, state: FSMContext) -> None:
    group = callback.data.split(":", 1)[1]
    await state.update_data(rand_loc_group=group)
    await _replace_with_text(callback, "Выберите локацию:", reply_markup=random_location_keyboard(group))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("rand_location:"))
async def on_random_location(callback: CallbackQuery, state: FSMContext) -> None:
    loc = callback.data.split(":", 1)[1]
    await state.update_data(rand_location=loc)
    await _replace_with_text(callback, "Выберите вайб:", reply_markup=random_vibe_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "rand_location_custom")
async def on_random_location_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateForm.waiting_custom_location)
    await _replace_with_text(callback, "Введите кратко локацию (до 100 символов):")
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("rand_vibe:"))
async def on_random_vibe(callback: CallbackQuery, state: FSMContext) -> None:
    vibe = callback.data.split(":", 1)[1]
    await state.update_data(rand_vibe=vibe)
    data = await state.get_data()
    if data.get("rand_location") == "photo_studio":
        await _replace_with_text(callback, "Декор фотостудии:", reply_markup=random_decor_keyboard())
    elif data.get("random_other_mode"):
        # Для прочих товаров ракурс (крупный/полный рост) может быть не так важен как формат
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
        await state.set_state(CreateForm.waiting_aspect)
    else:
        await _replace_with_text(callback, "Выберите ракурс:", reply_markup=random_shot_keyboard())
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
    if model and model[3]:
        await _answer_model_photo(
            callback,
            model[3],
            text,
            model_select_keyboard(category, cloth, 0, total),
        )
    else:
        await _replace_with_text(callback, text, reply_markup=model_select_keyboard(category, cloth, 0, total))
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
        _, category, cloth, index_str = callback.data.split(":", 3)
        index = int(index_str)
    except Exception:
        await _safe_answer(callback)
        return
    total = await db.count_models(category, cloth)
    if total <= 0:
        await _safe_answer(callback, "Модели отсутствуют", show_alert=True)
        return
    # Получаем выбранную модель и её промт
    model = await db.get_model_by_index(category, cloth, index)
    if not model:
        await _safe_answer(callback, "Модель не найдена", show_alert=True)
        return
    model_id, name, prompt_id, _photo = model
    # сохраним ранее выставленные флаги (например, plus_mode)
    prev = await state.get_data()
    plus_mode_flag = bool(prev.get("plus_mode"))
    await state.clear()
    await state.update_data(category=category, cloth=cloth, index=index, model_id=model_id, prompt_id=prompt_id, plus_mode=plus_mode_flag)
    if cloth == "pants":
        await _replace_with_text(callback, "Выберите фасон брюк:", reply_markup=pants_style_keyboard())
        await state.set_state(CreateForm.waiting_pants_style)
    else:
        if category == "child":
            # Если пол уже выбран (через новый упрощенный флоу), переходим к росту
            if prev.get("child_gender"):
                await _replace_with_text(callback, "Введите рост ребенка в см (например: 130):")
                await state.set_state(CreateForm.waiting_height)
            else:
                # Старый флоу (на всякий случай)
            from bot.keyboards import child_gender_keyboard
            await _replace_with_text(callback, "Выберите пол ребёнка:", reply_markup=child_gender_keyboard())
            await state.set_state(CreateForm.waiting_child_gender)
        else:
            # Взрослые: обувь — рост → размер ноги → ракурс; одежда — телосложение → возраст → рост → длина → рукав → ракурс
            if cloth == "shoes":
                await _replace_with_text(callback, "Введите рост модели в см (например: 170):")
                await state.set_state(CreateForm.waiting_height)
            elif category == "storefront":
                # Для витринного фона: длина изделия → ракурс → фото
                await _ask_garment_length(callback, state, db)
            else:
                # Для 'all' (упрощенный флоу) или обычной одежды
                data_state = await state.get_data()
                if data_state.get("plus_mode") and cloth != "shoes":
                    # Режим Большой размер: размер не спрашиваем; запускаем выбор локации
                    await _replace_with_text(callback, "Выберите локацию:", reply_markup=plus_location_keyboard())
                    await state.set_state(CreateForm.plus_loc)
                else:
                    await _replace_with_text(callback, "Выберите телосложение:", reply_markup=form_size_keyboard(category))
                    await state.set_state(CreateForm.waiting_size)
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("pants_style:"))
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

    if data.get("infographic_mode"):
        await state.set_state(CreateForm.waiting_sleeve)
        await _replace_with_text(callback, "Выберите тип рукава (или пропустите):", reply_markup=sleeve_length_keyboard(lang))
        return

    if data.get("random_mode"):
        # В рандоме после выбора кроя — переходим к ракурсу
        await _replace_with_text(callback, "👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())
        await state.set_state(CreateForm.waiting_view)
    elif category == "child":
        await _replace_with_text(callback, "Введите возраст ребенка (в годах):")
        await state.set_state(CreateForm.waiting_age)
    else:
        # Для взрослых брюк: если режим Большой размер — далее локация; иначе телосложение
        if data.get("plus_mode"):
            await _replace_with_text(callback, "Выберите локацию:", reply_markup=plus_location_keyboard())
            await state.set_state(CreateForm.plus_loc)
        else:
            await _replace_with_text(callback, "Выберите телосложение:", reply_markup=form_size_keyboard(category))
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


@router.callback_query(F.data.startswith("form_age:"))
async def form_set_age(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await _safe_answer(callback)
        return
    # Если детская категория — игнорируем нажатия кнопок возраста
    if data.get("category") == "child":
        await _safe_answer(callback)
        return
    age_key = callback.data.split(":", 1)[1]
    await state.update_data(age=age_key)
    # Для взрослых — к росту; для детей — к росту
    if data.get("category") == "child":
        await _replace_with_text(callback, "📏 Напишите рост ребенка в см (например: 130):")
        await state.set_state(CreateForm.waiting_height)
    else:
        await _replace_with_text(callback, "📏 Введите рост модели в см (например: 170):")
        await state.set_state(CreateForm.waiting_height)
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
        if cloth == "shoes":
            await state.set_state(CreateForm.waiting_view)
            await message.answer("👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())
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
    
    # ... логика маппинга размеров ...
    size_map = {
        "thin": "Худая и стройная",
        "curvy": "Телосложение пышное и полные ноги пухлое лицо.",
        "plus": "Size Plus очень крупное и пышное телосложение полные ноги и круглое и пухлое лицо.",
    }
    if category == "male":
        size_map = {
            "thin": "Худой и стройный",
            "curvy": "Телосложение пышное и полные ноги, пухлое лицо.",
            "plus": "Size Plus очень крупное и пышное телосложение, полные ноги и круглое пухлое лицо.",
        }
    
    await state.update_data(size=size_map.get(val, ""))
    
    if data.get("infographic_mode"):
        await _replace_with_text(callback, "Введите рост модели в см (например: 170):")
        await state.set_state(CreateForm.waiting_height)
    elif data.get("random_mode"):
        # ... существующая логика рандома ...
        await _ask_garment_length(callback, state, db)
    elif data.get("category") in ("female", "male") and (data.get("cloth") != "shoes"):
        await _replace_with_text(callback, "🎂 Пожалуйста выберите возраст модели:", reply_markup=form_age_keyboard())
        await state.set_state(CreateForm.waiting_age)
    else:
        await _replace_with_text(callback, "📏 Введите рост модели в см (например: 170):")
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
    category = data.get("category")
    cloth = data.get("cloth")
    # Взрослая обувь: после роста — размер ноги, затем ракурс
    if category in ("female", "male") and cloth == "shoes":
        await state.set_state(CreateForm.waiting_foot)
        await message.answer("Введите размер обуви (например: 38):")
        return
    # Для всех типов одежды, кроме обуви — спрашиваем длину изделия
    if category in ("female", "male") and cloth != "shoes":
        await _ask_garment_length(message, state, db)
        return
    # Детская одежда: после роста — возраст (можно Пропустить), затем длина изделия
    if category == "child" and cloth != "shoes":
        await state.set_state(CreateForm.waiting_age)
        await message.answer("Введите возраст ребенка (числом) или отправьте 'Пропустить':")
        return
    # Рандом-режим: после роста — размеры (для male/female), затем длина изделия
    if data.get("random_mode"):
        rand_gender = data.get("rand_gender")
        if rand_gender in ("male", "female"):
            await state.set_state(CreateForm.waiting_size)
            await message.answer("Выберите телосложение:", reply_markup=form_size_keyboard("male" if rand_gender=="male" else "female"))
            return
        # дети в рандоме: без телосложения — сразу к длине
        await _ask_garment_length(message, state, db)
        return
    # Детская обувь: после роста — сразу ракурс (размер уже спросили до роста)
    if category == "child" and cloth == "shoes":
        await state.set_state(CreateForm.waiting_view)
        await message.answer("👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())
        return
    # Прочие случаи: по умолчанию — длина изделия, затем рукав
    await _ask_garment_length(message, state, db)


@router.callback_query(F.data.startswith("garment_len:"))
async def on_garment_len_callback(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    
    if val == "custom":
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, get_string("enter_length_custom", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_length)
        await _safe_answer(callback)
        return

    # Маппинг значений для промпта
    len_map = {
        "short_top": "короткий топ",
        "regular_top": "обычный топ",
        "to_waist": "до талии",
        "below_waist": "ниже талии",
        "mid_thigh": "до середины бедра",
        "to_knees": "до колен",
        "below_knees": "ниже колен",
        "midi": "миди",
        "to_ankles": "до щиколоток",
        "to_floor": "в пол",
        "skip": ""
    }
    
    length_val = len_map.get(val, "")
    await state.update_data(length=length_val)
    
    # Фолбэк для own_mode (если это был Свой Вариант Модели)
    if data.get("own_mode"):
        await state.update_data(own_length=length_val)
        lang = await db.get_user_language(callback.from_user.id)
        await state.set_state(CreateForm.waiting_own_cut)
        await _replace_with_text(callback, get_string("select_pants_style", lang), reply_markup=pants_style_keyboard(lang))
        await _safe_answer(callback)
        return

    # Обычный флоу
    cloth = data.get("cloth")
    plus_mode = bool(data.get("plus_mode"))
    
    if data.get("random_mode") or cloth == "dress" or (plus_mode and cloth in ("top", "coat", "suit", "overall", "loungewear")):
        await state.set_state(CreateForm.waiting_sleeve)
        await _replace_with_text(callback, "Clothing Sleeve Length: выберите длину рукава или пропустите", reply_markup=sleeve_length_keyboard())
    elif plus_mode and cloth == "pants":
        await state.set_state(CreateForm.waiting_pants_style)
        await _replace_with_text(callback, "Тип кроя штанов (опционально):", reply_markup=pants_style_keyboard())
    else:
        await state.set_state(CreateForm.waiting_view)
        await _replace_with_text(callback, "👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())
    
    await _safe_answer(callback)


@router.message(CreateForm.waiting_length)
async def form_set_length(message: Message, state: FSMContext, db: Database) -> None:
    length = message.text.strip()
    await state.update_data(length=length)
    data = await state.get_data()
    lang = await db.get_user_language(message.from_user.id)
    
    if data.get("own_mode"):
        await state.update_data(own_length=length)
        await state.set_state(CreateForm.waiting_own_cut)
        await message.answer(get_string("select_pants_style", lang), reply_markup=pants_style_keyboard(lang))
        return

    cloth = data.get("cloth")
    plus_mode = bool(data.get("plus_mode"))
    # В Большом размере спрашиваем рукав для верхних вещей и платьев
    if data.get("random_mode"):
        # В рандоме всегда предложим длину рукава
        await state.set_state(CreateForm.waiting_sleeve)
        await message.answer("Clothing Sleeve Length: выберите длину рукава или пропустите", reply_markup=sleeve_length_keyboard())
    elif cloth == "dress" or (plus_mode and cloth in ("top", "coat", "suit", "overall", "loungewear")):
        await state.set_state(CreateForm.waiting_sleeve)
        await message.answer("Clothing Sleeve Length: выберите длину рукава или пропустите", reply_markup=sleeve_length_keyboard())
    elif plus_mode and cloth == "pants":
        # В Большом размере спросим крой брюк
        await state.set_state(CreateForm.waiting_pants_style)
        await message.answer("Тип кроя штанов (опционально):", reply_markup=pants_style_keyboard())
    else:
        await state.set_state(CreateForm.waiting_view)
        await message.answer("👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())


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
    await state.set_state(CreateForm.waiting_view)
    await message.answer("👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())


@router.callback_query(CreateForm.waiting_sleeve, F.data.startswith("form_sleeve:"))
async def form_set_sleeve(callback: CallbackQuery, state: FSMContext) -> None:
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
    await state.update_data(sleeve=sleeve_map.get(val, ""))
    # В рандом-режиме после рукава спросим тип кроя брюк (опционально), затем ракурс
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    if data.get("infographic_mode"):
        await state.set_state(CreateForm.waiting_info_angle)
        # Угол камеры (Спереди/Сзади) - переиспользуем form_view_keyboard
        await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
        return

    if data.get("random_mode"):
        await _replace_with_text(callback, "Тип кроя штанов (опционально):", reply_markup=pants_style_keyboard())
        await state.set_state(CreateForm.waiting_pants_style)
    else:
        await _replace_with_text(callback, "👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())
        await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_info_angle, F.data.startswith("form_view:"))
async def on_info_angle(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    view = callback.data.split(":", 1)[1]
    await state.update_data(info_angle=view)
    lang = await db.get_user_language(callback.from_user.id)
    # Далее Ракурс (Дальний/Средний/Близкий) - angle_keyboard
    await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=angle_keyboard(lang))
    await state.set_state(CreateForm.waiting_view) # Используем для выбора дистанции
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_view, F.data.startswith("angle:"))
async def on_info_dist(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    dist = callback.data.split(":", 1)[1]
    await state.update_data(info_dist=dist)
    lang = await db.get_user_language(callback.from_user.id)
    # Далее Поза (Вульгарная-Нестандратный-Обычный)
    from bot.keyboards import pose_keyboard
    await _replace_with_text(callback, "Выберите позу модели:", reply_markup=pose_keyboard(lang))
    await state.set_state(CreateForm.waiting_info_pose)
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_info_pose, F.data.startswith("pose:"))
async def on_info_pose(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    pose = callback.data.split(":", 1)[1]
    await state.update_data(info_pose=pose)
    # Далее Длина изделия
    await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("form_view:"))
async def form_set_view(callback: CallbackQuery, state: FSMContext) -> None:
    view = callback.data.split(":", 1)[1]
    await state.update_data(view=view)
    # Сразу просим фото, формат выбирается автоматически
    text = (
        "📸 Пожалуйста пришлите фотографию вашего товара.\n\n"
        "⚠️ Обратите внимание: фотография должна быть четкой без лишних бликов и размытостей.\n\n"
        "Если остались вопросы - пишите в поддержку @bnbslow"
    )
    # Устанавливаем состояние ожидания фото
    await state.set_state(CreateForm.waiting_view)
    await _replace_with_text(callback, text)
    await _safe_answer(callback)



@router.message(CreateForm.waiting_view, F.photo)
async def handle_user_photo(message: Message, state: FSMContext, db: Database) -> None:
    # Принимаем фото товара только на шаге waiting_view и только при наличии фото
    data = await state.get_data()
    if not data:
        return
    photo_id = message.photo[-1].file_id
    await state.update_data(user_photo_id=photo_id)
    lang = await db.get_user_language(message.from_user.id)

    if data.get("normal_gen_mode"):
        # Для обычной генерации просим промпт
        await message.answer(get_string("enter_prompt", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_prompt)
        return

    # Собираем параметры для других режимов
    category = data.get("category")
    cloth = data.get("cloth")
    # Тип фигуры (телосложение) теперь используется — берём из state
    height = data.get("height")
    length = data.get("length") or "—"
    age_key = data.get("age")
    age_map = {
        "20_26": "Молодая модель возраста 20-26 лет",
        "30_38": "Взрослая модель возраста 30-38 лет",
        "40_48": "Зрелая модель возраста 40-48 лет",
        "55_60": "Пожилая модель возраста 55-60 лет",
    }
    age = age_map.get(age_key, age_key or "—")
    view_key = data.get("view")
    view_map_readable = {"front": "Передняя часть", "back": "Сзади", "side": "Сбоку"}
    view = view_map_readable.get(view_key, "Передняя часть")
    aspect = data.get("aspect", "auto")
    sleeve = data.get("sleeve") or "—"
    size_desc = data.get("size") or "—"
    foot_size = data.get("foot_size")
    gender = data.get("gender")

    # Формируем текст подтверждения безопасно через список частей
    parts = []
    
    parts.append("📋 Проверьте выбранные параметры:\n\n")
    parts.append(f"📦 **Категория**: {('Женская' if category=='female' else 'Мужская' if category=='male' else 'Детская')}\n")
    if gender:
        parts.append(f"🚻 **Пол**: {gender}\n")
    parts.append(f"👕 **Тип одежды**: {cloth}\n")
    rm = data.get("random_mode")
    parts.append("**Режим**: 🎨 Рандом\n" if rm else "**Режим**: 🎨 Модель (фон)\n")
    parts.append(f"📏 **Рост модели**: {height} см\n")
    parts.append(f"🎂 **Возраст модели**: {age}\n")
    # Плюс-режим: дополнительные поля
    if data.get("plus_mode"):
        loc_map = {
            "outdoor":"На улице",
            "wall":"Возле стены",
            "car":"Возле машины",
            "park":"В парке",
            "bench":"У лавочки",
            "restaurant":"Возле ресторана",
            "studio":"Фотостудия",
        }
        season_map = {"winter":"Зима","summer":"Лето","spring":"Весна","autumn":"Осень"}
        vibe_map = {"decor":"С декором элементами","plain":"Без декора","normal":"Обычный"}
        if data.get('plus_loc'):
            parts.append(f"📍 **Локация**: {loc_map.get(data.get('plus_loc'))}\n")
        if data.get('plus_season'):
            parts.append(f"🕒 **Сезон**: {season_map.get(data.get('plus_season'))}\n")
        if data.get('plus_vibe'):
            parts.append(f"🎞 **Вайб**: {vibe_map.get(data.get('plus_vibe'))}\n")
    if category in ("female","male") and cloth != 'shoes':
        parts.append(f"📐 **Телосложение**: {size_desc}\n")
    parts.append(f"👀 **Ракурс**: {view}\n")
    if not (category == 'child' and cloth=='shoes') and cloth != 'pants':
        parts.append(f"🧥 **Длина рукав**: {sleeve}\n")
    if cloth == 'shoes' and foot_size:
        parts.append(f"👣 **Размер ноги**: {foot_size}\n")
    # Рандом — дополнительные поля
    if rm:
        loc_group = data.get("rand_loc_group")
        location = data.get("rand_location")
        vibe = data.get("rand_vibe")
        decor = data.get("rand_decor")
        shot = data.get("rand_shot")
        pants_style = data.get("pants_style")
        gender_map = {"male":"Мужчина","female":"Женщина","boy":"Мальчик","girl":"Девочка"}
        parts.append(f"🚻 **Пол**: {gender_map.get(data.get('rand_gender'),'—')}\n")
        loc_map = {"inside_restaurant":"Внутри ресторана","photo_studio":"В фотостудии","coffee_shop":"У кофейни (внутри)","city":"В городе","building":"У здания","wall":"У стены","park":"В парке","coffee_shop_out":"У кофейни (снаружи)","forest":"В лесу","car":"У машины"}
        vibe_map = {"summer":"Лето","winter":"Зима","autumn":"Осень","spring":"Весна"}
        if location:
            if location == 'custom':
                custom = (data.get('rand_location_custom') or '').strip()
                if custom:
                    parts.append(f"📍 **Локация**: {custom}\n")
            else:
                parts.append(f"📍 **Локация**: {loc_map.get(location, location)}\n")
        if vibe:
            parts.append(f"🎞 **Вайб**: {vibe_map.get(vibe, vibe)}\n")
        if location == 'photo_studio' and decor:
            parts.append(f"🎀 **Декор студии**: {'С декором' if decor=='decor' else 'Без декора'}\n")
        if shot:
            shot_view = "В полный рост" if shot == 'full' else "Близкий ракурс"
            parts.append(f"🎯 **Ракурс**: {shot_view}\n")
        if pants_style and pants_style != 'skip':
            style_map = {"relaxed":"Свободный крой","slim":"Зауженный","banana":"Бананы","flare_knee":"Клеш от колен","baggy":"Багги","mom":"Мом","straight":"Прямые"}
            parts.append(f"👖 **Крой штанов**: {style_map.get(pants_style, pants_style)}\n")
    # Плюс-режим: отобразим выбранный крой
    if data.get('plus_mode'):
        pstyle = data.get('pants_style')
        if pstyle and pstyle != 'skip':
            style_map = {"relaxed":"Свободный крой","slim":"Зауженный","banana":"Бананы","flare_knee":"Клеш от колен","baggy":"Багги","mom":"Мом","straight":"Прямые"}
            parts.append(f"👖 **Крой штанов**: {style_map.get(pstyle, pstyle)}\n")
    if aspect and aspect != "auto":
        parts.append(f"🖼️ **Формат**: {aspect.replace('x', ':')}")
    text = ''.join(parts)
    
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    await state.set_state(CreateForm.waiting_aspect)


@router.callback_query(F.data == "back_step", CreateForm.waiting_size)
async def on_back_from_size(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    category = data.get("category")
    cloth = data.get("cloth")
    index = data.get("index", 0)
    await on_model_nav(callback, db) # Re-use model navigation

@router.callback_query(F.data == "back_step", CreateForm.waiting_age)
async def on_back_from_age(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    category = data.get("category")
    lang = await db.get_user_language(callback.from_user.id)
    if data.get("plus_mode"):
        await _replace_with_text(callback, "Выберите вайб:", reply_markup=plus_vibe_keyboard(lang))
        await state.set_state(CreateForm.plus_vibe)
    else:
        await _replace_with_text(callback, "Выберите телосложение:", reply_markup=form_size_keyboard(category, lang))
        await state.set_state(CreateForm.waiting_size)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_height)
async def on_back_from_height(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
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
    if data.get("category") == "storefront":
        await on_marketplace_menu(callback, db)
    else:
        await _replace_with_text(callback, "📏 Введите рост модели в см (например: 170):")
        await state.set_state(CreateForm.waiting_height)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_sleeve)
async def on_back_from_sleeve(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await _ask_garment_length(callback, state, db)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_view)
async def on_back_from_view(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if data.get("infographic_mode"):
        await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=angle_keyboard(lang))
        await state.set_state(CreateForm.waiting_view) # Used for distance selection
    elif data.get("random_mode") or data.get("cloth") == "shoes":
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
    await on_model_nav(callback, db)

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

@router.callback_query(F.data == "back_step", CreateForm.waiting_custom_location)
async def on_back_from_custom_loc(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "Где будет находиться товар?", reply_markup=random_loc_group_keyboard(lang))
    await state.set_state(None)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_has_person)
async def on_back_from_has_person(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_create_photo(callback, db, state)

@router.callback_query(F.data == "back_step", CreateForm.waiting_child_gender)
async def on_back_from_child_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_model_nav(callback, db)

@router.callback_query(F.data == "back_step", CreateForm.waiting_pants_style)
async def on_back_from_pants_style(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    if data.get("random_mode"):
        await state.set_state(CreateForm.waiting_sleeve)
        lang = await db.get_user_language(callback.from_user.id)
        await _replace_with_text(callback, "Выберите длину рукава:", reply_markup=sleeve_length_keyboard(lang))
    else:
        await on_model_nav(callback, db)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_info_lang_custom)
async def on_back_from_info_lang_custom(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import info_lang_keyboard
    await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
    await state.set_state(None)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_has_person)
async def on_back_from_rand_other_person(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_marketplace_menu(callback, db)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_gender)
async def on_back_from_rand_other_gender(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import yes_no_keyboard
    await _replace_with_text(callback, get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_has_person)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_load)
async def on_back_from_rand_other_load(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if data.get("has_person"):
        from bot.keyboards import random_other_gender_keyboard
        await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=random_other_gender_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_gender)
    else:
        from bot.keyboards import yes_no_keyboard
        await _replace_with_text(callback, get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))
        await state.set_state(CreateForm.waiting_rand_other_has_person)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_name)
async def on_back_from_rand_other_name(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_info_load", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_load)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_angle)
async def on_back_from_rand_other_angle(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("enter_product_name", lang), reply_markup=back_step_keyboard(lang))
    await state.set_state(CreateForm.waiting_rand_other_name)

@router.callback_query(F.data == "back_step", CreateForm.waiting_rand_other_dist)
async def on_back_from_rand_other_dist(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "Выберите угол камеры (Спереди/Сзади):", reply_markup=form_view_keyboard(lang))
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
async def on_back_from_own_aspect(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if data.get("category") == "own_variant":
        await _replace_with_text(callback, get_string("upload_product", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_own_product_photo)
    elif data.get("own_mode"):
        # Для own_mode возвращаемся к рукаву
        await state.set_state(CreateForm.waiting_own_sleeve)
        await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))
    else:
        # fallback for other flows
        await on_create_photo(callback, db, state)
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

@router.callback_query(F.data == "back_step", CreateForm.result_ready)
async def on_back_from_result(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    await state.set_state(CreateForm.waiting_aspect)
    await _safe_answer(callback)

@router.callback_query(F.data == "back_step")
async def on_back_step_fallback(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Если ни один стейт-специфичный хендлер не сработал
    await on_back_main(callback, state, db)
async def on_back_from_own_aspect(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if data.get("category") == "own_variant":
        await _replace_with_text(callback, get_string("upload_product", lang), reply_markup=back_step_keyboard(lang))
        await state.set_state(CreateForm.waiting_own_product_photo)
    elif data.get("own_mode"):
        # Для own_mode возвращаемся к рукаву
        await state.set_state(CreateForm.waiting_own_sleeve)
        await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))
    else:
        # fallback for other flows
        await on_create_photo(callback, db, state)
    await _safe_answer(callback)


@router.callback_query(F.data == "form_generate")
async def form_generate(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    user_id = callback.from_user.id
    logger.info(f"[form_generate] Начало генерации для пользователя {user_id}")
    
    # Проверка техработ
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, get_string("maintenance_alert", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return

    try:
        sub = await db.get_user_subscription(user_id)
        if not sub:
            await _safe_answer(callback, get_string("limit_rem_zero", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return
        
        # sub structure: (plan_type, expires_at, daily_limit, daily_usage, ind_key)
        plan_type, expires_at, daily_limit, daily_usage, ind_key = sub
        if daily_usage >= daily_limit:
            await _safe_answer(callback, get_string("limit_rem_zero", await db.get_user_language(callback.from_user.id)), show_alert=True)
            return

        quality = '4K' if '4K' in plan_type.upper() else 'HD'

        data = await state.get_data()
        lang = await db.get_user_language(user_id)
        if not data:
            await _safe_answer(callback, get_string("session_not_found", lang), show_alert=True)
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

        prompt_text = ""
    if data.get("random_mode"):
        prompt_text = ""
        elif data.get("category") == "own_variant":
            # Промпт для своего варианта фона
            base = await db.get_own_variant_prompt() or "Professional fashion photography. Place the product from the second image onto the background from the first image. Maintain natural lighting, shadows, and perspective. High quality, 8k resolution."
            prompt_text = base
    else:
        if data.get("category") == "whitebg":
            base = await db.get_whitebg_prompt()
            prompt_text = base or ""
        else:
            pid = data.get('prompt_id')
            prompt_text = await db.get_prompt_text(int(pid)) if pid else ""
        
    # Приводим возраст и длину рукава к финальному виду для промта
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
            own_cut = (data.get("own_cut") or "")
            # Упрощенный промпт без генерации описания модели
            base = await db.get_own_prompt3() or "Professional fashion photography. Place the product from the second image on the model from the first image, maintaining the same pose, lighting, and background style. High quality, realistic, natural lighting."
            prompt_filled = base
            if own_length:
                prompt_filled += f" Garment length: {own_length}."
            if own_sleeve:
                prompt_filled += f" Sleeve length: {own_sleeve}."
            if own_cut:
                prompt_filled += f" Cut style: {own_cut}."
        elif data.get("random_other_mode"):
            has_person = data.get("has_person")
            gender = data.get("gender")
            load = data.get("info_load")
            product_name = data.get("product_name")
            view_key = data.get("view")
            dist = data.get("dist")
            h_cm = data.get("height_cm")
            w_cm = data.get("width_cm")
            l_cm = data.get("length_cm")
            season = data.get("season")
            style = data.get("style")
            
            view_word = {"back": "сзади", "front": "спереди", "side": "сбоку"}.get(view_key, "спереди")
            dist_word = {"far": "дальний", "medium": "средний", "close": "близкий"}.get(dist, "средний")
            gender_word = {"male": "Мужчина", "female": "Женщина", "boy": "Мальчик", "girl": "Девочка"}.get(gender, "")
            
            p_parts = ["Professional commercial product photography. High quality, ultra realistic lighting. "]
            p_parts.append(f"Product: {product_name}. ")
            
            if has_person:
                p_parts.append(f"A {gender_word} is in the scene with the product. ")
            else:
                p_parts.append("No people in the shot, focus strictly on the product itself. ")
            
            p_parts.append(f"Infographic load: {load}/10. ")
            p_parts.append(f"Camera angle: {view_word}, Distance: {dist_word}. ")
            
            dims = []
            if h_cm: dims.append(f"height {h_cm}cm")
            if w_cm: dims.append(f"width {w_cm}cm")
            if l_cm: dims.append(f"length {l_cm}cm")
            if dims:
                p_parts.append(f"Product dimensions: {', '.join(dims)}. ")
            
            if season:
                p_parts.append(f"Season/Vibe: {season}. ")
            if style:
                p_parts.append(f"Style: {style}. ")
                
            p_parts.append("8k resolution, cinematic lighting, sharp focus on product.")
            prompt_filled = "".join(p_parts)
        elif data.get("normal_gen_mode"):
            prompt_filled = data.get("prompt") or ""
    elif data.get("random_mode"):
        gender = data.get("rand_gender")
        gender_map = {"male":"мужчина","female":"женщина","boy":"мальчик","girl":"девочка"}
        loc_map = {"inside_restaurant":"внутри ресторана","photo_studio":"в фотостудии","coffee_shop":"в кофейне","city":"в городе","building":"у здания","wall":"у стены","park":"в парке","coffee_shop_out":"у кофейни","forest":"в лесу","car":"у машины"}
        vibe_map = {"summer":"летний", "winter":"зимний", "autumn":"осенний", "spring":"весенний"}
        p_parts: list[str] = []
            p_parts.append(f"{gender_map.get(gender, 'модель')} ")
            if age_text: p_parts.append(f"{age_text}. ")
        h = data.get("height")
            if h: p_parts.append(f"Рост {h} см. ")
            if size_text: p_parts.append(f"{size_text}. ")
        loc = data.get("rand_location")
        if loc:
            if loc == 'custom':
                custom = (data.get('rand_location_custom') or '').strip()
                    if custom: p_parts.append(f"Съёмка {custom}. ")
            else:
                    p_parts.append(f"Съёмка {loc_map.get(loc, loc)}. ")
        vibe = data.get("rand_vibe")
            if vibe: p_parts.append(f"Вайб: {vibe_map.get(vibe, vibe)}. ")
        shot = data.get("rand_shot")
        if shot:
            shot_map = {"full":"в полный рост", "close":"близкий ракурс"}
                p_parts.append(f"Ракурс: {shot_map.get(shot, shot)}. ")
        L = (data.get("length") or "").strip()
            if L: p_parts.append(f"Длина изделия: {L}. ")
            if sleeve_text: p_parts.append(f"Длина рукава: {sleeve_text}. ")
        view_txt = "сзади" if data.get("view") == "back" else "спереди"
            p_parts.append(f"Вид: {view_txt}. Профессиональное фото, реалистичный свет, высокое качество.")
        base_random = await db.get_random_prompt() or ""
            prompt_filled = (base_random + "\n\n" + ''.join(p_parts)).strip()
    else:
        view_key = data.get("view")
        view_word = {"back": "сзади", "front": "спереди", "side": "сбоку"}.get(view_key, "спереди")
            
            # Собираем все возможные замены для промпта
            replacements = {
                "{размер}": size_text,
                "{Размер модели}": size_text,
                "{Размер тела модели}": size_text,
                "{рост}": str(data.get("height", "")),
                "{Рост модели}": str(data.get("height", "")),
                "{длина изделия}": str(data.get("length", "")),
                "{Длина изделия}": str(data.get("length", "")),
                "{возраст}": age_text,
                "{Возраст модели}": age_text,
                "{длина рукав}": sleeve_text,
                "{Тип рукава}": sleeve_text,
                "{сзади/спереди}": view_word,
                "{Угол камеры}": view_word,
                "{Пол модели}": "мужчина" if data.get("category") == "male" else "женщина" if data.get("category") == "female" else "ребенок",
            }
            
            prompt_filled = prompt_text or ""
            for placeholder, value in replacements.items():
                prompt_filled = prompt_filled.replace(placeholder, str(value))
                
            if data.get("category") == "whitebg":
                prompt_filled += f" Ракурс: {view_word}. Белый фон, студийный свет."

        if quality == '4K':
            prompt_filled += " High quality, 4K resolution, ultra detailed."

        lang = await db.get_user_language(user_id)
        await _replace_with_text(callback, get_string("gen_in_progress", lang), reply_markup=None)
    await _safe_answer(callback)
        progress_msg = await callback.message.answer("⏳")
    stop_event = asyncio.Event()
    asyncio.create_task(_run_generation_progress(callback.bot, callback.message.chat.id, progress_msg.message_id, stop_event))

        # Загрузка фото
        image_bytes = None
        reference_bytes = None
        
        if category == "own_variant":
            bg_id = data.get("own_bg_photo_id")
        prod_id = data.get("own_product_photo_id")
            if bg_id and prod_id:
                bg_file = await callback.bot.get_file(bg_id)
                bg_f = await callback.bot.download_file(bg_file.file_path)
                reference_bytes = bg_f.read()
                prod_file = await callback.bot.get_file(prod_id)
                prod_f = await callback.bot.download_file(prod_file.file_path)
                image_bytes = prod_f.read()
        elif data.get("own_mode"):
            # Загружаем фото продукта
            prod_id = data.get("own_product_photo_id")
            if prod_id:
        prod_file = await callback.bot.get_file(prod_id)
        prod_bytes = await callback.bot.download_file(prod_file.file_path)
        image_bytes = prod_bytes.read()
            # Загружаем фото модели (референс)
            ref_id = data.get("own_ref_photo_id")
            if ref_id:
        ref_file = await callback.bot.get_file(ref_id)
                ref_bytes = await callback.bot.download_file(ref_file.file_path)
                reference_bytes = ref_bytes.read()
    else:
        user_photo_id = data.get("user_photo_id")
            if user_photo_id:
        file = await callback.bot.get_file(user_photo_id)
        file_bytes = await callback.bot.download_file(file.file_path)
        image_bytes = file_bytes.read()
                # Референс (модель)
                if not data.get("random_mode"):
                    model = await db.get_model_by_index(category, data.get("cloth"), data.get("index"))
                    if model and model[3]:
                        ref_file = await callback.bot.get_file(model[3])
                        ref_f = await callback.bot.download_file(ref_file.file_path)
                        reference_bytes = ref_f.read()

        if not image_bytes:
            stop_event.set()
            await callback.message.answer("Ошибка: фото не загружено.")
            return

        # Ротация ключей
    settings = load_settings()
        
        # Определяем, какую таблицу ключей использовать
        is_own_variant = (category == "own_variant")
        
        if is_own_variant:
            # Для "Своего варианта фона" используем специальные ключи
            keys_with_ids = await db.list_own_variant_api_keys()
            # list_own_variant_api_keys возвращает (id, token, is_active)
            tokens_order = []
            for kid, tok, is_active in keys_with_ids:
                if is_active:
                    tokens_order.append((kid, tok))
        else:
            # Для всех остальных (включая Обычную генерацию) используем общие ключи Gemini
    keys_with_ids = await db.list_api_keys()
            # list_api_keys возвращает 9 колонок
            tokens_order = []
            for kid, tok, is_active, prio, du, tu, lr, ca, ua in keys_with_ids:
                if is_active:
                    # Проверяем лимиты перед добавлением в список
                    can_use, reason = await db.check_api_key_limits(kid)
                    if can_use:
                        tokens_order.append((kid, tok))
                    else:
                        logger.info(f"API key {kid} skipped: {reason}")
        
        # Если есть индивидуальный ключ для 4K
        if quality == '4K' and ind_key:
            tokens_order.insert(0, (None, ind_key))
        
        if not tokens_order:
            stop_event.set()
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=progress_msg.message_id, text="❌ " + get_string("gen_error", lang))
            await callback.message.answer(get_string("gen_error", lang) + "\n\n⚠️ Все API ключи исчерпали лимиты. Обратитесь к администратору.")
            return
        
    result_bytes = None
        last_error = None
        aspect_ratio = data.get("aspect", "1:1").replace("x", ":")
    for key_id, token in tokens_order:
        try:
                # Дополнительная проверка перед использованием
                if key_id:
                    can_use, reason = await db.check_api_key_limits(key_id)
                    if not can_use:
                        logger.info(f"API key {key_id} limit reached before use: {reason}")
                        continue
                
                result_bytes = await generate_image(token, prompt_filled, image_bytes, reference_bytes, aspect_ratio=aspect_ratio, key_id=key_id, db_instance=db)
            if result_bytes:
                    if key_id: 
                        await db.record_api_usage(key_id)
                        # Проверяем, не достиг ли ключ лимита после использования
                        can_use, reason = await db.check_api_key_limits(key_id)
                        if not can_use and "Total limit" in reason:
                            logger.info(f"API key {key_id} reached total limit after usage, deactivated")
                break
        except Exception as e:
            last_error = e
                error_str = str(e)
                
                # Определяем тип ошибки и записываем в БД
                # Проверяем атрибуты исключения из gemini.py
                is_proxy_error = getattr(e, 'is_proxy_error', False) or any(x in error_str.lower() for x in ["proxy", "connection", "timeout", "network"])
                status_code = getattr(e, 'status_code', None)
                error_type = getattr(e, 'error_type', None)
                
                if status_code is None:
                    if "429" in error_str:
                        status_code = 429
                    elif "400" in error_str:
                        status_code = 400
                
                if error_type is None:
                    error_type = "429" if status_code == 429 else ("quota" if "quota" in error_str.lower() else ("proxy" if is_proxy_error else "unknown"))
                
                # Получаем preview ключа для логирования
                api_key_preview = token[:10] + "..." if len(token) > 10 else token
                
                # Записываем ошибку в БД
                if key_id:
                    await db.record_api_error(key_id, api_key_preview, error_type, error_str[:500], status_code, is_proxy_error)
                    
                    if "quota" in error_str.lower() or status_code == 429:
                    await db.update_api_key(key_id, is_active=0)
            continue

        stop_event.set()
        if result_bytes:
            # Списание
            total_after = total_tenths - price_tenths
            new_balance = total_after // 10
            new_frac = total_after % 10
            await db.increment_user_balance(user_id, new_balance - balance)
            await db.set_user_fraction(user_id, new_frac)
            await db.update_daily_usage(user_id)
            
        photo_file = BufferedInputFile(result_bytes, filename="result.png")
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=progress_msg.message_id, text="✅ " + get_string("gen_ready", lang))
            
            kb = result_actions_own_keyboard(lang) if category == "own_variant" else result_actions_keyboard(lang)
            await callback.message.answer_document(document=photo_file, caption=get_string("gen_success", lang), reply_markup=kb)
    await state.set_state(CreateForm.result_ready)
        else:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=progress_msg.message_id, text=get_string("gen_error_contact_support", lang))

    except Exception as e:
        logger.error(f"Глобальная ошибка в form_generate: {e}", exc_info=True)
        await callback.message.answer("Произошла неожиданная ошибка при генерации.")


@router.callback_query(F.data == "result_edit")
async def on_result_edit(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.set_state(CreateForm.waiting_edit_text)
    lang = await db.get_user_language(callback.from_user.id)
    # Не трогаем предыдущее сообщение с фото, отправляем новое
    await callback.message.answer(get_string("enter_edit_description", lang))
    await _safe_answer(callback)


@router.message(CreateForm.waiting_edit_text)
async def on_result_edit_text(message: Message, state: FSMContext, db: Database) -> None:
    edit_text = message.text.strip()
    data = await state.get_data()
    # Восстановим последние параметры (если нужно — можно хранить их отдельно перед генерацией)
    category = data.get("category")
    cloth = data.get("cloth")
    prompt_id = data.get("prompt_id")
    if data.get("random_mode"):
        # Сборка промта как в form_generate для рандома
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
        gender = data.get("rand_gender")
        gender_map = {"male":"мужчина","female":"женщина","boy":"мальчик","girl":"девочка"}
        loc_map = {"inside_restaurant":"внутри ресторана","photo_studio":"в фотостудии","coffee_shop":"в кофейне","city":"в городе","building":"у здания","wall":"у стены","park":"в парке","coffee_shop_out":"у кофейни","forest":"в лесу","car":"у машины"}
        vibe_map = {"summer":"летний", "winter":"зимний", "autumn":"осенний", "spring":"весенний"}
        parts: list[str] = []
        parts.append(f"{gender_map.get(gender, 'модель')} ")
        if age_text:
            parts.append(f"{age_text}. ")
        h = data.get("height")
        if h:
            parts.append(f"Рост {h} см. ")
        if size_text:
            parts.append(f"{size_text}. ")
        loc = data.get("rand_location")
        if loc:
            parts.append(f"Съёмка {loc_map.get(loc, loc)}. ")
        vibe = data.get("rand_vibe")
        if vibe:
            parts.append(f"Вайб: {vibe_map.get(vibe, vibe)}. ")
        shot = data.get("rand_shot")
        if shot:
            shot_map = {"full":"в полный рост", "close":"близкий ракурс"}
            parts.append(f"Ракурс: {shot_map.get(shot, shot)}. ")
        if loc == 'photo_studio':
            decor = data.get("rand_decor")
            if decor:
                parts.append(f"Студия: {'с декором' if decor=='decor' else 'без декора'}. ")
        L = (data.get("length") or "").strip()
        if L:
            parts.append(f"Длина изделия: {L}. ")
        if sleeve_text:
            parts.append(f"Длина рукава: {sleeve_text}. ")
        pants_style = data.get("pants_style")
        if pants_style and pants_style != 'skip':
            style_map = {"relaxed":"Свободный крой","slim":"Зауженный","banana":"Бананы","flare_knee":"Клеш от колен","baggy":"Багги","mom":"Мом","straight":"Прямые"}
            parts.append(f"Крой штанов: {style_map.get(pants_style, pants_style)}. ")
        view_txt = "сзади" if data.get("view") == "back" else "спереди"
        parts.append(f"Вид: {view_txt}. Профессиональное фото, реалистичный свет, высокое качество.")
        base_random = await db.get_random_prompt() or ""
        prompt_filled = (base_random + "\n\n" + ''.join(parts) + "\n\nПравки: " + edit_text).strip()
    else:
        if not prompt_id:
            await message.answer("Сессия недоступна. Начните заново.")
            await state.clear()
            return
        base_prompt = await db.get_prompt_text(int(prompt_id))
        prompt_filled = base_prompt + "\n\nПравки: " + edit_text

    # Берём последнее фото пользователя
    user_photo_id = data.get("user_photo_id")
    if not user_photo_id:
        await message.answer("Не найдено исходное фото. Начните заново.")
        await state.clear()
        return
    file = await message.bot.get_file(user_photo_id)
    f = await message.bot.download_file(file.file_path)
    user_image_bytes = f.read()

    # Ротация ключей для правок
    from bot.gemini import generate_image
    
    # Определяем, какую таблицу ключей использовать
    is_own_variant = (category == "own_variant")
    if is_own_variant:
        keys_with_ids = await db.list_own_variant_api_keys()
        tokens_order = [(kid, tok) for kid, tok, is_active in keys_with_ids if is_active]
    else:
        keys_with_ids = await db.list_api_keys()
        tokens_order = []
        for kid, tok, is_active, prio, du, tu, lr, ca, ua in keys_with_ids:
            if is_active:
                can_use, _ = await db.check_api_key_limits(kid)
                if can_use: tokens_order.append((kid, tok))

    if not tokens_order:
        await message.answer("Все API ключи исчерпали лимиты. Попробуйте позже.")
        return

    result_bytes = None
    for key_id, token in tokens_order:
        try:
            result_bytes = await generate_image(token, prompt_filled, user_image_bytes, None, key_id=key_id, db_instance=db)
            if result_bytes:
                if key_id and not is_own_variant:
                    await db.record_api_usage(key_id)
                break
    except Exception as e:
            logger.error(f"Error during edit with key {key_id}: {e}")
            continue

    if not result_bytes:
        await message.answer("Генерация не вернула изображение. Попробуйте позже.")
        return

    try:
        # Списываем 1 генерацию при успехе
        await db.increment_user_balance(message.from_user.id, -1)
        try:
            await db.add_transaction(message.from_user.id, -1, "spend", "edit_generation")
        except Exception:
            pass
        photo_file = BufferedInputFile(result_bytes, filename="result.png")
        # после правок оставляем только кнопку «Главное меню»
        lang = await db.get_user_language(message.from_user.id)
        await message.answer_document(document=photo_file, caption=get_string("gen_ready", lang), reply_markup=back_main_keyboard(lang))
    except Exception as e:
        lang = await db.get_user_language(message.from_user.id)
        await message.answer(get_string("gen_error", lang) + f": {e}")
    await state.clear()


@router.callback_query(F.data == "result_repeat")
async def on_result_repeat(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if not data:
        await _safe_answer(callback, get_string("session_not_found", lang), show_alert=True)
        return
    # Полностью сбрасываем сессию для новой генерации
    await state.clear()
    # Начинаем новую сессию с того же места
    category = data.get("category")
    if category:
        await state.update_data(category=category)
    await state.set_state(CreateForm.waiting_view)
    # Не удаляем предыдущее фото, отправляем новый запрос
    await callback.message.answer(get_string("repeat_photo_prompt", lang))
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("model_nav:"))
async def on_model_nav(callback: CallbackQuery, db: Database) -> None:
    try:
        _, category, cloth, index_str = callback.data.split(":", 3)
        index = int(index_str)
    except Exception:
        await _safe_answer(callback)
        return
    total = await db.count_models(category, cloth)
    if total <= 0:
        await _safe_answer(callback, "Модели не найдены", show_alert=True)
        return
    if index < 0:
        index = total - 1
    if index >= total:
        index = 0
    text = _model_header(index, total)
    model = await db.get_model_by_index(category, cloth, index)
    if model and model[3]:
        await _answer_model_photo(
            callback,
            model[3],
            text,
            model_select_keyboard(category, cloth, index, total),
        )
    else:
        await _replace_with_text(callback, text, reply_markup=model_select_keyboard(category, cloth, index, total))
    await _safe_answer(callback)


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
async def cmd_reset(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🔄 Состояние сброшено. Используйте /start для начала.")

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


