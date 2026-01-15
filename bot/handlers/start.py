from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
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
    language_keyboard, marketplace_menu_keyboard, plans_keyboard,
    history_pagination_keyboard, aspect_ratio_keyboard,
    form_generate_keyboard, subscription_check_keyboard,
    back_main_keyboard, create_product_keyboard_dynamic,
    model_select_keyboard_presets, pants_style_keyboard,
    sleeve_length_keyboard, garment_length_with_custom_keyboard,
    form_view_keyboard, pose_keyboard, angle_keyboard,
    plus_season_keyboard, quality_keyboard_with_back,
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
    waiting_quality = State()
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
    await _replace_with_text(callback, "Выберите пол модели:", reply_markup=random_gender_keyboard())

@router.callback_query(F.data == "create_own")
async def on_create_own_model(callback: CallbackQuery, db: Database, state: FSMContext):
    await state.set_state(PresetForm.waiting_background_photo)
    await state.update_data(category="own")
    await _replace_with_text(callback, "Пришлите фото вашей модели (на ком будем менять одежду):")

@router.callback_query(F.data == "create_own_variant")
async def on_create_own_bg(callback: CallbackQuery, db: Database, state: FSMContext):
    await state.set_state(PresetForm.waiting_background_photo)
    await state.update_data(category="own_variant")
    await _replace_with_text(callback, "Пришлите фото фона (с моделью или без):")

@router.callback_query(F.data.startswith("rand_gender:"), PresetForm.waiting_gender)
async def on_rand_gender(callback: CallbackQuery, state: FSMContext, db: Database):
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    data = await state.get_data()
    
    if data.get("category") == "own":
        # Если это 'Свой вариант МОДЕЛИ', после пола идем к параметрам (рост, возраст и т.д.)
        await state.set_state(PresetForm.waiting_height)
        await callback.message.edit_text("Введите рост модели (например, 170):")
    else:
        # Если это 'Одежда и обувь (Рандом)', идем к выбору локации
        await state.set_state(PresetForm.waiting_loc_group)
        from bot.keyboards import random_loc_group_keyboard
        await _replace_with_text(callback, "Где будет проходить съемка?", reply_markup=random_loc_group_keyboard())

@router.callback_query(F.data.startswith("rand_locgroup:"), PresetForm.waiting_loc_group)
async def on_rand_locgroup(callback: CallbackQuery, state: FSMContext):
    group = callback.data.split(":")[1]
    await state.update_data(loc_group=group)
    await state.set_state(PresetForm.waiting_location)
    from bot.keyboards import random_location_outdoor_keyboard, random_location_indoor_keyboard
    if group == "outdoor":
        await _replace_with_text(callback, "Выберите локацию на улице:", reply_markup=random_location_outdoor_keyboard())
    else:
        await _replace_with_text(callback, "Выберите локацию в помещении:", reply_markup=random_location_indoor_keyboard())

@router.callback_query(F.data.startswith("rand_loc:"), PresetForm.waiting_location)
async def on_rand_loc(callback: CallbackQuery, state: FSMContext):
    loc = callback.data.split(":")[1]
    if loc == "custom":
        await state.set_state(PresetForm.waiting_loc_custom)
        await callback.message.edit_text("Введите ваш вариант локации (до 100 символов):")
    else:
        await state.update_data(location=loc)
        await on_after_location(callback.message, state)

@router.message(PresetForm.waiting_loc_custom)
async def on_rand_loc_custom(message: Message, state: FSMContext):
    await state.update_data(location=message.text[:100])
    await on_after_location(message, state)

async def on_after_location(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("loc_group") == "outdoor":
        await state.set_state(PresetForm.waiting_season)
        from bot.keyboards import random_season_keyboard
        await message.answer("Выберите время года:", reply_markup=random_season_keyboard())
    else:
        # Для помещений сразу к праздникам
        await state.set_state(PresetForm.waiting_holiday)
        from bot.keyboards import random_holiday_keyboard
        await message.answer("Выберите праздник:", reply_markup=random_holiday_keyboard())

@router.callback_query(F.data.startswith("rand_season:"), PresetForm.waiting_season)
async def on_rand_season(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(season=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_holiday)
    from bot.keyboards import random_holiday_keyboard
    await _replace_with_text(callback, "Выберите праздник:", reply_markup=random_holiday_keyboard())

@router.callback_query(F.data.startswith("rand_holiday:"), PresetForm.waiting_holiday)
async def on_rand_holiday(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    if val == "custom":
        await state.set_state(PresetForm.waiting_holiday_custom)
        await callback.message.edit_text("Введите ваш вариант праздника (до 30 символов):")
    else:
        await state.update_data(holiday=None if val == "skip" else val)
        await on_after_holiday(callback.message, state)

@router.message(PresetForm.waiting_holiday_custom)
async def on_rand_holiday_custom(message: Message, state: FSMContext):
    await state.update_data(holiday=message.text[:30])
    await on_after_holiday(message, state)

async def on_after_holiday(message: Message, state: FSMContext):
    await state.set_state(PresetForm.waiting_pose)
    from bot.keyboards import pose_keyboard
    await message.answer("Выберите позу:", reply_markup=pose_keyboard())

@router.callback_query(F.data.startswith("pose:"), PresetForm.waiting_pose)
async def on_rand_pose(callback: CallbackQuery, state: FSMContext):
    await state.update_data(pose=callback.data.split(":")[1])
    await state.set_state(PresetForm.waiting_model_size)
    from bot.keyboards import form_length_skip_keyboard
    await _replace_with_text(callback, "Введите размер модели (числом):", reply_markup=form_length_skip_keyboard())

@router.message(PresetForm.waiting_background_photo, F.photo)
async def on_own_bg_photo(message: Message, state: FSMContext):
    await state.update_data(background_photo=message.photo[-1].file_id)
    await state.set_state(PresetForm.waiting_product_photo)
    await message.answer("Теперь пришлите фото товара:")

@router.message(PresetForm.waiting_product_photo, F.photo)
async def on_own_product_photo(message: Message, state: FSMContext):
    await state.update_data(product_photo=message.photo[-1].file_id)
    data = await state.get_data()
    if data.get("category") == "own_variant":
        # Сценарий 'Свой вариант ФОНА'
        await state.set_state(PresetForm.waiting_photo_type)
        from bot.keyboards import form_view_keyboard
        await message.answer("Выберите ракурс фотографии:", reply_markup=form_view_keyboard())
    elif data.get("category") == "own":
        # Сценарий 'Свой вариант МОДЕЛИ' - теперь спрашиваем пол/тип одежды
        await state.set_state(PresetForm.waiting_gender)
        from bot.keyboards import random_gender_keyboard
        await message.answer("Выберите пол/тип модели для генерации:", reply_markup=random_gender_keyboard())
    else:
        await state.set_state(PresetForm.waiting_height)
        await message.answer("Введите рост модели (например, 170):")

@router.callback_query(F.data == "form_len:skip", PresetForm.waiting_model_size)
async def on_rand_size_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(model_size=None)
    await state.set_state(PresetForm.waiting_height)
    await callback.message.edit_text("Введите рост модели (например, 170):")

@router.message(PresetForm.waiting_height, F.state == PresetForm.waiting_height)
async def on_rand_height(message: Message, state: FSMContext):
    await state.update_data(height=message.text)
    await state.set_state(PresetForm.waiting_age)
    await message.answer("Введите возраст модели числом:")

@router.message(PresetForm.waiting_age, F.state == PresetForm.waiting_age)
async def on_rand_age(message: Message, state: FSMContext):
    await state.update_data(age=message.text)
    await state.set_state(PresetForm.waiting_pants_style)
    from bot.keyboards import pants_style_keyboard
    await message.answer("Выберите тип кроя штанов:", reply_markup=pants_style_keyboard())

@router.callback_query(F.data.startswith("pants_style:"), PresetForm.waiting_pants_style)
async def on_rand_pants_style(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(pants_style=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_sleeve_length)
    from bot.keyboards import sleeve_length_keyboard
    await _replace_with_text(callback, "Выберите тип рукавов:", reply_markup=sleeve_length_keyboard())

@router.callback_query(F.data.startswith("form_sleeve:"), PresetForm.waiting_sleeve_length)
async def on_rand_sleeve(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(sleeve_length=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_length)
    from bot.keyboards import garment_length_with_custom_keyboard
    text = "Выберите длину изделия. Внимание! если ваш продукт Костюм 2-к,3-к то длину можно не указывать."
    await _replace_with_text(callback, text, reply_markup=garment_length_with_custom_keyboard())

@router.callback_query(F.data.startswith("garment_len:"), PresetForm.waiting_length)
async def on_rand_length_btn(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(length=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_photo_type)
    from bot.keyboards import form_view_keyboard
    await _replace_with_text(callback, "Выберите ракурс фотографии:", reply_markup=form_view_keyboard())

@router.callback_query(F.data.startswith("form_view:"), PresetForm.waiting_photo_type)
async def on_rand_view(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photo_type=callback.data.split(":")[1])
    await state.set_state(PresetForm.waiting_camera_dist)
    from bot.keyboards import camera_distance_keyboard
    await _replace_with_text(callback, "Выберите ракурс (удаленность):", reply_markup=camera_distance_keyboard())

# Добавляем обработку остальных шагов аналогично пресетам, но с новыми клавиатурами
@router.callback_query(F.data.startswith("camera_dist:"), PresetForm.waiting_camera_dist)
async def on_rand_camera_dist(callback: CallbackQuery, state: FSMContext):
    await state.update_data(camera_dist=callback.data.split(":")[1])
    await state.set_state(PresetForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await _replace_with_text(callback, "Выберите формат фото:", reply_markup=aspect_ratio_keyboard())

@router.callback_query(F.data.startswith("form_aspect:"), PresetForm.waiting_aspect)
async def on_rand_aspect(callback: CallbackQuery, state: FSMContext):
    await state.update_data(aspect=callback.data.split(":")[1])
    await state.set_state(PresetForm.result_ready)
    from bot.keyboards import confirm_generation_keyboard
    await _replace_with_text(callback, "Все готово! Создать фото?", reply_markup=confirm_generation_keyboard())

@router.callback_query(F.data == "create_cat:infographic_clothing")
async def on_create_infographic_clothing(callback: CallbackQuery, db: Database, state: FSMContext):
    await state.update_data(category="infographic_clothing")
    await state.set_state(PresetForm.waiting_info_load)
    await _replace_with_text(callback, "Инфографика: Выберите нагруженность (введите число от 1 до 10):")

@router.callback_query(F.data == "create_cat:infographic_other")
async def on_create_infographic_other(callback: CallbackQuery, db: Database, state: FSMContext):
    await state.update_data(category="infographic_other")
    await state.set_state(PresetForm.waiting_info_load)
    await _replace_with_text(callback, "Инфографика: Выберите нагруженность (введите число от 1 до 10):")

@router.message(PresetForm.waiting_info_load)
async def on_info_load_numeric(message: Message, state: FSMContext):
    await state.update_data(info_load=message.text)
    await state.set_state(PresetForm.waiting_product_name)
    await message.answer("Введите название вашего продукта вкратце (какой у вас продукт? до 75 символов):")

@router.message(PresetForm.waiting_product_name)
async def on_product_name(message: Message, state: FSMContext):
    await state.update_data(product_name=message.text[:75])
    await state.set_state(PresetForm.waiting_width)
    from bot.keyboards import skip_step_keyboard
    await message.answer("Введите параметры: 1. Ширина (числом) или пропустите:", reply_markup=skip_step_keyboard("width"))

@router.callback_query(F.data == "width:skip", PresetForm.waiting_width)
async def on_width_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(width=None)
    await state.set_state(PresetForm.waiting_height)
    from bot.keyboards import skip_step_keyboard
    await _replace_with_text(callback, "Введите высоту (числом) или пропустите:", reply_markup=skip_step_keyboard("height"))

@router.message(PresetForm.waiting_width)
async def on_width_text(message: Message, state: FSMContext):
    await state.update_data(width=message.text)
    await state.set_state(PresetForm.waiting_height)
    from bot.keyboards import skip_step_keyboard
    await message.answer("Введите высоту (числом) или пропустите:", reply_markup=skip_step_keyboard("height"))

@router.callback_query(F.data == "height:skip", PresetForm.waiting_height)
async def on_height_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(height=None)
    await state.set_state(PresetForm.waiting_length)
    from bot.keyboards import skip_step_keyboard
    await _replace_with_text(callback, "Введите длину (числом) или пропустите:", reply_markup=skip_step_keyboard("length"))

@router.message(PresetForm.waiting_height)
async def on_height_text(message: Message, state: FSMContext):
    await state.update_data(height=message.text)
    await state.set_state(PresetForm.waiting_length)
    from bot.keyboards import skip_step_keyboard
    await message.answer("Введите длину (числом) или пропустите:", reply_markup=skip_step_keyboard("length"))

@router.callback_query(F.data == "length:skip", PresetForm.waiting_length)
async def on_length_skip_info(callback: CallbackQuery, state: FSMContext):
    await state.update_data(length=None)
    await state.set_state(PresetForm.waiting_camera_dist)
    from bot.keyboards import camera_distance_keyboard
    await _replace_with_text(callback, "Выберите ракурс фотографии:", reply_markup=camera_distance_keyboard())

@router.message(PresetForm.waiting_length)
async def on_length_text_info(message: Message, state: FSMContext):
    await state.update_data(length=message.text)
    await state.set_state(PresetForm.waiting_camera_dist)
    from bot.keyboards import camera_distance_keyboard
    await message.answer("Выберите ракурс фотографии:", reply_markup=camera_distance_keyboard())

@router.callback_query(F.data.startswith("camera_dist:"), PresetForm.waiting_camera_dist)
async def on_camera_dist_info(callback: CallbackQuery, state: FSMContext):
    await state.update_data(camera_dist=callback.data.split(":")[1])
    await state.set_state(PresetForm.waiting_season)
    from bot.keyboards import random_season_keyboard
    await _replace_with_text(callback, "Выберите время года:", reply_markup=random_season_keyboard())

@router.callback_query(F.data.startswith("rand_season:"), PresetForm.waiting_season)
async def on_season_info_other(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(season=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_holiday)
    from bot.keyboards import random_holiday_keyboard
    await _replace_with_text(callback, "Выберите праздник:", reply_markup=random_holiday_keyboard())

@router.callback_query(F.data.startswith("rand_holiday:"), PresetForm.waiting_holiday)
async def on_holiday_info_other(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    if val == "custom":
        await state.set_state(PresetForm.waiting_holiday_custom)
        await callback.message.edit_text("Введите ваш вариант праздника (до 30 символов):")
    else:
        await state.update_data(holiday=None if val == "skip" else val)
        await on_after_holiday_info(callback.message, state)

@router.message(PresetForm.waiting_holiday_custom)
async def on_holiday_custom_info(message: Message, state: FSMContext):
    await state.update_data(holiday=message.text[:30])
    await on_after_holiday_info(message, state)

async def on_after_holiday_info(message: Message, state: FSMContext):
    await state.set_state(PresetForm.waiting_adv1)
    await message.answer("Введите первое преимущество словами (до 180 символов):")

@router.message(PresetForm.waiting_adv1)
async def on_adv1_text(message: Message, state: FSMContext):
    await state.update_data(adv1=message.text[:180])
    await state.set_state(PresetForm.waiting_adv2)
    await message.answer("Введите второе преимущество словами (до 180 символов):")

@router.message(PresetForm.waiting_adv2)
async def on_adv2_text(message: Message, state: FSMContext):
    await state.update_data(adv2=message.text[:180])
    await state.set_state(PresetForm.waiting_adv3)
    await message.answer("Введите третье преимущество словами (до 180 символов):")

@router.message(PresetForm.waiting_adv3)
async def on_adv3_text(message: Message, state: FSMContext):
    await state.update_data(adv3=message.text[:180])
    await state.set_state(PresetForm.waiting_extra_info)
    from bot.keyboards import skip_step_keyboard
    await message.answer("Введите дополнение если есть какие либо предпочтения (до 100 символов) или пропустите:", reply_markup=skip_step_keyboard("extra"))

@router.callback_query(F.data == "extra:skip", PresetForm.waiting_extra_info)
async def on_extra_skip_info_other(callback: CallbackQuery, state: FSMContext):
    await state.update_data(extra_info=None)
    await state.set_state(PresetForm.waiting_gender)
    from bot.keyboards import infographic_gender_extended_keyboard
    await _replace_with_text(callback, "К какому полу относится данный продукт:", reply_markup=infographic_gender_extended_keyboard())

@router.message(PresetForm.waiting_extra_info)
async def on_extra_text_info_other(message: Message, state: FSMContext):
    await state.update_data(extra_info=message.text[:100])
    await state.set_state(PresetForm.waiting_gender)
    from bot.keyboards import infographic_gender_extended_keyboard
    await message.answer("К какому полу относится данный продукт:", reply_markup=infographic_gender_extended_keyboard())

@router.callback_query(F.data.startswith("info_gender:"), PresetForm.waiting_gender)
async def on_info_gender_ext(callback: CallbackQuery, state: FSMContext):
    await state.update_data(gender=callback.data.split(":")[1])
    await state.set_state(PresetForm.waiting_info_style)
    from bot.keyboards import infographic_style_keyboard
    await _replace_with_text(callback, "Выберите стиль инфографики:", reply_markup=infographic_style_keyboard())

@router.callback_query(F.data.startswith("info_style:"), PresetForm.waiting_info_style)
async def on_info_style(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    if val == "skip":
        await state.update_data(info_style=None)
        await state.set_state(PresetForm.waiting_font_type)
        from bot.keyboards import font_type_keyboard
        await _replace_with_text(callback, "Выберите тип шрифта:", reply_markup=font_type_keyboard())
    elif val == "custom":
        await state.set_state(PresetForm.waiting_info_style_custom)
        await callback.message.edit_text("Введите свой вариант стиля (до 20 символов):")
    else:
        await state.update_data(info_style=val)
        await state.set_state(PresetForm.waiting_font_type)
        from bot.keyboards import font_type_keyboard
        await _replace_with_text(callback, "Выберите тип шрифта:", reply_markup=font_type_keyboard())

@router.message(PresetForm.waiting_info_style_custom)
async def on_info_style_custom(message: Message, state: FSMContext):
    await state.update_data(info_style=message.text[:20])
    await state.set_state(PresetForm.waiting_font_type)
    from bot.keyboards import font_type_keyboard
    await message.answer("Выберите тип шрифта:", reply_markup=font_type_keyboard())

@router.callback_query(F.data.startswith("font_type:"), PresetForm.waiting_font_type)
async def on_font_type(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    if val == "skip":
        await state.update_data(font_type=None)
        await state.set_state(PresetForm.waiting_info_lang)
        from bot.keyboards import info_lang_keyboard_extended
        await _replace_with_text(callback, "Выберите язык инфографики:", reply_markup=info_lang_keyboard_extended())
    elif val == "custom":
        await state.set_state(PresetForm.waiting_font_type_custom)
        await callback.message.edit_text("Введите свой вариант шрифта (до 20 символов):")
    else:
        await state.update_data(font_type=val)
        await state.set_state(PresetForm.waiting_info_lang)
        from bot.keyboards import info_lang_keyboard_extended
        await _replace_with_text(callback, "Выберите язык инфографики:", reply_markup=info_lang_keyboard_extended())

@router.message(PresetForm.waiting_font_type_custom)
async def on_font_type_custom(message: Message, state: FSMContext):
    await state.update_data(font_type=message.text[:20])
    await state.set_state(PresetForm.waiting_info_lang)
    from bot.keyboards import info_lang_keyboard_extended
    await message.answer("Выберите язык инфографики:", reply_markup=info_lang_keyboard_extended())

@router.callback_query(F.data.startswith("info_lang:"), PresetForm.waiting_info_lang)
async def on_info_lang_ext(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    if val == "custom":
        await state.set_state(PresetForm.waiting_info_lang_custom)
        await callback.message.edit_text("Введите свой вариант языка:")
    else:
        await state.update_data(info_lang=val)
        await state.set_state(PresetForm.waiting_aspect)
        from bot.keyboards import aspect_ratio_keyboard
        await _replace_with_text(callback, "Выберите формат фото:", reply_markup=aspect_ratio_keyboard())

@router.message(PresetForm.waiting_info_lang_custom)
async def on_info_lang_custom(message: Message, state: FSMContext):
    await state.update_data(info_lang=message.text)
    await state.set_state(PresetForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await message.answer("Выберите формат фото:", reply_markup=aspect_ratio_keyboard())

@router.callback_query(F.data == "create_normal_gen")
async def on_create_normal_gen(callback: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    await state.set_state(CreateForm.waiting_photos)
    await state.update_data(photos=[])
    await _replace_with_text(callback, "Обычная генерация: Пришлите от 1 до 3-х фотографий. Когда закончите, нажмите кнопку ниже.", 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text="✅ Готово, к тексту", callback_data="photos_done")],
                                 [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
                             ]))

@router.message(CreateForm.waiting_photos, F.photo)
async def on_normal_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= 3:
        await message.answer("Максимум 3 фото. Нажмите 'Готово', чтобы продолжить.")
        return
    
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    
    if len(photos) < 3:
        await message.answer(f"Фото получено ({len(photos)}/3). Пришлите еще или нажмите 'Готово'.", 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text="✅ Готово, к тексту", callback_data="photos_done")]
                             ]))
    else:
        await message.answer("Получено 3 фото. Теперь введите текст описания (до 1000 символов):")
        await state.set_state(CreateForm.waiting_text)

@router.callback_query(F.data == "photos_done", CreateForm.waiting_photos)
async def on_photos_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("photos"):
        await callback.answer("Пришлите хотя бы одно фото!", show_alert=True)
        return
    
    await state.set_state(CreateForm.waiting_text)
    await _replace_with_text(callback, "Теперь введите текст описания (до 1000 символов):")

@router.message(CreateForm.waiting_text)
async def on_normal_text(message: Message, state: FSMContext):
    await state.update_data(market_prompt=message.text[:1000]) # Используем market_prompt для совместимости с on_form_generate
    await state.set_state(CreateForm.waiting_aspect)
    from bot.keyboards import aspect_ratio_keyboard
    await message.answer("Выберите формат фото:", reply_markup=aspect_ratio_keyboard())

@router.callback_query(F.data.startswith("form_aspect:"), CreateForm.waiting_aspect)
async def on_normal_aspect(callback: CallbackQuery, state: FSMContext):
    await state.update_data(form_aspect=callback.data.split(":")[1])
    await state.set_state(CreateForm.result_ready)
    from bot.keyboards import confirm_generation_keyboard
    await _replace_with_text(callback, "Все готово! Начать генерацию?", reply_markup=confirm_generation_keyboard())

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
        await callback.answer(f"В категории {gender} пока нет моделей", show_alert=True)
        return
        
    model = await db.get_model_by_index(category, gender, 0)
    from bot.keyboards import model_select_keyboard_presets
    kb = model_select_keyboard_presets(category, gender, 0, total, lang)
    
    await callback.message.delete()
    await _send_model_photo(callback, model[3], f"Прессеты для {gender}\n\nМодель: {model[1]} (1/{total})", kb)

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
        await message.answer("🛠 В боте проводятся технические работы. Пожалуйста, попробуйте позже.\nВремя вашей подписки будет продлено на время техработ.")
        return
    
    # Регистрация пользователя
    await db.upsert_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    lang = await db.get_user_language(user_id)
    
    # 1. Обязательная подписка
    if not await check_user_subscription(user_id, bot, db):
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
        plan, expires, limit, usage = sub
        rem = max(0, limit - usage)
        sub_text = get_string("sub_active", lang, plan=plan.upper(), date=expires)
    else:
        sub_text = get_string("sub_none", lang)
        rem = 0
    
    text = get_string("profile_info", lang, id=user_id, sub=sub_text, daily_rem=rem)
    await _replace_with_text(callback, text, reply_markup=profile_keyboard(lang))

@router.callback_query(F.data == "settings_lang")
async def on_settings_lang(callback: CallbackQuery, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, get_string("select_lang", lang), reply_markup=language_keyboard(lang))

@router.callback_query(F.data.startswith("lang:"))
async def on_set_lang(callback: CallbackQuery, db: Database):
    new_lang = callback.data.split(":")[1]
    await db.set_user_language(callback.from_user.id, new_lang)
    await on_menu_profile(callback, db)

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
        await callback.message.answer(f"{caption}\n\n(Ошибка фото: {e})", reply_markup=reply_markup)

@router.callback_query(F.data == "menu_market")
async def on_menu_market(callback: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    lang = await db.get_user_language(callback.from_user.id)

    # Проверка техработ
    maint = await db.get_app_setting("maintenance")
    if maint == "1":
        await callback.answer("🛠 Технические работы. Подписка будет продлена.", show_alert=True)
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
    disclaimer = "Текст: обратите внимание внешность или другие параметры могут отличаться в зависимости от заданных параметров."
    from bot.keyboards import create_product_keyboard_dynamic
    await _replace_with_text(callback, disclaimer, reply_markup=create_product_keyboard_dynamic(cat_status, prices))

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
        await callback.answer("В этой категории пока нет моделей", show_alert=True)
        return
        
    model = await db.get_model_by_index(category, "default", 0)
    kb = model_select_keyboard_presets(category, "default", 0, total, lang)
    
    await callback.message.delete()
    await _send_model_photo(callback, model[3], f"Прессеты для одежды\n\nМодель: {model[1]} (1/{total})", kb)

@router.callback_query(F.data.startswith("preset_nav:"))
async def on_preset_nav(callback: CallbackQuery, db: Database, state: FSMContext):
    _, category, cloth, index = callback.data.split(":")
    index = int(index)
    total = await db.count_models(category, cloth)
    
    if index < 0: index = total - 1
    if index >= total: index = 0
    
    model = await db.get_model_by_index(category, cloth, index)
    lang = await db.get_user_language(callback.from_user.id)
    kb = model_select_keyboard_presets(category, cloth, index, total, lang)
    
    await callback.message.delete()
    await _send_model_photo(callback, model[3], f"Прессеты для одежды\n\nМодель: {model[1]} ({index+1}/{total})", kb)

@router.callback_query(F.data.startswith("preset_pick:"), PresetForm.waiting_model_pick)
async def on_preset_pick(callback: CallbackQuery, db: Database, state: FSMContext):
    _, category, cloth, index = callback.data.split(":")
    model = await db.get_model_by_index(category, cloth, int(index))
    lang = await db.get_user_language(callback.from_user.id)
    
    await state.update_data(model_id=model[0], prompt_id=model[2], category=category, cloth=cloth)
    
    if category == "infographic_other":
        # Для прочих товаров пропускаем рост/возраст/тело и идем к инфографическим параметрам
        await state.set_state(PresetForm.waiting_holiday)
        from bot.keyboards import info_holiday_keyboard
        await callback.message.answer("Выберите праздник (или пропустите):", reply_markup=info_holiday_keyboard())
    elif category == "child":
        await state.set_state(PresetForm.waiting_height)
        await callback.message.answer("Введите рост модели в числах на пример 170.")
    else:
        await state.set_state(PresetForm.waiting_body_type)
        await callback.message.answer("Выберите телосложение или введите числом:")

@router.message(PresetForm.waiting_body_type)
async def on_preset_body_type(message: Message, state: FSMContext):
    await state.update_data(body_type=message.text)
    await state.set_state(PresetForm.waiting_height)
    await message.answer("Введите рост модели в числах на пример 170.")

@router.message(PresetForm.waiting_height)
async def on_preset_height(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(height=message.text)
    await state.set_state(PresetForm.waiting_age)
    await message.answer("Введите возраст модели числом:")

@router.message(PresetForm.waiting_age)
async def on_preset_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(age=message.text)
    await state.set_state(PresetForm.waiting_pants_style)
    await message.answer("Выберите тип кроя штанов:", reply_markup=pants_style_keyboard())

@router.callback_query(F.data.startswith("pants_style:"), PresetForm.waiting_pants_style)
async def on_preset_pants_style(callback: CallbackQuery, state: FSMContext):
    style = callback.data.split(":")[1]
    if style == "skip":
        await state.update_data(pants_style=None)
    else:
        await state.update_data(pants_style=style)
    await state.set_state(PresetForm.waiting_sleeve_length)
    await callback.message.edit_text("Выберите тип рукавов:", reply_markup=sleeve_length_keyboard())

@router.callback_query(F.data.startswith("form_sleeve:"), PresetForm.waiting_sleeve_length)
async def on_preset_sleeve_length(callback: CallbackQuery, state: FSMContext):
    length = callback.data.split(":")[1]
    if length == "skip":
        await state.update_data(sleeve_length=None)
    else:
        await state.update_data(sleeve_length=length)
    await state.set_state(PresetForm.waiting_length)
    text = "Выберите длину изделия. Текст: Внимание! если ваш продукт Костюм 2-к, 3-к то длину можно не указывать."
    await callback.message.edit_text(text, reply_markup=garment_length_with_custom_keyboard())

@router.callback_query(F.data == "garment_len:skip", PresetForm.waiting_length)
async def on_preset_length_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(length=None)
    await preset_ask_photo_type(callback.message, state)

@router.callback_query(F.data.startswith("garment_len:"), PresetForm.waiting_length)
async def on_preset_length_btn(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(length=val)
    await preset_ask_photo_type(callback.message, state)

@router.callback_query(F.data == "garment_len_custom", PresetForm.waiting_length)
async def on_preset_length_custom(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите длину изделия текстом:")

@router.message(PresetForm.waiting_length)
async def on_preset_length_text(message: Message, state: FSMContext):
    await state.update_data(length=message.text)
    await preset_ask_photo_type(message, state)

async def preset_ask_photo_type(message: Message, state: FSMContext):
    await state.set_state(PresetForm.waiting_photo_type)
    await message.answer("Выберите тип фотографии:", reply_markup=form_view_keyboard())

@router.callback_query(F.data.startswith("form_view:"), PresetForm.waiting_photo_type)
async def on_preset_photo_type(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(photo_type=val)
    
    data = await state.get_data()
    category = data.get("category")
    
    if category == "own_variant":
        # Сценарий 'Свой вариант ФОНА' - после ракурса сразу генерация
        await state.set_state(PresetForm.result_ready)
        from bot.keyboards import confirm_generation_keyboard
        await callback.message.edit_text("Все готово! Создать фото?", reply_markup=confirm_generation_keyboard())
    else:
        await state.set_state(PresetForm.waiting_pose)
        from bot.keyboards import pose_keyboard
        await callback.message.edit_text("Выберите позу:", reply_markup=pose_keyboard())

@router.callback_query(F.data.startswith("pose:"), PresetForm.waiting_pose)
async def on_preset_pose(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(pose=val)
    await state.set_state(PresetForm.waiting_angle)
    await callback.message.edit_text("Выберите ракурс фотографии:", reply_markup=angle_keyboard())

@router.callback_query(F.data.startswith("angle:"), PresetForm.waiting_angle)
async def on_preset_angle(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(angle=val)
    await state.set_state(PresetForm.waiting_season)
    await callback.message.edit_text("Выберите сезон:", reply_markup=plus_season_keyboard())

@router.callback_query(F.data.startswith("plus_season:"), PresetForm.waiting_season)
async def on_preset_season(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    if val == "skip":
        await state.update_data(season=None)
    else:
        await state.update_data(season=val)
    
    data = await state.get_data()
    category = data.get("category")
    
    if category and category.startswith("infographic"):
        await state.set_state(PresetForm.waiting_holiday)
        from bot.keyboards import info_holiday_keyboard
        await callback.message.edit_text("Выберите праздник:", reply_markup=info_holiday_keyboard())
    else:
        await state.set_state(PresetForm.waiting_quality)
        await callback.message.edit_text("Выберите формат (качество):", reply_markup=quality_keyboard_with_back())

@router.callback_query(F.data.startswith("info_holiday:"), PresetForm.waiting_holiday)
async def on_preset_holiday(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(holiday=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_info_load)
    from bot.keyboards import info_load_keyboard
    await callback.message.edit_text("Выберите нагруженность инфографики:", reply_markup=info_load_keyboard())

@router.callback_query(F.data.startswith("info_load:"), PresetForm.waiting_info_load)
async def on_preset_info_load(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(info_load=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_info_lang)
    from bot.keyboards import info_lang_keyboard
    await callback.message.edit_text("Выберите язык инфографики:", reply_markup=info_lang_keyboard())

@router.callback_query(F.data.startswith("info_lang:"), PresetForm.waiting_info_lang)
async def on_preset_info_lang(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(info_lang=None if val == "skip" else val)
    await state.set_state(PresetForm.waiting_adv1)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text("Введите Преимущество 1 (текстом) или пропустите:", reply_markup=skip_step_keyboard("adv1"))

@router.message(PresetForm.waiting_adv1)
async def on_preset_adv1_text(message: Message, state: FSMContext):
    await state.update_data(adv1=message.text)
    await state.set_state(PresetForm.waiting_adv2)
    from bot.keyboards import skip_step_keyboard
    await message.answer("Введите Преимущество 2 (текстом) или пропустите:", reply_markup=skip_step_keyboard("adv2"))

@router.callback_query(F.data == "adv1:skip", PresetForm.waiting_adv1)
async def on_preset_adv1_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(adv1=None)
    await state.set_state(PresetForm.waiting_adv2)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text("Введите Преимущество 2 (текстом) или пропустите:", reply_markup=skip_step_keyboard("adv2"))

@router.message(PresetForm.waiting_adv2)
async def on_preset_adv2_text(message: Message, state: FSMContext):
    await state.update_data(adv2=message.text)
    await state.set_state(PresetForm.waiting_adv3)
    from bot.keyboards import skip_step_keyboard
    await message.answer("Введите Преимущество 3 (текстом) или пропустите:", reply_markup=skip_step_keyboard("adv3"))

@router.callback_query(F.data == "adv2:skip", PresetForm.waiting_adv2)
async def on_preset_adv2_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(adv2=None)
    await state.set_state(PresetForm.waiting_adv3)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text("Введите Преимущество 3 (текстом) или пропустите:", reply_markup=skip_step_keyboard("adv3"))

@router.message(PresetForm.waiting_adv3)
async def on_preset_adv3_text(message: Message, state: FSMContext):
    await state.update_data(adv3=message.text)
    await state.set_state(PresetForm.waiting_extra_info)
    from bot.keyboards import skip_step_keyboard
    await message.answer("Введите ДОП ИНФОРМАЦИЮ (до 75 символов) или пропустите:", reply_markup=skip_step_keyboard("extra_info"))

@router.callback_query(F.data == "adv3:skip", PresetForm.waiting_adv3)
async def on_preset_adv3_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(adv3=None)
    await state.set_state(PresetForm.waiting_extra_info)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text("Введите ДОП ИНФОРМАЦИЮ (до 75 символов) или пропустите:", reply_markup=skip_step_keyboard("extra_info"))

@router.message(PresetForm.waiting_extra_info)
async def on_preset_extra_info_text(message: Message, state: FSMContext):
    await state.update_data(extra_info=message.text[:75])
    await state.set_state(PresetForm.waiting_quality)
    await message.answer("Выберите формат (качество):", reply_markup=quality_keyboard_with_back())

@router.callback_query(F.data == "extra_info:skip", PresetForm.waiting_extra_info)
async def on_preset_extra_info_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(extra_info=None)
    await state.set_state(PresetForm.waiting_quality)
    await callback.message.edit_text("Выберите формат (качество):", reply_markup=quality_keyboard_with_back())

@router.callback_query(F.data.startswith("quality:"), PresetForm.waiting_quality)
async def on_preset_quality(callback: CallbackQuery, state: FSMContext):
    val = callback.data.split(":")[1]
    await state.update_data(quality=val)
    await state.set_state(PresetForm.result_ready)
    await callback.message.edit_text("Подтвердите параметры и создайте фото:", reply_markup=confirm_generation_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_height)
async def on_back_to_body_type(callback: CallbackQuery, state: FSMContext, db: Database):
    data = await state.get_data()
    if data.get("category") == "child":
        await on_preset_pick(callback, db, state)
    else:
        await state.set_state(PresetForm.waiting_body_type)
        await callback.message.edit_text("Выберите телосложение или введите числом:")

@router.callback_query(F.data == "back_step", PresetForm.waiting_age)
async def on_back_to_height(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_height)
    await callback.message.edit_text("Введите рост модели в числах на пример 170.")

@router.callback_query(F.data == "back_step", PresetForm.waiting_pants_style)
async def on_back_to_age(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_age)
    await callback.message.edit_text("Введите возраст модели числом:")

@router.callback_query(F.data == "back_step", PresetForm.waiting_sleeve_length)
async def on_back_to_pants_style(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_pants_style)
    await callback.message.edit_text("Выберите тип кроя штанов:", reply_markup=pants_style_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_length)
async def on_back_to_sleeve_length(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_sleeve_length)
    await callback.message.edit_text("Выберите тип рукавов:", reply_markup=sleeve_length_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_photo_type)
async def on_back_to_length(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_length)
    text = "Выберите длину изделия. Текст: Внимание! если ваш продукт Костюм 2-к, 3-к то длину можно не указывать. Длину мы делаем кнопками как у нас ранее в разделе Свой вариант и кнопку нужно добавить свой вариант чтобы человек сам смог написать длину"
    await callback.message.edit_text(text, reply_markup=garment_length_with_custom_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_pose)
async def on_back_to_photo_type(callback: CallbackQuery, state: FSMContext):
    await preset_ask_photo_type(callback.message, state)

@router.callback_query(F.data == "back_step", PresetForm.waiting_angle)
async def on_back_to_pose(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_pose)
    await callback.message.edit_text("Выберите позу:", reply_markup=pose_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_season)
async def on_back_to_angle(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_angle)
    await callback.message.edit_text("Выберите ракурс фотографии:", reply_markup=angle_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_quality)
async def on_back_to_season(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_season)
    await callback.message.edit_text("Выберите сезон:", reply_markup=plus_season_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_holiday)
async def on_back_to_season_info(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_season)
    await callback.message.edit_text("Выберите сезон:", reply_markup=plus_season_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_info_load)
async def on_back_to_holiday(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_holiday)
    from bot.keyboards import info_holiday_keyboard
    await callback.message.edit_text("Выберите праздник:", reply_markup=info_holiday_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_info_lang)
async def on_back_to_info_load(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_info_load)
    from bot.keyboards import info_load_keyboard
    await callback.message.edit_text("Выберите нагруженность инфографики:", reply_markup=info_load_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_adv1)
async def on_back_to_info_lang(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_info_lang)
    from bot.keyboards import info_lang_keyboard
    await callback.message.edit_text("Выберите язык инфографики:", reply_markup=info_lang_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_adv2)
async def on_back_to_adv1(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_adv1)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text("Введите Преимущество 1 (текстом) или пропустите:", reply_markup=skip_step_keyboard("adv1"))

@router.callback_query(F.data == "back_step", PresetForm.waiting_adv3)
async def on_back_to_adv2(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_adv2)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text("Введите Преимущество 2 (текстом) или пропустите:", reply_markup=skip_step_keyboard("adv2"))

@router.callback_query(F.data == "back_step", PresetForm.waiting_extra_info)
async def on_back_to_adv3(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_adv3)
    from bot.keyboards import skip_step_keyboard
    await callback.message.edit_text("Введите Преимущество 3 (текстом) или пропустите:", reply_markup=skip_step_keyboard("adv3"))

@router.callback_query(F.data == "back_step", PresetForm.waiting_loc_group)
async def on_back_to_gender(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.set_state(PresetForm.waiting_gender)
    from bot.keyboards import random_gender_keyboard
    await callback.message.edit_text("Выберите пол модели:", reply_markup=random_gender_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_location)
async def on_back_to_loc_group(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_loc_group)
    from bot.keyboards import random_loc_group_keyboard
    await callback.message.edit_text("Где будет проходить съемка?", reply_markup=random_loc_group_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_model_size)
async def on_back_to_pose_info(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_pose)
    from bot.keyboards import pose_keyboard
    await callback.message.edit_text("Выберите позу:", reply_markup=pose_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_camera_dist)
async def on_back_to_photo_type_info(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_photo_type)
    from bot.keyboards import form_view_keyboard
    await callback.message.edit_text("Выберите ракурс фотографии:", reply_markup=form_view_keyboard())

@router.callback_query(F.data == "back_step", PresetForm.waiting_aspect)
async def on_back_to_camera_dist(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_camera_dist)
    from bot.keyboards import camera_distance_keyboard
    await callback.message.edit_text("Выберите ракурс (удаленность):", reply_markup=camera_distance_keyboard())

@router.callback_query(F.data == "form_generate")
async def on_form_generate(callback: CallbackQuery, state: FSMContext, db: Database):
    global active_generations
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    
    # Проверка техработ
    maint = await db.get_app_setting("maintenance")
    if maint == "1":
        await callback.answer("🛠 В боте техработы. Генерация временно недоступна.", show_alert=True)
        return

    async with active_generations_lock:
        if active_generations >= 20:
            await callback.answer(get_string("rate_limit", lang), show_alert=True)
            return
        active_generations += 1

    try:
        sub = await db.get_user_subscription(user_id)
        if not sub or sub[3] >= sub[2]:
            await callback.answer("Лимит фото на сегодня исчерпан или у вас нет активной подписки.", show_alert=True)
            return

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
                "{Пол модели}": data.get("gender") or "None",
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
                "{Присутствие человека на фото}": data.get("has_person") or "Yes",
            }
            
            final_prompt = base_prompt
            for k, v in replacements.items():
                final_prompt = final_prompt.replace(k, str(v))
            
            # Логика для детей (child)
            if category == "child":
                final_prompt = "Kid style, soft lighting, child model. " + final_prompt

            aspect = data.get("aspect") or data.get("form_aspect") or "3:4"
            final_prompt += f"\nResolution: {data.get('quality', 'hd').upper()}. Aspect: {aspect}."
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
            prompt += f"\nResolution: 4K. Aspect: {aspect}."
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
        
        keys = await db.list_api_keys()
        result_bytes = None
        for kid, token, active, priority, daily, total, last_reset, created, updated in keys:
            if not active: continue
            allowed, _ = await db.check_api_key_limits(kid)
            if not allowed: continue
            
            try:
                result_bytes = await generate_image(token, final_prompt, input_image_bytes, bg_image_bytes, "gemini-3-pro-image-preview")
                if result_bytes:
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
        await callback.answer("История пуста", show_alert=True)
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
    await _replace_with_text(callback, get_string("how_to", lang), reply_markup=back_main_keyboard(lang))

@router.callback_query(F.data == "menu_subscription")
async def on_sub_menu(callback: CallbackQuery, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    user_id = callback.from_user.id
    sub = await db.get_user_subscription(user_id)
    
    plans = await db.list_subscription_plans()
    
    if sub:
        plan_name, expires, limit, usage = sub
        rem = max(0, limit - usage)
        text = get_string("subscription_info_active", lang, plan=plan_name.upper(), expires=expires, usage=usage, limit=limit)
        await _replace_with_text(callback, text, reply_markup=plans_keyboard(plans, lang))
    else:
        await _replace_with_text(callback, get_string("subscription_info_none", lang), reply_markup=plans_keyboard(plans, lang))

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
    
    text = f"<b>💎 Тариф {name}</b>\n\n{desc}\n\n<b>Цена: {price} ₽</b>\n\nВы уверены, что хотите оформить подписку?"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_buy:{plan_id}")],
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
    
    await db.increment_user_balance(user_id, -await db.get_user_balance(user_id))
    await db.grant_subscription(user_id, plan_id, plan[1], plan[8], plan[9])
    
    await callback.answer("✅ Подписка успешно оформлена!", show_alert=True)
    await on_menu_profile(callback, db)
