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
    waiting_market_photos = State()
    waiting_market_prompt = State()
    waiting_market_advantage = State()
    waiting_market_aspect = State()
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
    waiting_quality = State()
    result_ready = State()

# Глобальный счетчик активных генераций для rate limiting
active_generations = 0
active_generations_lock = asyncio.Lock()

async def check_user_subscription(user_id: int, bot: Bot) -> bool:
    """Проверяет подписку на обязательный канал"""
    channel_id = "-1002242395646" # ID канала из ТЗ
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

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
    
    # Регистрация пользователя
    await db.upsert_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    lang = await db.get_user_language(user_id)
    
    # 1. Обязательная подписка
    if not await check_user_subscription(user_id, bot):
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
    if await check_user_subscription(callback.from_user.id, bot):
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
    enabled = await db.get_all_app_settings()
    cat_status = {k: (v == "1") for k, v in enabled.items() if k in ["female", "male", "child", "storefront", "whitebg", "random", "own", "own_variant"]}
    
    # Текст с картинки 2: Обратите внимание...
    disclaimer = "Текст: обратите внимание внешность или другие параметры могут отличаться в зависимости от заданных параметров."
    await _replace_with_text(callback, disclaimer, reply_markup=create_product_keyboard_dynamic(cat_status))

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

@router.callback_query(F.data.startswith("preset_pick:"))
async def on_preset_pick(callback: CallbackQuery, db: Database, state: FSMContext):
    _, category, cloth, index = callback.data.split(":")
    model = await db.get_model_by_index(category, cloth, int(index))
    lang = await db.get_user_language(callback.from_user.id)
    
    await state.update_data(model_id=model[0], prompt_id=model[2], category=category, cloth=cloth)
    
    if category == "child":
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
    await state.update_data(pants_style=style)
    await state.set_state(PresetForm.waiting_sleeve_length)
    await callback.message.edit_text("Выберите тип рукавов:", reply_markup=sleeve_length_keyboard())

@router.callback_query(F.data.startswith("form_sleeve:"), PresetForm.waiting_sleeve_length)
async def on_preset_sleeve_length(callback: CallbackQuery, state: FSMContext):
    length = callback.data.split(":")[1]
    await state.update_data(sleeve_length=length)
    await state.set_state(PresetForm.waiting_length)
    text = "Выберите длину изделия. Текст: Внимание! если ваш продукт Костюм 2-к, 3-к то длину можно не указывать. Длину мы делаем кнопками как у нас ранее в разделе Свой вариант и кнопку нужно добавить свой вариант чтобы человек сам смог написать длину"
    await callback.message.edit_text(text, reply_markup=garment_length_with_custom_keyboard())

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
    await state.set_state(PresetForm.waiting_pose)
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
    await state.update_data(season=val)
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

@router.callback_query(F.data == "back_step", PresetForm.result_ready)
async def on_back_to_quality(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PresetForm.waiting_quality)
    await callback.message.edit_text("Выберите формат (качество):", reply_markup=quality_keyboard_with_back())

@router.callback_query(F.data == "form_generate")
async def on_form_generate(callback: CallbackQuery, state: FSMContext, db: Database):
    global active_generations
    user_id = callback.from_user.id
    lang = await db.get_user_language(user_id)
    
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
            
            async with aiosqlite.connect(db._db_path) as conn:
                async with conn.execute("SELECT text FROM prompts WHERE id=?", (prompt_id,)) as cur:
                    row = await cur.fetchone()
                    base_prompt = row[0] if row else ""
            
            params = []
            if data.get("body_type"): params.append(f"Body type: {data['body_type']}")
            if data.get("height"): params.append(f"Height: {data['height']}cm")
            if data.get("age"): params.append(f"Age: {data['age']}")
            if data.get("pants_style"): params.append(f"Pants style: {data['pants_style']}")
            if data.get("sleeve_length"): params.append(f"Sleeve: {data['sleeve_length']}")
            if data.get("length"): params.append(f"Length: {data['length']}")
            if data.get("photo_type"): params.append(f"View: {data['photo_type']}")
            if data.get("pose"): params.append(f"Pose: {data['pose']}")
            if data.get("angle"): params.append(f"Angle: {data['angle']}")
            if data.get("season"): params.append(f"Season: {data['season']}")
            
            final_prompt = base_prompt + "\nParameters:\n" + "\n".join(params)
            final_prompt += f"\nResolution: {data.get('quality', 'hd').upper()}."
            final_prompt += "\nBrand name: AI-ROOM."
            
            async with aiosqlite.connect(db._db_path) as conn:
                async with conn.execute("SELECT photo_file_id FROM models WHERE id=?", (model_id,)) as cur:
                    row = await cur.fetchone()
                    model_photo = row[0] if row else None
            
            input_image_bytes = None
            if model_photo:
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
            aspect = data.get("form_aspect", "3:4")
            prompt += f"\nResolution: 4K. Aspect: {aspect}."
            prompt += "\nBrand name: AI-ROOM."
            final_prompt = prompt
            
            photos = data.get("photos", [])
            input_image_bytes = None
            if photos:
                file = await callback.bot.get_file(photos[0])
                f_bytes = await callback.bot.download_file(file.file_path)
                input_image_bytes = f_bytes.read()

        await _replace_with_text(callback, get_string("generation_started", lang), reply_markup=None)
        
        keys = await db.list_api_keys()
        result_bytes = None
        for kid, token, active, priority, daily, total, last_reset, created, updated in keys:
            if not active: continue
            allowed, _ = await db.check_api_key_limits(kid)
            if not allowed: continue
            
            try:
                result_bytes = await generate_image(token, final_prompt, input_image_bytes, None, "gemini-3-pro-image-preview")
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
