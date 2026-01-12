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

from bot.db import Database
from bot.strings import get_string
from bot.keyboards import (
    terms_keyboard, main_menu_keyboard, profile_keyboard, 
    language_keyboard, marketplace_menu_keyboard, plans_keyboard,
    history_pagination_keyboard, aspect_ratio_keyboard,
    form_generate_keyboard, subscription_check_keyboard,
    back_main_keyboard
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

from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile, FSInputFile, BufferedInputFile
import os
import json

# ...

async def _send_model_photo(callback: CallbackQuery, photo_id: str, caption: str, reply_markup: InlineKeyboardMarkup):
    """Универсальная функция для отправки фото модели (file_id или локальный путь)"""
    try:
        if photo_id and (photo_id.startswith('data/uploads') or photo_id.startswith('C:')):
            if os.path.exists(photo_id):
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
async def on_menu_market(callback: CallbackQuery, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    # Получаем настройки включенных категорий и цены
    enabled = await db.get_all_app_settings()
    # Фильтруем только те, что относятся к категориям
    cat_status = {k: (v == "1") for k, v in enabled.items() if k in ["female", "male", "child", "storefront", "whitebg", "random", "own", "own_variant"]}
    
    # По ТЗ: "создать фото до 4 фотографий промт до 1тыщ символом" - это и есть основной флоу Маркетплейса
    # Но мы даем выбор категории
    await _replace_with_text(callback, "Выберите категорию:", reply_markup=create_product_keyboard_dynamic(cat_status))

@router.callback_query(F.data.startswith("create_cat:"))
async def on_create_cat(callback: CallbackQuery, db: Database):
    category = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)
    
    # Показываем первую модель в этой категории
    total = await db.count_models(category, "default")
    if total == 0:
        await callback.answer("В этой категории пока нет моделей", show_alert=True)
        return
        
    model = await db.get_model_by_index(category, "default", 0)
    kb = model_select_keyboard(category, "default", 0, total)
    
    await callback.message.delete()
    await _send_model_photo(callback, model[3], f"Модель: {model[1]} (1/{total})", kb)

@router.callback_query(F.data.startswith("model_nav:"))
async def on_model_nav(callback: CallbackQuery, db: Database):
    _, category, cloth, index = callback.data.split(":")
    index = int(index)
    total = await db.count_models(category, cloth)
    
    if index < 0: index = total - 1
    if index >= total: index = 0
    
    model = await db.get_model_by_index(category, cloth, index)
    kb = model_select_keyboard(category, cloth, index, total)
    
    await callback.message.delete()
    await _send_model_photo(callback, model[3], f"Модель: {model[1]} ({index+1}/{total})", kb)

@router.callback_query(F.data.startswith("model_pick:"))
async def on_model_pick(callback: CallbackQuery, db: Database, state: FSMContext):
    _, category, cloth, index = callback.data.split(":")
    model = await db.get_model_by_index(category, cloth, int(index))
    
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(CreateForm.waiting_market_photos)
    await state.update_data(photos=[], model_id=model[0], prompt_id=model[2], category=category)
    
    await callback.message.answer(get_string("upload_photo", lang), reply_markup=back_main_keyboard(lang))

@router.message(CreateForm.waiting_market_photos, F.photo)
async def on_market_photos(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    photos = data.get("photos", [])
    lang = await db.get_user_language(message.from_user.id)
    
    if len(photos) >= 4: return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    
    if len(photos) < 4:
        await message.answer(f"Фото {len(photos)}/4. Еще? Или введите описание:", 
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text="Далее", callback_data="market_photos_done")],
                                 [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_main")]
                             ]))
        else:
        await state.set_state(CreateForm.waiting_market_prompt)
        await message.answer(get_string("enter_prompt", lang))

@router.callback_query(F.data == "market_photos_done", CreateForm.waiting_market_photos)
async def on_market_photos_done(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await db.get_user_language(callback.from_user.id)
    await state.set_state(CreateForm.waiting_market_prompt)
    await callback.message.answer(get_string("enter_prompt", lang))

@router.message(CreateForm.waiting_market_prompt, F.text)
async def on_market_prompt(message: Message, state: FSMContext, db: Database):
    if len(message.text) > 1000: return
    await state.update_data(market_prompt=message.text)
    await state.set_state(CreateForm.waiting_market_advantage)
    await message.answer("Преимущество (до 100 симв):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="market_advantage_skip")]
    ]))

@router.message(CreateForm.waiting_market_advantage, F.text)
async def on_market_advantage(message: Message, state: FSMContext, db: Database):
    if len(message.text) > 100: return
    await state.update_data(market_advantage=message.text)
    await market_ask_aspect(message, state, db)

@router.callback_query(F.data == "market_advantage_skip", CreateForm.waiting_market_advantage)
async def on_market_advantage_skip(callback: CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(market_advantage="")
    await market_ask_aspect(callback.message, state, db)

async def market_ask_aspect(message: Message, state: FSMContext, db: Database):
    lang = await db.get_user_language(message.chat.id if hasattr(message, "chat") else message.from_user.id)
    await state.set_state(CreateForm.waiting_market_aspect)
    await message.answer(get_string("select_format", lang), reply_markup=aspect_ratio_keyboard(lang))

@router.callback_query(F.data.startswith("form_aspect:"), CreateForm.waiting_market_aspect)
async def on_aspect_set(callback: CallbackQuery, state: FSMContext, db: Database):
    aspect = callback.data.split(":")[1].replace("x", ":")
    await state.update_data(form_aspect=aspect)
    lang = await db.get_user_language(callback.from_user.id)
    await _replace_with_text(callback, "Подтвердите создание:", reply_markup=form_generate_keyboard(lang))

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
            await callback.answer("Лимит исчерпан или нет подписки", show_alert=True)
        return

    data = await state.get_data()
        prompt = data.get("market_prompt", "")
        if data.get("market_advantage"): prompt += f"\nAdvantage: {data['market_advantage']}"
        aspect = data.get("form_aspect", "3:4")
        prompt += f"\nResolution: 4K. Aspect: {aspect}."

        await _replace_with_text(callback, "Генерирую...", reply_markup=None)
        
        # 20. Key rotation
        keys = await db.list_api_keys()
    result_bytes = None
        for kid, token, active, priority, daily, total, last_reset, created, updated in keys:
            if not active: continue
            allowed, _ = await db.check_api_key_limits(kid)
            if not allowed: continue
            
            try:
                # В ТЗ: до 4 фотографий. Берем первую как основу.
                photos = data.get("photos", [])
                img_bytes = None
                if photos:
                    file = await callback.bot.get_file(photos[0])
                    f_bytes = await callback.bot.download_file(file.file_path)
                    img_bytes = f_bytes.read()
                
                result_bytes = await generate_image(token, prompt, img_bytes, None, "gemini-3-pro-image-preview")
            if result_bytes:
                    await db.record_api_usage(kid)
                break
                except Exception:
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
        
        await db.add_generation_history(pid, user_id, "market", json.dumps(data), json.dumps(data.get("photos", [])), "FILE_ID_MOCK")
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
    
    # Показываем описание плана перед покупкой
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
    
    # 12. При оформлении бонус сгорает
    await db.increment_user_balance(user_id, -await db.get_user_balance(user_id))
    
    # Выдаем подписку
    # plan structure: (id, name_ru, name_en, name_vi, desc_ru, desc_en, desc_vi, price, duration, limit, is_active)
    await db.grant_subscription(user_id, plan_id, plan[1], plan[8], plan[9])
    
    await callback.answer("✅ Подписка успешно оформлена!", show_alert=True)
    await on_menu_profile(callback, db)
