from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatAction
import asyncio
import logging
import json
import aiosqlite
import os

from bot.db import Database
from bot.strings import get_string
from bot.keyboards import (
    terms_keyboard, main_menu_keyboard, profile_keyboard, 
    settings_keyboard, language_keyboard, marketplace_menu_keyboard, plans_keyboard,
    history_pagination_keyboard, aspect_ratio_keyboard,
    form_generate_keyboard, subscription_check_keyboard,
    back_main_keyboard, create_product_keyboard_dynamic,
    model_select_keyboard_presets, pants_style_keyboard,
    sleeve_length_keyboard, garment_length_with_custom_keyboard,
    form_view_keyboard, pose_keyboard, angle_keyboard,
    confirm_generation_keyboard
)
from bot.config import load_settings
from bot.gemini import generate_image

logger = logging.getLogger(__name__)
router = Router()

class CreateForm(StatesGroup):
    waiting_photos = State()
    waiting_text = State()
    waiting_aspect = State()
    result_ready = State()

class PresetForm(StatesGroup):
    waiting_gender = State()
    waiting_model_pick = State()
    waiting_body_type = State()
    waiting_height = State()
    waiting_age = State()
    waiting_pants_style = State()
    waiting_sleeve_length = State()
    waiting_length = State()
    waiting_photo_type = State()
    waiting_pose = State()
    waiting_angle = State()
    waiting_season = State()
    waiting_holiday = State()
    waiting_info_load = State()
    waiting_info_lang = State()
    waiting_adv1 = State()
    waiting_adv2 = State()
    waiting_adv3 = State()
    waiting_extra_info = State()
    waiting_info_style = State()
    waiting_info_style_custom = State()
    waiting_font_type = State()
    waiting_font_type_custom = State()
    waiting_info_lang_custom = State()
    waiting_product_name = State()
    waiting_width = State()
    waiting_height = State()
    waiting_length = State()
    waiting_loc_group = State()
    waiting_location = State()
    waiting_loc_custom = State()
    waiting_holiday_custom = State()
    waiting_model_size = State()
    waiting_camera_dist = State()
    waiting_aspect = State()
    waiting_background_photo = State()
    waiting_product_photo = State()
    waiting_has_person = State()
    waiting_model_gender = State()
    result_ready = State()

# Глобальный счетчик активных генераций для rate limiting
active_generations = 0
active_generations_lock = asyncio.Lock()

async def check_user_subscription(user_id: int, bot: Bot, db: Database) -> bool:
    """Проверяет подписку на обязательный канал"""
    channel_id = await db.get_app_setting("channel_id")
    if not channel_id:
        # Если ID не задан в БД, используем актуальный ID канала
        channel_id = "-1003224356583"
    
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        # Если статус не 'left', значит пользователь в канале (member, administrator, creator)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Error checking subscription (channel_id={channel_id}): {e}")
        # Если ошибка "chat not found", значит ID неверный или бот не админ
        return False

@router.callback_query(F.data == "create_random")
async def on_create_random(callback: CallbackQuery, db: Database, state: FSMContext):
    from bot.keyboards import random_gender_keyboard
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_gender)
    await state.update_data(category="random")
    await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=random_gender_keyboard(lang))

@router.callback_query(F.data == "create_own")
async def on_create_own_model(callback: CallbackQuery, db: Database, state: FSMContext):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_background_photo)
    await state.update_data(category="own")
    await _replace_with_text(callback, get_string("upload_background", lang))

@router.callback_query(F.data == "create_own_variant")
async def on_create_own_bg(callback: CallbackQuery, db: Database, state: FSMContext):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_background_photo)
    await state.update_data(category="own_variant")
    await _replace_with_text(callback, get_string("upload_background", lang))

@router.callback_query(F.data.startswith("rand_gender:"), PresetForm.waiting_gender)
async def on_rand_gender(callback: CallbackQuery, state: FSMContext, db: Database):
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    
    if data.get("category") == "own":
        await state.set_state(PresetForm.waiting_height)
        await callback.message.edit_text(get_string("enter_height", lang))
    elif data.get("category") == "random":
        if gender in ["boy", "girl"]:
            await state.set_state(PresetForm.waiting_height)
            await callback.message.edit_text(get_string("enter_height_example", lang))
        else:
            await state.set_state(PresetForm.waiting_age)
            await callback.message.edit_text(get_string("enter_age_num", lang))
    elif data.get("category") == "infographic_clothing":
        await state.set_state(PresetForm.waiting_info_load)
        await callback.message.edit_text(get_string("select_info_load", lang))
    elif data.get("category") == "infographic_other":
        # Если это в конце флоу 'Прочее', идем к формату
        await state.set_state(PresetForm.waiting_aspect)
        from bot.keyboards import aspect_ratio_keyboard
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    else:
        # Для других категорий (female, male, child и т.д.) - опрос из прошлого запроса
        await state.set_state(PresetForm.waiting_age)
        await callback.message.edit_text(get_string("enter_age_num", lang))

@router.message(PresetForm.waiting_age)
async def on_preset_age(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(age=message.text)
    data = await state.get_data()
    cat = data.get("category")
    
    if cat == "random":
        await state.set_state(PresetForm.waiting_height)
        await message.answer(get_string("enter_height_example", lang))
    elif cat == "infographic_clothing":
        await state.set_state(PresetForm.waiting_pose)
        from bot.keyboards import pose_keyboard
        await message.answer(get_string("select_pose", lang), reply_markup=pose_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_model_size)
        from bot.keyboards import skip_step_keyboard
        await message.answer(get_string("enter_model_size", lang), reply_markup=skip_step_keyboard("size", lang))

@router.message(PresetForm.waiting_height)
async def on_preset_height(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(height=message.text)
    data = await state.get_data()
    cat = data.get("category")
    
    if cat == "random":
        await state.set_state(PresetForm.waiting_model_size)
        from bot.keyboards import skip_step_keyboard
        await message.answer(get_string("enter_model_size", lang), reply_markup=skip_step_keyboard("size", lang))
    elif cat == "infographic_clothing":
        await state.set_state(PresetForm.waiting_model_gender)
        from bot.keyboards import random_gender_keyboard
        await message.answer(get_string("select_model_gender", lang), reply_markup=random_gender_keyboard(lang))
    elif cat == "child" or data.get("gender") in ["boy", "girl"]:
        await state.set_state(PresetForm.waiting_pants_style)
        from bot.keyboards import pants_style_keyboard
        await message.answer(get_string("select_pants_style_btn", lang), reply_markup=pants_style_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_age)
        await message.answer(get_string("enter_age_num", lang))

@router.callback_query(F.data == "size:skip", PresetForm.waiting_model_size)
@router.message(PresetForm.waiting_model_size)
async def on_preset_size(event: Message | CallbackQuery, state: FSMContext, db: Database):
    val = None if isinstance(event, CallbackQuery) else event.text
    await state.update_data(model_size=val)
    msg = event.message if isinstance(event, CallbackQuery) else event
    uid = event.from_user.id
    lang = await db.get_user_language(uid)
    data = await state.get_data()
    cat = data.get("category")
    
    if cat == "random":
        await state.set_state(PresetForm.waiting_pose)
        from bot.keyboards import pose_keyboard
        await (event.message.edit_text if isinstance(event, CallbackQuery) else msg.answer)(
            get_string("select_pose", lang), reply_markup=pose_keyboard(lang))
    elif cat == "infographic_clothing":
        await state.set_state(PresetForm.waiting_height)
        await (event.message.edit_text if isinstance(event, CallbackQuery) else msg.answer)(
            get_string("enter_height_example", lang))
    else:
        await state.set_state(PresetForm.waiting_height)
        await (event.message.edit_text if isinstance(event, CallbackQuery) else msg.answer)(
            get_string("enter_height_example", lang))

@router.callback_query(F.data.startswith("pose:"), PresetForm.waiting_pose)
async def on_preset_pose(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(pose=callback.data.split(":")[1])
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_photo_type)
    from bot.keyboards import form_view_keyboard
    await _replace_with_text(callback, get_string("select_photo_type", lang), reply_markup=form_view_keyboard(lang))

@router.callback_query(F.data.startswith("form_view:"), PresetForm.waiting_photo_type)
async def on_preset_photo_type(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(photo_type=callback.data.split(":")[1])
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    cat = data.get("category")
    
    await state.set_state(PresetForm.waiting_camera_dist)
    from bot.keyboards import camera_distance_keyboard
    await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=camera_distance_keyboard(lang))

@router.callback_query(F.data.startswith("camera_dist:"), PresetForm.waiting_camera_dist)
async def on_preset_camera_dist(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(camera_dist=callback.data.split(":")[1])
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    cat = data.get("category")
    
    if cat == "random":
        await state.set_state(PresetForm.waiting_pants_style)
        from bot.keyboards import pants_style_keyboard
        await _replace_with_text(callback, get_string("select_pants_style_btn", lang), reply_markup=pants_style_keyboard(lang))
    elif cat == "infographic_clothing":
        await state.set_state(PresetForm.waiting_length)
        from bot.keyboards import garment_length_with_custom_keyboard
        await _replace_with_text(callback, get_string("garment_length_notice", lang), reply_markup=garment_length_with_custom_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_pose)
        from bot.keyboards import pose_keyboard
        await _replace_with_text(callback, get_string("select_pose", lang), reply_markup=pose_keyboard(lang))

@router.callback_query(F.data.startswith("pants_style:"), PresetForm.waiting_pants_style)
async def on_preset_pants_style(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(pants_style=None if val == "skip" else val)
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    cat = data.get("category")
    
    if cat == "random":
        await state.set_state(PresetForm.waiting_sleeve_length)
        from bot.keyboards import sleeve_length_keyboard
        await _replace_with_text(callback, get_string("select_sleeve_length_btn", lang), reply_markup=sleeve_length_keyboard(lang))
    elif cat == "infographic_clothing":
        await state.set_state(PresetForm.waiting_loc_group)
        from bot.keyboards import random_loc_group_keyboard
        await _replace_with_text(callback, get_string("select_loc_group", lang), reply_markup=random_loc_group_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_sleeve_length)
        from bot.keyboards import sleeve_length_keyboard
        await _replace_with_text(callback, get_string("select_sleeve_length_btn", lang), reply_markup=sleeve_length_keyboard(lang))

@router.callback_query(F.data.startswith("form_sleeve:"), PresetForm.waiting_sleeve_length)
async def on_preset_sleeve_length(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(sleeve_length=None if val == "skip" else val)
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    cat = data.get("category")
    
    if cat == "random":
        await state.set_state(PresetForm.waiting_length)
        from bot.keyboards import garment_length_with_custom_keyboard
        await _replace_with_text(callback, get_string("garment_length_notice", lang), reply_markup=garment_length_with_custom_keyboard(lang))
    elif cat == "infographic_clothing":
        await state.set_state(PresetForm.waiting_pants_style)
        from bot.keyboards import pants_style_keyboard
        await _replace_with_text(callback, get_string("select_pants_style_btn", lang), reply_markup=pants_style_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_length)
        from bot.keyboards import garment_length_with_custom_keyboard
        await _replace_with_text(callback, get_string("garment_length_notice", lang), reply_markup=garment_length_with_custom_keyboard(lang))

@router.callback_query(F.data.startswith("garment_len:"), PresetForm.waiting_length)
@router.callback_query(F.data == "garment_len:skip", PresetForm.waiting_length)
async def on_preset_length_btn(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(length=None if val == "skip" else val)
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    cat = data.get("category")
    
    if cat == "random":
        await state.set_state(PresetForm.waiting_aspect)
        from bot.keyboards import aspect_ratio_keyboard
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    elif cat == "infographic_clothing":
        await state.set_state(PresetForm.waiting_sleeve_length)
        from bot.keyboards import sleeve_length_keyboard
        await _replace_with_text(callback, get_string("select_sleeve_length_btn", lang), reply_markup=sleeve_length_keyboard(lang))
    elif cat == "own":
        await state.set_state(PresetForm.waiting_aspect)
        from bot.keyboards import aspect_ratio_keyboard
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_photo_type)
        from bot.keyboards import form_view_keyboard
        await _replace_with_text(callback, get_string("select_photo_type", lang), reply_markup=form_view_keyboard(lang))

@router.message(PresetForm.waiting_background_photo, F.photo)
async def on_own_bg_photo(message: Message, state: FSMContext, db: Database):
    await state.update_data(background_photo=message.photo[-1].file_id)
    await state.set_state(PresetForm.waiting_product_photo)
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(get_string("upload_product", lang))

@router.message(PresetForm.waiting_product_photo, F.photo)
async def on_own_product_photo(message: Message, state: FSMContext, db: Database):
    await state.update_data(product_photo=message.photo[-1].file_id)
    data = await state.get_data()
    lang = await db.get_user_language(message.from_user.id)
    if data.get("category") == "own_variant":
        # Сценарий 'Свой вариант ФОНА'
        await state.set_state(PresetForm.waiting_photo_type)
        from bot.keyboards import form_view_keyboard
        await message.answer(get_string("select_view", lang), reply_markup=form_view_keyboard(lang))
    elif data.get("category") == "own":
        # Сценарий 'Свой вариант МОДЕЛИ' - оставляем только длину и рукав
        await state.set_state(PresetForm.waiting_sleeve_length)
        from bot.keyboards import sleeve_length_keyboard
        await message.answer(get_string("select_sleeve_length_btn", lang), reply_markup=sleeve_length_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_height)
        await message.answer(get_string("enter_height", lang))

@router.callback_query(F.data == "form_len:skip", PresetForm.waiting_model_size)
async def on_rand_size_skip(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(model_size=None)
    await state.set_state(PresetForm.waiting_height)
    lang = await db.get_user_language(callback.from_user.id)
    await callback.message.edit_text(get_string("enter_height", lang))

@router.message(PresetForm.waiting_height, F.state == PresetForm.waiting_height)
async def on_rand_height(message: Message, state: FSMContext, db: Database):
    await state.update_data(height=message.text)
    await state.set_state(PresetForm.waiting_age)
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(get_string("enter_age", lang))

@router.message(PresetForm.waiting_age, F.state == PresetForm.waiting_age)
async def on_rand_age(message: Message, state: FSMContext, db: Database):
    await state.update_data(age=message.text)
    await state.set_state(PresetForm.waiting_pants_style)
    from bot.keyboards import pants_style_keyboard
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(get_string("select_pants_style", lang), reply_markup=pants_style_keyboard(lang))

@router.callback_query(F.data.startswith("pants_style:"), PresetForm.waiting_pants_style)
async def on_rand_pants_style(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(pants_style=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_sleeve_length)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import sleeve_length_keyboard
    await _replace_with_text(callback, get_string("select_sleeve_length", lang), reply_markup=sleeve_length_keyboard(lang))

@router.callback_query(F.data.startswith("form_sleeve:"), PresetForm.waiting_sleeve_length)
async def on_rand_sleeve(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(sleeve_length=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_length)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import garment_length_with_custom_keyboard
    await _replace_with_text(callback, get_string("select_garment_length", lang), reply_markup=garment_length_with_custom_keyboard(lang))

@router.callback_query(F.data.startswith("garment_len:"), PresetForm.waiting_length)
async def on_rand_length_btn(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(length=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_photo_type)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import form_view_keyboard
    await _replace_with_text(callback, get_string("select_view", lang), reply_markup=form_view_keyboard(lang))

@router.callback_query(F.data.startswith("form_view:"), PresetForm.waiting_photo_type)
async def on_rand_view(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(photo_type=callback.data.split(":")[1])
    await state.set_state(PresetForm.waiting_camera_dist)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import camera_distance_keyboard
    await _replace_with_text(callback, get_string("select_camera_dist", lang), reply_markup=camera_distance_keyboard(lang))

# Добавляем обработку остальных шагов аналогично пресетам, но с новыми клавиатурами
@router.callback_query(F.data.startswith("camera_dist:"), PresetForm.waiting_camera_dist)
async def on_rand_camera_dist(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(camera_dist=callback.data.split(":")[1])
    await state.set_state(PresetForm.waiting_aspect)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import aspect_ratio_keyboard
    await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data.startswith("form_aspect:"), PresetForm.waiting_aspect)
async def on_rand_aspect(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(aspect=callback.data.split(":")[1])
    await state.set_state(PresetForm.result_ready)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import confirm_generation_keyboard
    await _replace_with_text(callback, get_string("create_photo", lang) + "?", reply_markup=confirm_generation_keyboard(lang))

@router.callback_query(F.data == "create_cat:infographic_clothing")
async def on_create_infographic_clothing(callback: CallbackQuery, db: Database, state: FSMContext):
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(category="infographic_clothing")
    await state.set_state(PresetForm.waiting_gender)
    from bot.keyboards import infographic_gender_keyboard
    await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang))

@router.callback_query(F.data == "create_cat:infographic_other")
async def on_create_infographic_other(callback: CallbackQuery, db: Database, state: FSMContext):
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(category="infographic_other")
    await state.set_state(PresetForm.waiting_product_name)
    await _replace_with_text(callback, get_string("enter_product_name", lang))

@router.message(PresetForm.waiting_info_load)
async def on_info_load_numeric(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(info_load=message.text)
    data = await state.get_data()
    
    if data.get("category") == "infographic_clothing":
        await state.set_state(PresetForm.waiting_info_lang)
        from bot.keyboards import info_lang_keyboard
        await message.answer(get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
    else:
        # Для infographic_other
        await state.set_state(PresetForm.waiting_has_person)
        from bot.keyboards import yes_no_keyboard
        await message.answer(get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))

@router.callback_query(F.data.startswith("info_lang:"), PresetForm.waiting_info_lang)
async def on_info_lang_ext(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if val == "custom":
        await state.set_state(PresetForm.waiting_info_lang_custom)
        await callback.message.edit_text(get_string("enter_custom_lang", lang))
    else:
        await state.update_data(info_lang=val)
        await state.set_state(PresetForm.waiting_product_name)
        await _replace_with_text(callback, get_string("enter_product_name", lang))

@router.message(PresetForm.waiting_info_lang_custom)
async def on_info_lang_custom(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(info_lang=message.text)
    await state.set_state(PresetForm.waiting_product_name)
    await message.answer(get_string("enter_product_name", lang))

@router.message(PresetForm.waiting_product_name)
async def on_product_name(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(product_name=message.text[:75])
    data = await state.get_data()
    
    if data.get("category") == "infographic_clothing":
        await state.set_state(PresetForm.waiting_adv1)
        from bot.keyboards import skip_step_keyboard
        await message.answer(get_string("enter_adv1_skip", lang), reply_markup=skip_step_keyboard("adv1", lang))
    else:
        # Для infographic_other
        await state.set_state(PresetForm.waiting_angle)
        from bot.keyboards import angle_keyboard
        await message.answer(get_string("select_camera_dist", lang), reply_markup=angle_keyboard(lang))

@router.callback_query(F.data.startswith("angle:"), PresetForm.waiting_angle)
async def on_preset_angle(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(angle=val)
    await state.set_state(PresetForm.waiting_width)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import skip_step_keyboard
    await _replace_with_text(callback, get_string("enter_width", lang), reply_markup=skip_step_keyboard("width", lang))

@router.callback_query(F.data == "width:skip", PresetForm.waiting_width)
@router.message(PresetForm.waiting_width)
async def on_width_input(event: Message | CallbackQuery, state: FSMContext, db: Database):
    if isinstance(event, CallbackQuery):
        await state.update_data(width=None)
        msg = event.message
        uid = event.from_user.id
    else:
        await state.update_data(width=event.text)
        msg = event
        uid = event.from_user.id
    
    lang = await db.get_user_language(uid)
    await state.set_state(PresetForm.waiting_height)
    from bot.keyboards import skip_step_keyboard
    if isinstance(event, CallbackQuery):
        await _replace_with_text(event, get_string("enter_height_dim", lang), reply_markup=skip_step_keyboard("height", lang))
    else:
        await msg.answer(get_string("enter_height_dim", lang), reply_markup=skip_step_keyboard("height", lang))

@router.callback_query(F.data == "height:skip", PresetForm.waiting_height)
@router.message(PresetForm.waiting_height)
async def on_height_input(event: Message | CallbackQuery, state: FSMContext, db: Database):
    if isinstance(event, CallbackQuery):
        await state.update_data(height=None)
        msg = event.message
        uid = event.from_user.id
    else:
        await state.update_data(height=event.text)
        msg = event
        uid = event.from_user.id
    
    lang = await db.get_user_language(uid)
    await state.set_state(PresetForm.waiting_length)
    from bot.keyboards import skip_step_keyboard
    if isinstance(event, CallbackQuery):
        await _replace_with_text(event, get_string("enter_length_dim", lang), reply_markup=skip_step_keyboard("length", lang))
    else:
        await msg.answer(get_string("enter_length_dim", lang), reply_markup=skip_step_keyboard("length", lang))

@router.callback_query(F.data == "length:skip", PresetForm.waiting_length)
@router.message(PresetForm.waiting_length)
async def on_length_input(event: Message | CallbackQuery, state: FSMContext, db: Database):
    if isinstance(event, CallbackQuery):
        await state.update_data(length=None)
        msg = event.message
        uid = event.from_user.id
    else:
        await state.update_data(length=event.text)
        msg = event
        uid = event.from_user.id
    
    lang = await db.get_user_language(uid)
    await state.set_state(PresetForm.waiting_season)
    from bot.keyboards import random_season_keyboard
    if isinstance(event, CallbackQuery):
        await _replace_with_text(event, get_string("select_season", lang), reply_markup=random_season_keyboard(lang))
    else:
        await msg.answer(get_string("select_season", lang), reply_markup=random_season_keyboard(lang))

@router.callback_query(F.data.startswith("rand_season:"), PresetForm.waiting_season)
async def on_season_input(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(season=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_info_style)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import infographic_style_keyboard
    await _replace_with_text(callback, get_string("select_info_style_other", lang), reply_markup=infographic_style_keyboard(lang))

@router.callback_query(F.data.startswith("info_style:"), PresetForm.waiting_info_style)
async def on_style_input(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if val == "custom":
        await state.set_state(PresetForm.waiting_info_style_custom)
        await callback.message.edit_text(get_string("enter_custom_style", lang))
    else:
        await state.update_data(info_style=None if val == "skip" else val)
        await state.set_state(PresetForm.waiting_info_load)
        from bot.keyboards import info_load_keyboard
        await _replace_with_text(callback, get_string("select_info_load", lang), reply_markup=info_load_keyboard(lang))

@router.message(PresetForm.waiting_info_style_custom)
async def on_style_custom_input(message: Message, state: FSMContext, db: Database):
    await state.update_data(info_style=message.text[:20])
    await state.set_state(PresetForm.waiting_info_load)
    lang = await db.get_user_language(message.from_user.id)
    from bot.keyboards import info_load_keyboard
    await message.answer(get_string("select_info_load", lang), reply_markup=info_load_keyboard(lang))

@router.callback_query(F.data.startswith("info_load:"), PresetForm.waiting_info_load)
async def on_load_input(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(info_load=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_has_person)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import yes_no_keyboard
    await _replace_with_text(callback, get_string("has_person_ask", lang), reply_markup=yes_no_keyboard(lang))

@router.callback_query(F.data.startswith("yes_no:"), PresetForm.waiting_has_person)
async def on_has_person_input(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(has_person=val)
    lang = await db.get_user_language(callback.from_user.id)
    if val == "yes":
        await state.set_state(PresetForm.waiting_gender)
        from bot.keyboards import infographic_gender_keyboard
        await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang))
    else:
        await state.update_data(gender=None)
        await state.set_state(PresetForm.waiting_aspect)
        from bot.keyboards import aspect_ratio_keyboard
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data.startswith("rand_locgroup:"), PresetForm.waiting_loc_group)
async def on_loc_group_input(callback: CallbackQuery, state: FSMContext, db: Database):
    group = callback.data.split(":")[1]
    await state.update_data(loc_group=group)
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_location)
    await _replace_with_text(callback, get_string("enter_loc_style", lang)) # Спрашиваем стиль локации

@router.message(PresetForm.waiting_location)
async def on_loc_style_input(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(location=message.text[:120])
    data = await state.get_data()
    
    if data.get("loc_group") == "outdoor":
        await state.set_state(PresetForm.waiting_season)
        from bot.keyboards import random_season_keyboard
        await message.answer(get_string("select_season", lang), reply_markup=random_season_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_holiday)
        from bot.keyboards import random_holiday_keyboard
        await message.answer(get_string("select_holiday", lang), reply_markup=random_holiday_keyboard(lang))

@router.callback_query(F.data.startswith("rand_season:"), PresetForm.waiting_season)
async def on_season_input(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(season=None if val == "skip" else val)
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_holiday)
    from bot.keyboards import random_holiday_keyboard
    await _replace_with_text(callback, get_string("select_holiday", lang), reply_markup=random_holiday_keyboard(lang))

@router.callback_query(F.data.startswith("rand_holiday:"), PresetForm.waiting_holiday)
async def on_holiday_input(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if val == "custom":
        await state.set_state(PresetForm.waiting_holiday_custom)
        await callback.message.edit_text(get_string("enter_custom_holiday", lang))
    else:
        await state.update_data(holiday=None if val == "skip" else val)
        await state.set_state(PresetForm.waiting_aspect)
        from bot.keyboards import aspect_ratio_keyboard
        await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.message(PresetForm.waiting_holiday_custom)
async def on_holiday_custom_input(message: Message, state: FSMContext, db: Database):
    await state.update_data(holiday=message.text[:30])
    lang = await db.get_user_language(message.from_user.id)
    await state.set_state(PresetForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.message(PresetForm.waiting_adv1)
async def on_adv1_text(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(adv1=message.text[:180])
    await state.set_state(PresetForm.waiting_adv2)
    await message.answer(get_string("enter_adv2", lang))

@router.message(PresetForm.waiting_adv2)
async def on_adv2_text(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(adv2=message.text[:180])
    await state.set_state(PresetForm.waiting_adv3)
    await message.answer(get_string("enter_adv3", lang))

@router.message(PresetForm.waiting_adv3)
async def on_adv3_text(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(adv3=message.text[:180])
    await state.set_state(PresetForm.waiting_extra_info)
    from bot.keyboards import skip_step_keyboard
    await message.answer(get_string("enter_additional", lang), reply_markup=skip_step_keyboard("extra", lang))

@router.callback_query(F.data == "extra:skip", PresetForm.waiting_extra_info)
async def on_extra_skip_info_other(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(extra_info=None)
    data = await state.get_data()
    
    if data.get("category") == "infographic_clothing":
        await state.set_state(PresetForm.waiting_model_size)
        from bot.keyboards import skip_step_keyboard
        await _replace_with_text(callback, get_string("enter_model_size", lang), reply_markup=skip_step_keyboard("size", lang))
    else:
        await state.set_state(PresetForm.waiting_gender)
        from bot.keyboards import infographic_gender_keyboard
        await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang))

@router.message(PresetForm.waiting_extra_info)
async def on_extra_text_info_other(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(extra_info=message.text[:100])
    data = await state.get_data()
    
    if data.get("category") == "infographic_clothing":
        await state.set_state(PresetForm.waiting_model_size)
        from bot.keyboards import skip_step_keyboard
        await message.answer(get_string("enter_model_size", lang), reply_markup=skip_step_keyboard("size", lang))
    else:
        await state.set_state(PresetForm.waiting_gender)
        from bot.keyboards import infographic_gender_keyboard
        await message.answer(get_string("select_gender", lang), reply_markup=infographic_gender_keyboard(lang))

@router.callback_query(F.data.startswith("rand_gender:"), PresetForm.waiting_model_gender)
async def on_model_gender_input(callback: CallbackQuery, state: FSMContext, db: Database):
    gender = callback.data.split(":")[1]
    await state.update_data(model_gender=gender)
    lang = await db.get_user_language(callback.from_user.id)
    
    if gender in ["boy", "girl"]:
        await state.set_state(PresetForm.waiting_pose)
        from bot.keyboards import pose_keyboard
        await _replace_with_text(callback, get_string("select_pose", lang), reply_markup=pose_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_age)
        await _replace_with_text(callback, get_string("enter_age_num", lang))

@router.callback_query(F.data.startswith("info_style:"), PresetForm.waiting_info_style)
async def on_info_style(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if val == "skip":
        await state.update_data(info_style=None)
        await state.set_state(PresetForm.waiting_font_type)
        from bot.keyboards import font_type_keyboard
        await _replace_with_text(callback, get_string("select_font_type", lang), reply_markup=font_type_keyboard(lang))
    elif val == "custom":
        await state.set_state(PresetForm.waiting_info_style_custom)
        await callback.message.edit_text(get_string("enter_custom_style", lang))
    else:
        await state.update_data(info_style=val)
        await state.set_state(PresetForm.waiting_font_type)
        from bot.keyboards import font_type_keyboard
        await _replace_with_text(callback, get_string("select_font_type", lang), reply_markup=font_type_keyboard(lang))

@router.message(PresetForm.waiting_info_style_custom)
async def on_info_style_custom(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(info_style=message.text[:20])
    await state.set_state(PresetForm.waiting_font_type)
    from bot.keyboards import font_type_keyboard
    await message.answer(get_string("select_font_type", lang), reply_markup=font_type_keyboard(lang))

@router.callback_query(F.data.startswith("font_type:"), PresetForm.waiting_font_type)
async def on_font_type(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if val == "skip":
        await state.update_data(font_type=None)
        await state.set_state(PresetForm.waiting_info_lang)
        from bot.keyboards import info_lang_keyboard
        await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))
    elif val == "custom":
        await state.set_state(PresetForm.waiting_font_type_custom)
        await callback.message.edit_text(get_string("enter_custom_font", lang))
    else:
        await state.update_data(font_type=val)
        await state.set_state(PresetForm.waiting_info_lang)
        from bot.keyboards import info_lang_keyboard
        await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))

@router.message(PresetForm.waiting_font_type_custom)
async def on_font_type_custom(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(font_type=message.text[:20])
    await state.set_state(PresetForm.waiting_info_lang)
    from bot.keyboards import info_lang_keyboard
    await message.answer(get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))

@router.callback_query(F.data.startswith("info_lang:"), PresetForm.waiting_info_lang)
async def on_info_lang_ext(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if val == "custom":
        await state.set_state(PresetForm.waiting_info_lang_custom)
        await callback.message.edit_text(get_string("enter_custom_lang", lang))
    else:
        await state.update_data(info_lang=val)
        await state.set_state(PresetForm.waiting_aspect)
        from bot.keyboards import aspect_ratio_keyboard
        await _replace_with_text(callback, get_string("select_photo_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.message(PresetForm.waiting_info_lang_custom)
async def on_info_lang_custom(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(info_lang=message.text)
    await state.set_state(PresetForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await message.answer(get_string("select_photo_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data == "create_normal_gen")
async def on_create_normal_gen(callback: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(CreateForm.waiting_photos)
    await state.update_data(photos=[])
    await _replace_with_text(callback, get_string("normal_gen_prompt", lang), 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text=get_string("done_to_text", lang), callback_data="photos_done")],
                                 [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_main")]
                             ]))

@router.message(CreateForm.waiting_photos, F.photo)
async def on_normal_photos(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= 4:
        await message.answer(get_string("max_photos_alert", lang))
        return
    
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    
    if len(photos) < 4:
        await message.answer(get_string("photo_received_count", lang, count=len(photos)), 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text=get_string("done_to_text", lang), callback_data="photos_done")]
                             ]))
    else:
        await message.answer(get_string("photos_received_four", lang))
        await state.set_state(CreateForm.waiting_text)

@router.callback_query(F.data == "photos_done", CreateForm.waiting_photos)
async def on_photos_done(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    if not data.get("photos"):
        await callback.answer(get_string("at_least_one_photo", lang), show_alert=True)
        return
    
    await state.set_state(CreateForm.waiting_text)
    await _replace_with_text(callback, get_string("enter_normal_text", lang))

@router.message(CreateForm.waiting_text)
async def on_normal_text(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(market_prompt=message.text[:1000]) # Используем market_prompt для совместимости с on_form_generate
    await state.set_state(CreateForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await message.answer(get_string("select_photo_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data.startswith("form_aspect:"), CreateForm.waiting_aspect)
async def on_normal_aspect(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(form_aspect=callback.data.split(":")[1])
    await state.set_state(CreateForm.result_ready)
    from bot.keyboards import confirm_generation_keyboard
    await _replace_with_text(callback, get_string("generation_confirm", lang), reply_markup=confirm_generation_keyboard(lang))

@router.callback_query(F.data == "back_step", CreateForm.waiting_aspect)
async def on_back_from_create_aspect(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(CreateForm.waiting_text)
    await _replace_with_text(callback, get_string("enter_normal_text", lang))

@router.callback_query(F.data == "back_step", CreateForm.result_ready)
async def on_back_from_create_ready(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(CreateForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data.startswith("info_gender:"), PresetForm.waiting_gender)
async def on_info_gender(callback: CallbackQuery, state: FSMContext, db: Database):
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    await state.set_state(PresetForm.waiting_model_pick)
    
    data = await state.get_data()
    category = data.get("category")
    lang = await db.get_user_language(callback.from_user.id)
    
    total = await db.count_models(category, gender)
    if total == 0:
        await callback.answer(get_string("no_gender_models_alert", lang, gender=gender), show_alert=True)
        return
        
    model = await db.get_model_by_index(category, gender, 0)
    from bot.keyboards import model_select_keyboard_presets
    kb = model_select_keyboard_presets(category, gender, 0, total, lang)
    
    await callback.message.delete()
    await _send_model_photo(callback, model[3], get_string("gender_presets_title", lang, gender=gender, name=model[1], index=1, total=total), kb)

async def _safe_answer(callback: CallbackQuery, text: str | None = None, show_alert: bool = False) -> None:
    try:
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
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    await state.clear()
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)

    # Проверка техработ
    maint = await db.get_app_setting("maintenance")
    if maint == "1":
        await message.answer(get_string("maintenance", lang))
        return
    
    # Регистрация пользователя
    await db.upsert_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    
    # 1. Обязательная подписка
    if not await check_user_subscription(user_id, bot, db):
        channel_id = await db.get_app_setting("channel_id") or "-1003224356583"
        channel_url = f"https://t.me/c/{channel_id[4:]}" if channel_id.startswith("-100") else f"https://t.me/{channel_id}"
        # Пользователь предоставил ссылку: https://t.me/+fOA5fiDstVdlMzIy
        channel_url = "https://t.me/+fOA5fiDstVdlMzIy"
        await message.answer(get_string("subscribe_channel", lang), reply_markup=subscription_check_keyboard(channel_url, lang))
        return

    # 11. Бесплатный триал (1 день, 5 генераций)
    if not await db.get_user_trial_status(user_id):
        await db.grant_subscription(user_id, None, "trial", 1, 5)
        await message.answer(get_string("trial_info", lang))

    # Условия соглашения
    async with aiosqlite.connect(db._db_path) as conn:
        async with conn.execute("SELECT accepted_terms FROM users WHERE id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row and not row[0]:
                agreement_text = await db.get_agreement_text()
                await message.answer(f"<b>{get_string('agreement', lang)}</b>\n\n{agreement_text}", reply_markup=terms_keyboard(lang))
                return

    await message.answer(get_string("start_welcome", lang), reply_markup=main_menu_keyboard(lang))

@router.message(Command("profile"))
async def cmd_profile(message: Message, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    user_id = message.from_user.id
    sub = await db.get_user_subscription(user_id)
    
    if sub:
        plan, expires, limit, usage, api_key = sub
        rem = max(0, limit - usage)
        # Форматируем дату (убираем T и миллисекунды)
        formatted_date = expires.replace("T", " ")[:16]
        sub_text = get_string("sub_active", lang, plan=plan.upper(), date=formatted_date)
    else:
        sub_text = get_string("sub_none", lang)
        rem = 0
    
    text = get_string("profile_info", lang, id=user_id, sub=sub_text, daily_rem=rem)
    await message.answer(text, reply_markup=profile_keyboard(lang))

@router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    from bot.keyboards import settings_keyboard
    await message.answer(get_string("menu_settings", lang), reply_markup=settings_keyboard(lang))

@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext, db: Database, bot: Bot):
    await state.clear()
    await cmd_start(message, state, db, bot)

@router.message(Command("help"))
async def cmd_help(message: Message, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    text = await db.get_app_setting("howto") or get_string("how_to", lang)
    from bot.keyboards import back_main_keyboard
    await message.answer(text, reply_markup=back_main_keyboard(lang))

@router.callback_query(F.data == "accept_terms")
async def on_accept_terms(callback: CallbackQuery, db: Database):
    await db.set_terms_acceptance(callback.from_user.id, True)
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("start_welcome", lang), reply_markup=main_menu_keyboard(lang))

@router.callback_query(F.data == "check_subscription")
async def on_check_sub(callback: CallbackQuery, bot: Bot, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    if await check_user_subscription(callback.from_user.id, bot, db):
        await _replace_with_text(callback, get_string("start_welcome", lang), reply_markup=main_menu_keyboard(lang))
    else:
        await callback.answer(get_string("subscribe_channel", lang), show_alert=True)

@router.callback_query(F.data == "menu_profile")
async def on_menu_profile(callback: CallbackQuery, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    user_id = callback.from_user.id
    sub = await db.get_user_subscription(user_id)
    
    if sub:
        plan, expires, limit, usage, api_key = sub
        rem = max(0, limit - usage)
        # Форматируем дату (убираем T и миллисекунды)
        formatted_date = expires.replace("T", " ")[:16]
        sub_text = get_string("sub_active", lang, plan=plan.upper(), date=formatted_date)
    else:
        sub_text = get_string("sub_none", lang)
        rem = 0
    
    text = get_string("profile_info", lang, id=user_id, sub=sub_text, daily_rem=rem)
    await _replace_with_text(callback, text, reply_markup=profile_keyboard(lang))

@router.callback_query(F.data == "menu_settings")
async def on_menu_settings(callback: CallbackQuery, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("menu_settings", lang), reply_markup=settings_keyboard(lang))

@router.callback_query(F.data == "settings_lang")
async def on_settings_lang(callback: CallbackQuery, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_lang", lang), reply_markup=language_keyboard(lang))

@router.callback_query(F.data.startswith("lang:"))
async def on_set_lang(callback: CallbackQuery, db: Database):
    new_lang = callback.data.split(":")[1]
    await db.set_user_language(callback.from_user.id, new_lang)
    await on_menu_settings(callback, db)

async def _send_model_photo(callback: CallbackQuery, photo_id: str, caption: str, reply_markup: InlineKeyboardMarkup):
    """Универсальная функция для отправки фото модели (file_id или локальный путь)"""
    try:
        if photo_id and (photo_id.startswith('data/uploads') or photo_id.startswith('C:')):
            if os.path.exists(photo_id):
                from aiogram.types import FSInputFile
                photo = FSInputFile(photo_id)
                await callback.message.answer_photo(photo, caption=caption, reply_markup=reply_markup)
            else:
                await callback.message.answer(caption, reply_markup=reply_markup)
        elif photo_id:
            await callback.message.answer_photo(photo_id, caption=caption, reply_markup=reply_markup)
        else:
            await callback.message.answer(caption, reply_markup=reply_markup)
    except Exception as e:
        await callback.message.answer(f"{caption}\n\n({get_string('error_api', lang)}: {e})", reply_markup=reply_markup)

@router.callback_query(F.data == "menu_market")
async def on_menu_market(callback: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    lang = await db.get_user_language(callback.from_user.id)

    # Проверка техработ
    maint = await db.get_app_setting("maintenance")
    if maint == "1":
        await callback.answer(get_string("maintenance_alert", lang), show_alert=True)
        return

    enabled = await db.get_all_app_settings()
    cats = ["female", "male", "child", "storefront", "whitebg", "random", "own", "own_variant", "infographic_clothing", "infographic_other"]
    # По умолчанию категории включены ("1"), если статус не задан
    cat_status = {k: (enabled.get(k, "1") == "1") for k in cats}
    
    # Получаем цены из настроек
    prices = {}
    for cat in cats:
        prices[cat] = int(enabled.get(f"category_price_{cat}", "10"))

    # Текст с картинки 2: Обратите внимание...
    disclaimer = get_string("disclaimer_text", lang)
    from bot.keyboards import create_product_keyboard_dynamic
    await _replace_with_text(callback, disclaimer, reply_markup=create_product_keyboard_dynamic(cat_status, lang))

@router.callback_query(F.data.startswith("create_cat:"))
async def on_create_cat(callback: CallbackQuery, db: Database, state: FSMContext):
    category = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    
    # Начинаем флоу пресетов
    await state.set_state(PresetForm.waiting_model_pick)
    await state.update_data(category=category, subcategory="default")
    
    # Показываем выбор модели (пресета)
    total = await db.count_models(category, "default")
    if total == 0:
        await callback.answer(get_string("no_models_in_category_alert", lang), show_alert=True)
        return
        
    model = await db.get_model_by_index(category, "default", 0)
    from bot.keyboards import model_select_keyboard_presets
    kb = model_select_keyboard_presets(category, "default", 0, total, lang)
    
    await callback.message.delete()
    await _send_model_photo(callback, model[3], get_string("model_presets_title", lang, name=model[1], index=1, total=total), kb)

@router.callback_query(F.data.startswith("preset_nav:"))
async def on_preset_nav(callback: CallbackQuery, db: Database, state: FSMContext):
    _, category, cloth, index = callback.data.split(":")
    index = int(index)
    total = await db.count_models(category, cloth)
    
    if index < 0: index = total - 1
    if index >= total: index = 0
    
    model = await db.get_model_by_index(category, cloth, index)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import model_select_keyboard_presets
    kb = model_select_keyboard_presets(category, cloth, index, total, lang)
    
    await callback.message.delete()
    await _send_model_photo(callback, model[3], get_string("model_presets_title", lang, name=model[1], index=index+1, total=total), kb)

@router.callback_query(F.data.startswith("preset_pick:"), PresetForm.waiting_model_pick)
async def on_preset_pick(callback: CallbackQuery, db: Database, state: FSMContext):
    _, category, cloth, index = callback.data.split(":")
    model = await db.get_model_by_index(category, cloth, int(index))
    lang = await db.get_user_language(callback.from_user.id)
    
    await state.update_data(model_id=model[0], prompt_id=model[2], category=category, cloth=cloth)
    
    if category == "infographic_other":
        await state.set_state(PresetForm.waiting_product_name)
        await callback.message.answer(get_string("enter_product_name", lang))
    elif category == "child":
        await state.set_state(PresetForm.waiting_height)
        await callback.message.answer(get_string("enter_height_example", lang))
    else:
        await state.set_state(PresetForm.waiting_body_type)
        await callback.message.answer(get_string("enter_body_type", lang))

@router.message(PresetForm.waiting_body_type)
async def on_preset_body_type(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(body_type=message.text)
    await state.set_state(PresetForm.waiting_height)
    await message.answer(get_string("enter_height_example", lang))

@router.message(PresetForm.waiting_height)
async def on_preset_height(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    if not message.text.isdigit():
        await message.answer(get_string("enter_height_example", lang)) # Use same string for re-asking
        return
    await state.update_data(height=message.text)
    await state.set_state(PresetForm.waiting_age)
    await message.answer(get_string("enter_age_num", lang))

@router.message(PresetForm.waiting_age)
async def on_preset_age(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    if not message.text.isdigit():
        await message.answer(get_string("enter_age_num", lang))
        return
    await state.update_data(age=message.text)
    await state.set_state(PresetForm.waiting_pants_style)
    from bot.keyboards import pants_style_keyboard
    await message.answer(get_string("select_pants_style_btn", lang), reply_markup=pants_style_keyboard(lang))

@router.callback_query(F.data.startswith("pants_style:"), PresetForm.waiting_pants_style)
async def on_preset_pants_style(callback: CallbackQuery, state: FSMContext, db: Database):
    style = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if style == "skip":
        await state.update_data(pants_style=None)
    else:
        await state.update_data(pants_style=style)
    await state.set_state(PresetForm.waiting_sleeve_length)
    from bot.keyboards import sleeve_length_keyboard
    await callback.message.edit_text(get_string("select_sleeve_length_btn", lang), reply_markup=sleeve_length_keyboard(lang))

@router.callback_query(F.data.startswith("form_sleeve:"), PresetForm.waiting_sleeve_length)
async def on_preset_sleeve_length(callback: CallbackQuery, state: FSMContext, db: Database):
    length = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if length == "skip":
        await state.update_data(sleeve_length=None)
    else:
        await state.update_data(sleeve_length=length)
    await state.set_state(PresetForm.waiting_length)
    text = get_string("garment_length_notice", lang)
    from bot.keyboards import garment_length_with_custom_keyboard
    await callback.message.edit_text(text, reply_markup=garment_length_with_custom_keyboard(lang))

@router.callback_query(F.data == "garment_len:skip", PresetForm.waiting_length)
async def on_preset_length_skip(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(length=None)
    await preset_ask_photo_type(callback.message, state, db)

@router.callback_query(F.data.startswith("garment_len:"), PresetForm.waiting_length)
async def on_preset_length_btn(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(length=val)
    await preset_ask_photo_type(callback.message, state, db)

@router.callback_query(F.data == "garment_len_custom", PresetForm.waiting_length)
async def on_preset_length_custom(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await callback.message.answer(get_string("enter_length_custom", lang))

@router.message(PresetForm.waiting_length)
async def on_preset_length_text(message: Message, state: FSMContext, db: Database):
    await state.update_data(length=message.text)
    await preset_ask_photo_type(message, state, db)

async def preset_ask_photo_type(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.set_state(PresetForm.waiting_photo_type)
    from bot.keyboards import form_view_keyboard
    await message.answer(get_string("select_photo_type", lang), reply_markup=form_view_keyboard(lang))

@router.callback_query(F.data.startswith("form_view:"), PresetForm.waiting_photo_type)
async def on_preset_photo_type(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(photo_type=val)
    lang = await db.get_user_language(callback.from_user.id)
    
    data = await state.get_data()
    category = data.get("category")
    
    if category == "own_variant":
        # Сценарий 'Свой вариант ФОНА' - после ракурса выбор формата
        await state.set_state(PresetForm.waiting_aspect)
        from bot.keyboards import aspect_ratio_keyboard
        await callback.message.edit_text(get_string("select_photo_format", lang), reply_markup=aspect_ratio_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_pose)
        from bot.keyboards import pose_keyboard
        await callback.message.edit_text(get_string("select_pose", lang), reply_markup=pose_keyboard(lang))

@router.callback_query(F.data.startswith("pose:"), PresetForm.waiting_pose)
async def on_preset_pose(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(pose=val)
    await state.set_state(PresetForm.waiting_angle)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import angle_keyboard
    await callback.message.edit_text(get_string("select_view", lang), reply_markup=angle_keyboard(lang))

@router.callback_query(F.data.startswith("angle:"), PresetForm.waiting_angle)
async def on_preset_angle(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(angle=val)
    await state.set_state(PresetForm.waiting_season)
    lang = await db.get_user_language(callback.from_user.id)
    from bot.keyboards import random_season_keyboard
    await callback.message.edit_text(get_string("select_season", lang), reply_markup=random_season_keyboard(lang))

@router.callback_query(F.data.startswith("rand_season:"), PresetForm.waiting_season)
async def on_preset_season(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    if val == "skip":
        await state.update_data(season=None)
    else:
        await state.update_data(season=val)
    
    data = await state.get_data()
    category = data.get("category")
    
    if category and category.startswith("infographic"):
        await state.set_state(PresetForm.waiting_holiday)
        from bot.keyboards import info_holiday_keyboard
        await callback.message.edit_text(get_string("select_holiday", lang), reply_markup=info_holiday_keyboard(lang))
    else:
        await state.set_state(PresetForm.waiting_aspect)
        from bot.keyboards import aspect_ratio_keyboard
        await callback.message.edit_text(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data.startswith("info_holiday:"), PresetForm.waiting_holiday)
async def on_preset_holiday(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(holiday=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_info_load)
    from bot.keyboards import info_load_keyboard
    await callback.message.edit_text(get_string("select_info_load", lang), reply_markup=info_load_keyboard(lang))

@router.callback_query(F.data.startswith("info_load:"), PresetForm.waiting_info_load)
async def on_preset_info_load(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(info_load=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_info_lang)
    from bot.keyboards import info_lang_keyboard
    await callback.message.edit_text(get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))

@router.callback_query(F.data.startswith("info_lang:"), PresetForm.waiting_info_lang)
async def on_preset_info_lang(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(info_lang=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_adv1)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text(get_string("enter_adv1_skip", lang), reply_markup=skip_step_keyboard("adv1", lang))

@router.message(PresetForm.waiting_adv1)
async def on_preset_adv1_text(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(adv1=message.text)
    await state.set_state(PresetForm.waiting_adv2)
    from bot.keyboards import skip_step_keyboard
    await message.answer(get_string("enter_adv2_skip", lang), reply_markup=skip_step_keyboard("adv2", lang))

@router.callback_query(F.data == "adv1:skip", PresetForm.waiting_adv1)
async def on_preset_adv1_skip(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(adv1=None)
    await state.set_state(PresetForm.waiting_adv2)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text(get_string("enter_adv2_skip", lang), reply_markup=skip_step_keyboard("adv2", lang))

@router.message(PresetForm.waiting_adv2)
async def on_preset_adv2_text(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(adv2=message.text)
    await state.set_state(PresetForm.waiting_adv3)
    from bot.keyboards import skip_step_keyboard
    await message.answer(get_string("enter_adv3_skip", lang), reply_markup=skip_step_keyboard("adv3", lang))

@router.callback_query(F.data == "adv2:skip", PresetForm.waiting_adv2)
async def on_preset_adv2_skip(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(adv2=None)
    await state.set_state(PresetForm.waiting_adv3)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text(get_string("enter_adv3_skip", lang), reply_markup=skip_step_keyboard("adv3", lang))

@router.message(PresetForm.waiting_adv3)
async def on_preset_adv3_text(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(adv3=message.text)
    await state.set_state(PresetForm.waiting_extra_info)
    from bot.keyboards import skip_step_keyboard
    await message.answer(get_string("enter_extra_info_skip", lang), reply_markup=skip_step_keyboard("extra_info", lang))

@router.callback_query(F.data == "adv3:skip", PresetForm.waiting_adv3)
async def on_preset_adv3_skip(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(adv3=None)
    await state.set_state(PresetForm.waiting_extra_info)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text(get_string("enter_extra_info_skip", lang), reply_markup=skip_step_keyboard("extra_info", lang))

@router.message(PresetForm.waiting_extra_info)
async def on_preset_extra_info_text(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.from_user.id)
    await state.update_data(extra_info=message.text[:75])
    await state.set_state(PresetForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data == "extra_info:skip", PresetForm.waiting_extra_info)
async def on_preset_extra_info_skip(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.update_data(extra_info=None)
    await state.set_state(PresetForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await callback.message.edit_text(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_height)
async def on_back_to_body_type(callback: CallbackQuery, state: FSMContext, db: Database):
    data = await state.get_data()
    lang = await db.get_user_language(callback.from_user.id)
    if data.get("category") == "child":
        await on_preset_pick(callback, db, state)
    else:
        await state.set_state(PresetForm.waiting_body_type)
        await _replace_with_text(callback, get_string("enter_body_type", lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_age)
async def on_back_to_height(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_height)
    await _replace_with_text(callback, get_string("enter_height_example", lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_pants_style)
async def on_back_to_age(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_age)
    await _replace_with_text(callback, get_string("enter_age_num", lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_sleeve_length)
async def on_back_to_pants_style(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    if data.get("category") == "own":
        await state.set_state(PresetForm.waiting_product_photo)
        await _replace_with_text(callback, get_string("upload_product", lang))
        return
    await state.set_state(PresetForm.waiting_pants_style)
    from bot.keyboards import pants_style_keyboard
    await _replace_with_text(callback, get_string("select_pants_style_btn", lang), reply_markup=pants_style_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_length)
async def on_back_to_sleeve_length(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_sleeve_length)
    from bot.keyboards import sleeve_length_keyboard
    await _replace_with_text(callback, get_string("select_sleeve_length_btn", lang), reply_markup=sleeve_length_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_photo_type)
async def on_back_to_length(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    if data.get("category") == "own_variant":
        await state.set_state(PresetForm.waiting_product_photo)
        await _replace_with_text(callback, get_string("upload_product", lang))
        return
    await state.set_state(PresetForm.waiting_length)
    text = get_string("garment_length_notice", lang)
    from bot.keyboards import garment_length_with_custom_keyboard
    await _replace_with_text(callback, text, reply_markup=garment_length_with_custom_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_pose)
async def on_back_to_photo_type(callback: CallbackQuery, state: FSMContext, db: Database):
    await preset_ask_photo_type(callback.message, state, db)

@router.callback_query(F.data == "back_step", PresetForm.waiting_angle)
async def on_back_to_pose(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_pose)
    from bot.keyboards import pose_keyboard
    await _replace_with_text(callback, get_string("select_pose", lang), reply_markup=pose_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_season)
async def on_back_to_angle(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_angle)
    from bot.keyboards import angle_keyboard
    await _replace_with_text(callback, get_string("select_view", lang), reply_markup=angle_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_holiday)
async def on_back_to_season_info(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_season)
    from bot.keyboards import random_season_keyboard
    await _replace_with_text(callback, get_string("select_season", lang), reply_markup=random_season_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_info_load)
async def on_back_to_holiday(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_holiday)
    from bot.keyboards import info_holiday_keyboard
    await _replace_with_text(callback, get_string("select_holiday", lang), reply_markup=info_holiday_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_info_lang)
async def on_back_to_info_load(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_info_load)
    from bot.keyboards import info_load_keyboard
    await _replace_with_text(callback, get_string("select_info_load", lang), reply_markup=info_load_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_adv1)
async def on_back_to_info_lang(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_info_lang)
    from bot.keyboards import info_lang_keyboard
    await _replace_with_text(callback, get_string("select_info_lang", lang), reply_markup=info_lang_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_adv2)
async def on_back_to_adv1(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_adv1)
    from bot.keyboards import skip_step_keyboard
    await _replace_with_text(callback, get_string("enter_adv1_skip", lang), reply_markup=skip_step_keyboard("adv1", lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_adv3)
async def on_back_to_adv2(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_adv2)
    from bot.keyboards import skip_step_keyboard
    await _replace_with_text(callback, get_string("enter_adv2_skip", lang), reply_markup=skip_step_keyboard("adv2", lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_extra_info)
async def on_back_to_adv3(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_adv3)
    from bot.keyboards import skip_step_keyboard
    await _replace_with_text(callback, get_string("enter_adv3_skip", lang), reply_markup=skip_step_keyboard("adv3", lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_loc_group)
async def on_back_to_gender(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_gender)
    from bot.keyboards import random_gender_keyboard
    await _replace_with_text(callback, get_string("select_gender", lang), reply_markup=random_gender_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_location)
async def on_back_to_loc_group(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_loc_group)
    from bot.keyboards import random_loc_group_keyboard
    await _replace_with_text(callback, get_string("select_loc_group", lang), reply_markup=random_loc_group_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_model_size)
async def on_back_to_pose_info(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_pose)
    from bot.keyboards import pose_keyboard
    await _replace_with_text(callback, get_string("select_pose", lang), reply_markup=pose_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_camera_dist)
async def on_back_to_photo_type_info(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_photo_type)
    from bot.keyboards import form_view_keyboard
    await _replace_with_text(callback, get_string("select_photo_type", lang), reply_markup=form_view_keyboard(lang))

@router.callback_query(F.data.startswith("form_aspect:"), PresetForm.waiting_aspect)
async def on_preset_aspect_done(callback: CallbackQuery, state: FSMContext, db: Database):
    val = callback.data.split(":")[1]
    await state.update_data(aspect=val)
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.result_ready)
    from bot.keyboards import form_generate_keyboard
    await _replace_with_text(callback, get_string("confirm_params", lang), reply_markup=form_generate_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.result_ready)
async def on_back_from_preset_ready(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(PresetForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await _replace_with_text(callback, get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data == "back_step", PresetForm.waiting_aspect)
async def on_back_from_aspect(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    cat = data.get("category")
    
    if cat == "own":
        await state.set_state(PresetForm.waiting_length)
        from bot.keyboards import garment_length_with_custom_keyboard
        await callback.message.edit_text(get_string("garment_length_notice", lang), reply_markup=garment_length_with_custom_keyboard(lang))
    elif cat == "own_variant":
        await state.set_state(PresetForm.waiting_photo_type)
        from bot.keyboards import form_view_keyboard
        await callback.message.edit_text(get_string("select_view", lang), reply_markup=form_view_keyboard(lang))
    elif cat == "random":
        await state.set_state(PresetForm.waiting_length)
        from bot.keyboards import garment_length_with_custom_keyboard
        await callback.message.edit_text(get_string("garment_length_notice", lang), reply_markup=garment_length_with_custom_keyboard(lang))
    elif cat == "infographic_other":
        await state.set_state(PresetForm.waiting_holiday)
        from bot.keyboards import info_holiday_keyboard
        await callback.message.edit_text(get_string("select_holiday", lang), reply_markup=info_holiday_keyboard(lang))
    elif cat in ["female", "male", "child"]:
        await state.set_state(PresetForm.waiting_extra_info)
        from bot.keyboards import skip_step_keyboard
        await callback.message.edit_text(get_string("enter_extra_info_skip", lang), reply_markup=skip_step_keyboard("extra_info", lang))
    else:
        # Default fallback
        await state.set_state(PresetForm.waiting_camera_dist)
        from bot.keyboards import camera_distance_keyboard
        await callback.message.edit_text(get_string("select_camera_dist", lang), reply_markup=camera_distance_keyboard(lang))

@router.callback_query(F.data == "form_generate")
async def on_form_generate(callback: CallbackQuery, state: FSMContext, db: Database):
    global active_generations
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    
    # Проверка техработ
    maint = await db.get_app_setting("maintenance")
    if maint == "1":
        await callback.answer(get_string("maintenance_alert", lang), show_alert=True)
        return

    async with active_generations_lock:
        if active_generations >= 20:
            await callback.answer(get_string("rate_limit", lang), show_alert=True)
            return
        active_generations += 1

    try:
        sub = await db.get_user_subscription(user_id)
        if not sub or sub[3] >= sub[2]:
            await callback.answer(get_string("limit_rem_zero", lang), show_alert=True)
            return

        # Автоматический выбор качества на основе подписки
        plan_type, expires_at, daily_limit, daily_usage, ind_key = sub
        if plan_type.lower() == 'trial':
            quality = 'HD'
        elif '4k' in plan_type.upper():
            quality = '4K'
        else:
            quality = 'HD' # По умолчанию HD для обычных платных если не указано 4К

        data = await state.get_data()
        current_state = await state.get_state()
        
        if current_state and current_state.startswith("PresetForm:"):
            model_id = data.get("model_id")
            prompt_id = data.get("prompt_id")
            category = data.get("category")
            
            async with aiosqlite.connect(db._db_path) as conn:
                async with conn.execute("SELECT text FROM prompts WHERE id=?", (prompt_id,)) as cur:
                    row = await cur.fetchone()
                    base_prompt = row[0] if row else ""
            
            # Подстановка переменных
            replacements = {
                "{Пол}": data.get("gender") or "None",
                "{Пол модели}": data.get("model_gender") or data.get("gender") or "None",
                "{Длина изделия}": data.get("length") or "None",
                "{Тип рукав}": data.get("sleeve_length") or "None",
                "{Тип рукава}": data.get("sleeve_length") or "None",
                "{Тип кроя штанов}": data.get("pants_style") or "None",
                "{Возраст}": data.get("age") or "None",
                "{Возраст модели}": data.get("age") or "None",
                "{Рост}": data.get("height") or "None",
                "{Рост модели}": data.get("height") or "None",
                "{Размер}": data.get("model_size") or "None",
                "{Размер модели}": data.get("model_size") or "None",
                "{Размер тела модели}": data.get("body_type") or "None",
                "{Поза}": data.get("pose") or "None",
                "{Поза модели}": data.get("pose") or "None",
                "{Праздник}": data.get("holiday") or "None",
                "{Сезон}": data.get("season") or "None",
                "{Локация}": data.get("location") or "None",
                "{Тип локации}": data.get("location_group") or "None",
                "{Стиль локации}": data.get("location") or "None",
                "{НАГРУЖЕННОСТЬ ИНФОГРАФИКИ}": data.get("info_load") or "None",
                "{Нагруженность инфографики}": data.get("info_load") or "None",
                "{ЯЗЫК ИНФОГРАФИКИ}": data.get("info_lang") or "None",
                "{Язык инфографики}": data.get("info_lang") or "None",
                "{Преимущество 1}": data.get("adv1") or "None",
                "{Топ 1 преимущества товара}": data.get("adv1") or "None",
                "{Преимущество 2}": data.get("adv2") or "None",
                "{Топ 2 преимущества товара}": data.get("adv2") or "None",
                "{Преимущество 3}": data.get("adv3") or "None",
                "{Топ 3 преимущества товара}": data.get("adv3") or "None",
                "{ДОП ИНФОРМАЦИЯ}": data.get("extra_info") or "None",
                "{Дополнительная информация о продукте}": data.get("extra_info") or "None",
                "{ДОП ИНФОРМАЦИЯ ДО 75 СИМВОЛОВ}": data.get("extra_info") or "None",
                "{РАСТОЯНИЕ КАМЕРЫ}": data.get("camera_dist") or data.get("angle") or "None",
                "{ракурс фотографии}": data.get("camera_dist") or data.get("angle") or "None",
                "{РАКУРС}": data.get("photo_type") or "None",
                "{Угол камеры}": data.get("photo_type") or "None",
                "{Ширина}": data.get("width") or "None",
                "{Высота}": data.get("height") or "None",
                "{Длина}": data.get("length") or "None",
                "{Название продукта}": data.get("product_name") or "None",
                "{Название товара/бренда}": data.get("product_name") or "None",
                "{Стиль инфографики}": data.get("info_style") or "None",
                "{Стиль}": data.get("info_style") or "None",
                "{Тип шрифта}": data.get("font_type") or "None",
                "{Присутствие человека на фото}": "Yes" if data.get("has_person") == "yes" else "No",
            }
            
            final_prompt = base_prompt
            for k, v in replacements.items():
                final_prompt = final_prompt.replace(k, str(v))
            
            # Логика для детей (child)
            if category == "child":
                final_prompt = "Kid style, soft lighting, child model. " + final_prompt

            aspect = data.get("aspect") or data.get("form_aspect") or "3:4"
            final_prompt += f"\nResolution: {quality}. Aspect: {aspect}."
            final_prompt += "\nBrand name: AI-ROOM."
            
            async with aiosqlite.connect(db._db_path) as conn:
                async with conn.execute("SELECT photo_file_id FROM models WHERE id=?", (model_id,)) as cur:
                    row = await cur.fetchone()
                    model_photo = row[0] if row else None
            
            input_image_bytes = None
            bg_image_bytes = None
            
            # Если есть фото товара (product_photo) и фона (background_photo) - это Свой Вариант
            if data.get("product_photo"):
                # Скачиваем товар
                pfile = await callback.bot.get_file(data["product_photo"])
                pb = await callback.bot.download_file(pfile.file_path)
                input_image_bytes = pb.read()
                
                # Если есть фон (background_photo) - скачиваем его
                if data.get("background_photo"):
                    bfile = await callback.bot.get_file(data["background_photo"])
                    bb = await callback.bot.download_file(bfile.file_path)
                    bg_image_bytes = bb.read()
            elif model_photo:
                if model_photo.startswith('data/uploads') or model_photo.startswith('C:'):
                    if os.path.exists(model_photo):
                        with open(model_photo, "rb") as f:
                            input_image_bytes = f.read()
                else:
                    file = await callback.bot.get_file(model_photo)
                    f_bytes = await callback.bot.download_file(file.file_path)
                    input_image_bytes = f_bytes.read()

        else:
            prompt = data.get("market_prompt", "")
            if data.get("market_advantage"): prompt += f"\nAdvantage: {data['market_advantage']}"
            aspect = data.get("form_aspect") or data.get("aspect") or "3:4"
            prompt += f"\nResolution: {quality}. Aspect: {aspect}."
            prompt += "\nBrand name: AI-ROOM."
            final_prompt = prompt
            
            photos = data.get("photos", [])
            input_image_bytes = []
            for photo_id in photos:
                file = await callback.bot.get_file(photo_id)
                f_bytes = await callback.bot.download_file(file.file_path)
                input_image_bytes.append(f_bytes.read())
            
            if not input_image_bytes:
                # Если вдруг нет фото в photos (старый формат), пробуем взять из product_photo
                if data.get("product_photo"):
                    file = await callback.bot.get_file(data["product_photo"])
                    f_bytes = await callback.bot.download_file(file.file_path)
                    input_image_bytes = [f_bytes.read()]

        await _replace_with_text(callback, get_string("generation_started", lang), reply_markup=None)
        
        # Выбор ключа: индивидуальный для 4K или общие для остальных
        plan_type = sub[0]
        individual_key = sub[4]
        
        target_keys = []
        if "4K" in plan_type.upper():
            if not individual_key:
                await callback.message.answer(get_string("missing_4k_key", lang))
                return
            target_keys = [(0, individual_key, 1, 0, 0, 0, None, None, None)] # Mock structure
        else:
            target_keys = await db.list_api_keys()

        result_bytes = None
        for kid, token, active, priority, daily, total, last_reset, created, updated in target_keys:
            if not active: continue
            
            # Для индивидуальных ключей лимиты пока не проверяем по БД (они на совести юзера или внешнего сервиса)
            if kid != 0:
                allowed, _ = await db.check_api_key_limits(kid)
                if not allowed: continue
            
            try:
                result_bytes = await generate_image(token, final_prompt, input_image_bytes, bg_image_bytes, "gemini-3-pro-image-preview")
                if result_bytes:
                    if kid != 0:
                        await db.record_api_usage(kid)
                    break
            except Exception as e:
                logger.error(f"Error generating image with key {kid}: {e}")
                continue

        if not result_bytes:
            await callback.message.answer(get_string("error_api", lang))
            return

        await db.update_daily_usage(user_id)
        pid = await db.generate_pid()
        
        await callback.message.answer_photo(
            BufferedInputFile(result_bytes, filename=f"{pid}.jpg"),
            caption=f"PID: `{pid}`",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(lang)
        )
        
        await db.add_generation_history(pid, user_id, "preset" if current_state and current_state.startswith("PresetForm:") else "market", 
                                       json.dumps(data), json.dumps(data.get("photos", [])), "FILE_ID_MOCK")
        await state.clear()
        
    finally:
        async with active_generations_lock:
            active_generations -= 1

@router.callback_query(F.data == "menu_history")
async def on_history(callback: CallbackQuery, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    gens = await db.list_user_generations(callback.from_user.id, limit=20)
    if not gens:
        await callback.answer(get_string("history_empty", lang), show_alert=True)
        return
    
    text = get_string("history_title", lang) + "\n\n"
    for pid, res_id, date in gens:
        text += f"🔹 PID: `{pid}` | {date}\n"
    
    await _replace_with_text(callback, text, reply_markup=history_pagination_keyboard(0, 1, lang))

@router.callback_query(F.data == "back_main")
async def on_back_main(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("start_welcome", lang), reply_markup=main_menu_keyboard(lang))

@router.callback_query(F.data == "menu_howto")
async def on_howto(callback: CallbackQuery, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    text = await db.get_app_setting("howto") or get_string("how_to", lang)
    await _replace_with_text(callback, text, reply_markup=back_main_keyboard(lang))

@router.callback_query(F.data == "menu_subscription")
async def on_sub_menu(callback: CallbackQuery, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    user_id = callback.from_user.id
    sub = await db.get_user_subscription(user_id)
    
    plans = await db.list_subscription_plans()
    
    if sub:
        plan_name, expires, limit, usage, api_key = sub
        rem = max(0, limit - usage)
        # Форматируем дату (убираем T и миллисекунды)
        formatted_date = expires.replace("T", " ")[:16]
        text = get_string("profile_info", lang, id=user_id, sub=get_string("sub_active", lang, plan=plan_name.upper(), date=formatted_date), daily_rem=rem)
        await _replace_with_text(callback, text, reply_markup=plans_keyboard(plans, lang))
    else:
        await _replace_with_text(callback, get_string("buy_plan", lang), reply_markup=plans_keyboard(plans, lang))

@router.callback_query(F.data.startswith("buy_plan:"))
async def on_buy_plan(callback: CallbackQuery, db: Database):
    plan_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    
    plan = await db.get_subscription_plan(plan_id)
    if not plan: return
    
    name = plan[1] if lang == "ru" else (plan[2] if lang == "en" else plan[3])
    desc = plan[4] if lang == "ru" else (plan[5] if lang == "en" else plan[6])
    price = plan[7]
    
    text = get_string("buy_sub_text", lang, name=name, desc=desc, price=price)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_string("confirm_btn", lang), callback_data=f"confirm_buy:{plan_id}")],
        [InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_subscription")]
    ])
    
    await _replace_with_text(callback, text, reply_markup=kb)

@router.callback_query(F.data.startswith("confirm_buy:"))
async def on_confirm_buy(callback: CallbackQuery, db: Database):
    plan_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    
    plan = await db.get_subscription_plan(plan_id)
    if not plan: return
    
    await db.grant_subscription(user_id, plan_id, plan[1], plan[8], plan[9])
    
    msg_key = "sub_success_alert"
    if "4K" in plan[1].upper():
        msg_key = "sub_success_4k"
        
    await callback.answer(get_string(msg_key, lang), show_alert=True)
    await on_menu_profile(callback, db)
