from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.types import BufferedInputFile
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from bot.keyboards import (
    terms_keyboard,
    main_menu_keyboard,
    profile_keyboard,
    settings_keyboard,
    language_keyboard,
    marketplace_menu_keyboard,
    plans_keyboard,
    balance_keyboard,
    referral_keyboard,
    withdraw_keyboard,
    quality_keyboard,
    subscription_check_keyboard,
    create_product_keyboard,
    create_product_keyboard_dynamic,
    female_mode_keyboard,
    female_clothes_keyboard,
    male_mode_keyboard,
    male_clothes_keyboard,
    boy_mode_keyboard,
    boy_clothes_keyboard,
    girl_mode_keyboard,
    girl_clothes_keyboard,
    back_main_keyboard,
    model_select_keyboard,
    form_age_keyboard,
    form_size_keyboard,
    form_length_skip_keyboard,
    own_variant_length_skip_keyboard,
    form_view_keyboard,
    whitebg_view_keyboard,
    confirm_generation_keyboard,
    result_actions_keyboard,
    result_actions_own_keyboard,
    pants_style_keyboard,
    aspect_ratio_keyboard,
    sleeve_length_keyboard,
    random_gender_keyboard,
    random_loc_group_keyboard,
    random_location_keyboard,
    random_vibe_keyboard,
    random_decor_keyboard,
    random_skip_keyboard,
    random_shot_keyboard,
    plus_location_keyboard,
    plus_season_keyboard,
    plus_vibe_keyboard,
    plus_gender_keyboard,
    cut_type_keyboard,
    garment_length_keyboard,
    own_variant_category_keyboard,
    own_variant_male_subcategory_keyboard,
    own_variant_female_subcategory_keyboard,
    own_variant_boy_subcategory_keyboard,
    own_variant_girl_subcategory_keyboard,
    own_variant_subcategory_items_keyboard,
    own_variant_product_view_keyboard,
)
from bot.db import Database
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.config import load_settings
from bot.gemini import generate_image, generate_text
import asyncio
from aiogram.enums import ChatAction
import logging
import aiosqlite

logger = logging.getLogger(__name__)


router = Router()


class CreateForm(StatesGroup):
    waiting_age = State()
    waiting_child_gender = State()
    waiting_size = State()
    waiting_height = State()
    waiting_length = State()
    waiting_view = State()
    waiting_aspect = State()
    waiting_sleeve = State()
    waiting_foot = State()
    waiting_edit_text = State()
    result_ready = State()
    # Random mode custom steps reuse existing where possible
    random_mode = State()
    random_dummy = State()
    waiting_custom_location = State()
    # Own flow
    own_mode = State()
    waiting_ref_photo = State()
    waiting_product_photo = State()
    waiting_own_view = State()
    waiting_own_size = State()
    waiting_own_length = State()
    waiting_own_sleeve = State()
    waiting_own_cut = State()
    # Own Variant flow
    waiting_own_variant_photo1 = State()
    waiting_own_variant_photo2 = State()
    waiting_own_variant_length = State()
    waiting_own_variant_sleeve = State()
    waiting_own_variant_product_type = State()
    waiting_own_variant_view = State()
    plus_loc = State()
    waiting_photos = State()
    waiting_product_photos = State()
    plus_season = State()
    plus_vibe = State()
    category = State()
    cloth = State()
    index = State()
    model_id = State()
    prompt_id = State()
    # Marketplace flows
    waiting_product_photos = State() # Для загрузки до 3-4 фото

WELCOME_TEXT = (
    "Добро пожаловать в AI-ROOM — пространство, где вы можете генерировать любые "
    "изображения и воплощать свои идеи в реальность.\n\n"
    "Чтобы вы могли подробнее познакомиться с нашим ботом, **мы дарим 4 бесплатных токена.**\n"
    "1 токен = 30 рублей.\n\n"
    "Также приглашаем вас принять участие в нашей реферальной программе — вы сможете зарабатывать "
    "до 20% с каждого пополнения ваших рефералов.\n"
    "Выплаты производятся один раз в месяц."
)


async def check_user_subscription(user_id: int, bot: Bot) -> bool:
    """Проверяет подписку на обязательный канал"""
    # В ТЗ ссылка: https://t.me/+fOA5fiDstVdlMzIy
    # ID канала: -1002242395646 (пример)
    try:
        member = await bot.get_chat_member(chat_id="-1002242395646", user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        # Если не удалось проверить, считаем что не подписан
        return False

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
    except TelegramBadRequest as e:
        logger.warning(f"[_replace_with_text] TelegramBadRequest при редактировании: {e}")
        try:
            await callback.message.answer(text, reply_markup=reply_markup)
        except TelegramBadRequest as e2:
            logger.error(f"[_replace_with_text] TelegramBadRequest при отправке нового сообщения: {e2}")
            pass
    except TelegramRetryAfter:
        # Фолбэк при флуд-контроле TG — отправляем новое сообщение вместо редактирования
        try:
            await callback.message.answer(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"[_replace_with_text] Ошибка при отправке нового сообщения после RetryAfter: {e}")
            pass


async def _run_generation_progress(bot, chat_id: int, message_id: int, stop_event: asyncio.Event) -> None:
    """Красивая анимация прогресса генерации с прогресс-баром"""
    import time
    start_time = time.time()
    
    # Шаги генерации
    steps = [
        "Анализ изображения",
        "Обработка данных",
        "Генерация модели",
        "Создание композиции",
        "Финальная обработка"
    ]
    
    total_steps = len(steps)
    current_step = 0
    
    # Эмодзи для прогресс-бара
    filled = "🟩"
    empty = "⬜️"
    bar_length = 10
    
    while not stop_event.is_set():
        elapsed = int(time.time() - start_time)
        
        # Вычисляем прогресс (от 0 до 100%)
        # Имитируем прогресс: первые 20% быстро, потом медленнее
        if elapsed < 3:
            progress = min(20, elapsed * 7)
            current_step = 0
        elif elapsed < 8:
            progress = min(40, 20 + (elapsed - 3) * 4)
            current_step = 1
        elif elapsed < 15:
            progress = min(65, 40 + (elapsed - 8) * 3.5)
            current_step = 2
        elif elapsed < 25:
            progress = min(85, 65 + (elapsed - 15) * 2)
            current_step = 3
        else:
            progress = min(95, 85 + (elapsed - 25) * 0.5)
            current_step = 4
        
        # Строим прогресс-бар
        filled_count = int(bar_length * progress / 100)
        progress_bar = filled * filled_count + empty * (bar_length - filled_count)
        
        # Формируем текст
        step_text = steps[current_step] if current_step < total_steps else steps[-1]
        progress_text = f"{int(progress)}%"
        
        message = (
            f"✏️ Редактирование\n\n"
            f"Понимаю, что изменить\n\n"
            f"{progress_bar} {progress_text}\n\n"
            f"Прошло: {elapsed}с • Шаг {current_step + 1}/{total_steps}\n\n"
            f"Результат вас приятно удивит"
        )
        
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message)
        except TelegramBadRequest:
            pass
        except TelegramRetryAfter:
            pass
        except Exception:
            pass
        
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=1.5)
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
async def on_child_gender(callback: CallbackQuery, state: FSMContext) -> None:
    gender_key = callback.data.split(":", 1)[1]
    await state.update_data(gender=("мальчик" if gender_key == "boy" else "девочка"))
    await _replace_with_text(callback, "Введите рост ребенка в см (например: 130):")
    await state.set_state(CreateForm.waiting_height)
    await _safe_answer(callback)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    # Обработка реферальной ссылки: /start ref_12345
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
            if referrer_id == message.from_user.id:
                referrer_id = None
        except ValueError:
            pass

    user = message.from_user
    is_new = not await db.user_exists(user.id)
    
    await db.upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        referrer_id=referrer_id if is_new else None
    )
    
    # Начисляем бонус только новым пользователям
    if is_new:
        await db.increment_user_balance(user.id, 4)
        await db.add_transaction(user.id, 4, "bonus", "Welcome bonus")
        logger.info(f"[cmd_start] Новому пользователю {user.id} начислен бонус 4 токена")
        bonus_text = "\n\n🎁 Вам начислен бонус: 4 токена!"
    else:
        bonus_text = ""
    
    await state.clear()
    
    # Проверка подписки (закомментировал до установки реального ID канала)
    # if not await check_user_subscription(user.id, bot):
    #     await message.answer(
    #         "Для использования бота необходимо подписаться на наш канал!",
    #         reply_markup=subscription_check_keyboard("https://t.me/+fOA5fiDstVdlMzIy")
    #     )
    #     return

    async with aiosqlite.connect(db._db_path) as conn:
        async with conn.execute("SELECT accepted_terms FROM users WHERE id=?", (user.id,)) as cur:
            row = await cur.fetchone()
            accepted = bool(row[0]) if row else False
    
    if not accepted:
        await message.answer(WELCOME_TEXT + bonus_text, reply_markup=terms_keyboard())
    else:
        await message.answer("🎯 Главное меню:", reply_markup=main_menu_keyboard())


@router.message(F.text == "/reset")
async def cmd_reset(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔄 Состояние сброшено. Главное меню:", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "check_subscription")
async def on_check_subscription(callback: CallbackQuery, bot: Bot, db: Database):
    if await check_user_subscription(callback.from_user.id, bot):
        await callback.message.answer("✅ Подписка подтверждена! Главное меню:", reply_markup=main_menu_keyboard())
        await callback.answer()
    else:
        await callback.answer("❌ Вы всё еще не подписаны на канал!", show_alert=True)


@router.callback_query(F.data == "menu_market")
async def on_menu_market(callback: CallbackQuery):
    await _replace_with_text(callback, "📦 Раздел для маркетплейсов:", reply_markup=marketplace_menu_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "menu_profile")
async def on_menu_profile(callback: CallbackQuery, db: Database):
    balance = await db.get_user_balance(callback.from_user.id)
    sub = await db.get_user_subscription(callback.from_user.id)
    if sub:
        plan, expires, limit, usage = sub
        sub_text = f"Подписка: {plan.upper()}\nДо {expires}\nЛимит: {usage}/{limit} фото в день"
    else:
        sub_text = "Подписка: отсутствует"
    
    text = f"👤 Профиль\n\n🆔 Ваш ID: {callback.from_user.id}\n💰 Баланс: {balance} токенов\n\n{sub_text}"
    await _replace_with_text(callback, text, reply_markup=profile_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "menu_settings")
async def on_menu_settings(callback: CallbackQuery):
    await _replace_with_text(callback, "⚙️ Настройки:", reply_markup=settings_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "settings_lang")
async def on_settings_lang(callback: CallbackQuery):
    await _replace_with_text(callback, "Выберите язык / Choose language:", reply_markup=language_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("lang:"))
async def on_lang_set(callback: CallbackQuery, db: Database):
    lang = callback.data.split(":")[1]
    await db.set_user_language(callback.from_user.id, lang)
    await _safe_answer(callback, f"Язык изменен на {lang.upper()}", show_alert=True)
    await on_menu_settings(callback)


@router.callback_query(F.data == "menu_balance")
async def on_menu_balance(callback: CallbackQuery, db: Database):
    balance = await db.get_user_balance(callback.from_user.id)
    text = f"💰 Ваш баланс: {balance} токенов\n\n1 токен = 30 руб.\nВыберите пакет токенов:"
    await _replace_with_text(callback, text, reply_markup=balance_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "menu_subscription")
async def on_menu_subscription(callback: CallbackQuery):
    text = (
        "Выберите тарифный план:\n\n"
        "🔹 Тариф 2 ДНЯ — 649 ₽\n"
        "Доступ на 48 часов, до 15 фото в день.\n\n"
        "🔹 Тариф 7 ДНЕЙ — 1990 ₽\n"
        "Доступ на неделю, до 12 фото в день.\n\n"
        "🔹 Тариф PRO — 5490 ₽\n"
        "Полный доступ на 30 дней, до 35 фото в день.\n\n"
        "🔋 Тариф MAX — 9990 ₽\n"
        "До 60 фото в день.\n\n"
        "🔥 Тариф ULTRA 4K — 15990 ₽\n"
        "До 25 фото в день, разрешение 4K."
    )
    await _replace_with_text(callback, text, reply_markup=plans_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "menu_referral")
async def on_menu_referral(callback: CallbackQuery, db: Database):
    count, earned = await db.get_referral_stats(callback.from_user.id)
    text = (
        f"🤝 Реферальная программа\n\n"
        f"Приглашайте друзей и получайте 20% от их пополнений!\n\n"
        f"📊 Ваша статистика:\n"
        f"Приглашено друзей: {count}\n"
        f"Заработано: {earned} руб.\n\n"
        f"Минимальная сумма вывода: 1000 руб."
    )
    await _replace_with_text(callback, text, reply_markup=referral_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "ref_invite")
async def on_ref_invite(callback: CallbackQuery):
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{callback.from_user.id}"
    await callback.message.answer(f"Ваша реферальная ссылка:\n`{ref_link}`", parse_mode="Markdown")
    await _safe_answer(callback)


@router.callback_query(F.data == "menu_history")
async def on_menu_history(callback: CallbackQuery, db: Database):
    gens = await db.list_user_generations(callback.from_user.id)
    if not gens:
        await _safe_answer(callback, "У вас еще нет генераций", show_alert=True)
        return
    
    text = "Последние 20 генераций:\n\n"
    for pid, photo_id, date in gens:
        text += f"🔹 PID: `{pid}` | {date}\n"
    
    await callback.message.answer(text, parse_mode="Markdown")
    await _safe_answer(callback)


@router.callback_query(F.data == "accept_terms")
async def on_accept_terms(callback: CallbackQuery, db: Database) -> None:
    await db.set_terms_acceptance(callback.from_user.id, True)
    await callback.message.answer("🎯 Главное меню:", reply_markup=main_menu_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "back_main")
async def on_back_main(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    text = "🎯 Главное меню:"
    # Если на экране результат (фото), не редактируем/не удаляем, а отправляем новое сообщение
    if current == CreateForm.result_ready.state:
        await callback.message.answer(text, reply_markup=main_menu_keyboard())
        await state.clear()
        await _safe_answer(callback)
        return
    await state.clear()
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=main_menu_keyboard())
    await _safe_answer(callback)

@router.callback_query(F.data == "menu_create")
async def on_create_photo(callback: CallbackQuery, db: Database) -> None:
    # Техработы: блокируем для не-админов
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    balance = await db.get_user_balance(callback.from_user.id)
    # Блокировка пользователя
    if await db.get_user_blocked(callback.from_user.id):
        await _safe_answer(callback, "Ваш доступ ограничен. Обратитесь в поддержку.", show_alert=True)
        return
    if balance <= 0:
        await _safe_answer(callback, "Недостаточно генераций для создания фото.", show_alert=True)
        return
    text = "Выберите пожалуйста какой продукт вы хотите создать?"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    # динамически скрываем отключённые категории
    try:
        statuses = await db.list_categories_enabled()
        if not any(statuses.values()):
            await _replace_with_text(
                callback,
                "Категории временно недоступны. Пожалуйста, попробуйте позже или свяжитесь с поддержкой.",
                reply_markup=back_main_keyboard(),
            )
        else:
            prices = await db.list_category_prices()
            await _replace_with_text(callback, text, reply_markup=create_product_keyboard_dynamic(statuses, prices))
    except Exception:
        # на случай отсутствия настроек — показать стандартное меню
        try:
            prices = await db.list_category_prices()
        except Exception:
            prices = None
        await _replace_with_text(callback, text, reply_markup=create_product_keyboard(prices))
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
    await state.update_data(random_mode=True)
    await _replace_with_text(callback, "Выберите пол модели:", reply_markup=random_gender_keyboard())
    await _safe_answer(callback)


# Own flow (reference + product)
@router.callback_query(F.data == "create_own")
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
    text = (
        "Пришлите фото, которое вам нравится.\n\n"
        "Бот проанализирует модель, позу, свет и фон, чтобы создать похожее изображение с вашим товаром.\n\n"
        "Нужно понимать, что эта функция не создаёт точную копию человека или фона. Похожесть составляет примерно 50–60%. Если вы ожидаете 100% совпадения, возврат средств в таких ситуациях не предусмотрен.\n\n"
        "За исключением несходства вашей одежды"
    )
    await _replace_with_text(callback, text)
    await state.set_state(CreateForm.waiting_ref_photo)
    await _safe_answer(callback)


# Own Variant flow (2 photos: model + clothing)
@router.callback_query(F.data == "create_own_variant")
async def on_create_own_variant(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    # Техработы: блокируем для не-админов
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    # Категория может быть выключена в админке
    if not await db.get_category_enabled("own_variant"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    await state.clear()
    await state.update_data(own_variant_mode=True)
    text = (
        "✨ Свой вариант\n\n"
        "Шаг 1/2: Пришлите фото модели (поза, фон, освещение).\n\n"
        "Это фото будет использовано как референс для модели, позы, освещения и фона."
    )
    await _replace_with_text(callback, text, reply_markup=back_main_keyboard())
    await state.set_state(CreateForm.waiting_own_variant_photo1)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_own_variant_photo1, F.photo)
async def on_own_variant_photo1(message: Message, state: FSMContext) -> None:
    photo1_id = message.photo[-1].file_id
    await state.update_data(own_variant_photo1_id=photo1_id)
    await state.set_state(CreateForm.waiting_own_variant_photo2)
    await message.answer(
        "Шаг 2/2: Пришлите фото одежды.\n\n"
        "Это фото будет использовано для воспроизведения одежды на модели.",
        reply_markup=back_main_keyboard()
    )


@router.message(CreateForm.waiting_own_variant_photo2, F.photo)
async def on_own_variant_photo2(message: Message, state: FSMContext) -> None:
    photo2_id = message.photo[-1].file_id
    await state.update_data(own_variant_photo2_id=photo2_id)
    await state.set_state(CreateForm.waiting_own_variant_length)
    # Отправляем изображение-гайд для выбора длины
    import os
    # Путь к изображению: в корне проекта или в /app (для Docker)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # Проверяем разные варианты путей
    image_paths = [
        os.path.join(project_root, "WhatsApp Image 2025-11-25 at 00.40.21.jpeg"),  # Локально
        "/app/garment_length_guide.jpeg",  # В Docker (переименованный файл)
        "/app/WhatsApp Image 2025-11-25 at 00.40.21.jpeg",  # В Docker (оригинальное имя)
    ]
    
    image_file_path = None
    for path in image_paths:
        if os.path.exists(path):
            image_file_path = path
            break
    
    # Маппинг для длины изделия
    length_map = {
        "short_top": "Короткий топ",
        "regular_top": "Обычный топ",
        "to_waist": "До талии",
        "below_waist": "Ниже талии",
        "mid_thigh": "До середины бедра",
        "to_knees": "До колен",
        "below_knees": "Ниже колен",
        "midi": "Миди",
        "to_ankles": "До щиколоток",
        "to_floor": "До пола",
    }
    
    if image_file_path:
        try:
            with open(image_file_path, "rb") as f:
                photo_file = BufferedInputFile(f.read(), filename="garment_length_guide.jpeg")
                await message.answer_photo(
                    photo=photo_file,
                    caption="📏 Выберите длину изделия:",
                    reply_markup=garment_length_keyboard()
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке изображения-гайда: {e}")
            await message.answer(
                "📏 Выберите длину изделия:",
                reply_markup=garment_length_keyboard()
            )
    else:
        # Если файл не найден, отправляем текстовое сообщение
        await message.answer(
            "📏 Выберите длину изделия:",
            reply_markup=garment_length_keyboard()
        )


@router.callback_query(CreateForm.waiting_own_variant_length, F.data.startswith("garment_len:"))
async def on_own_variant_length_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик выбора длины изделия через клавиатуру для 'Свой вариант'"""
    data = await state.get_data()
    # Проверяем, что это действительно "Свой вариант"
    if not data.get("own_variant_mode"):
        await _safe_answer(callback)
        return
    
    length_val = callback.data.split(":", 1)[1]
    length_map = {
        "short_top": "Короткий топ",
        "regular_top": "Обычный топ",
        "to_waist": "До талии",
        "below_waist": "Ниже талии",
        "mid_thigh": "До середины бедра",
        "to_knees": "До колен",
        "below_knees": "Ниже колен",
        "midi": "Миди",
        "to_ankles": "До щиколоток",
        "to_floor": "До пола",
    }
    length_text = length_map.get(length_val, length_val)
    await state.update_data(own_variant_length=length_text)
    
    # Проверяем, что длина действительно сохранилась
    verify_data = await state.get_data()
    saved_length = verify_data.get("own_variant_length", "")
    logger.info(f"[on_own_variant_length_callback] Сохранена длина изделия: '{length_text}'")
    logger.info(f"[on_own_variant_length_callback] Проверка сохранения: в состоянии = '{saved_length}' (совпадает: {saved_length == length_text})")
    
    if saved_length != length_text:
        logger.error(f"[on_own_variant_length_callback] ОШИБКА: Длина не сохранилась правильно! Ожидалось: '{length_text}', получено: '{saved_length}'")
    
    await state.set_state(CreateForm.waiting_own_variant_sleeve)
    await _replace_with_text(callback, "👕 Выберите длину рукавов:", reply_markup=sleeve_length_keyboard())
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_own_variant_length, F.data == "own_variant_length:skip")
async def on_own_variant_length_skip(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик пропуска длины изделия для 'Свой вариант'"""
    data = await state.get_data()
    # Проверяем, что это действительно "Свой вариант"
    if not data.get("own_variant_mode"):
        await _safe_answer(callback)
        return
    await state.update_data(own_variant_length="")
    await state.set_state(CreateForm.waiting_own_variant_sleeve)
    await _replace_with_text(callback, "👕 Выберите длину рукавов:", reply_markup=sleeve_length_keyboard())
    await _safe_answer(callback)

@router.message(CreateForm.waiting_own_variant_length)
async def on_own_variant_length(message: Message, state: FSMContext) -> None:
    """Обработчик текстового ввода длины изделия для 'Свой вариант' (fallback)"""
    length_text = (message.text or "").strip()
    if not length_text:
        await message.answer("Пожалуйста, укажите длину изделия словами (например: до талии, до колен, миди и т.д.) или выберите из предложенных вариантов")
        return
    
    # Сохраняем введенную длину как есть (пользователь пишет словами)
    await state.update_data(own_variant_length=length_text)
    await state.set_state(CreateForm.waiting_own_variant_sleeve)
    await message.answer(
        "👕 Выберите длину рукавов:",
        reply_markup=sleeve_length_keyboard()
    )


@router.callback_query(CreateForm.waiting_own_variant_sleeve, F.data.startswith("form_sleeve:"))
async def on_own_variant_sleeve(callback: CallbackQuery, state: FSMContext) -> None:
    val = callback.data.split(":", 1)[1]
    sleeve_map = {
        "normal": "Обычный",
        "long": "Длинные",
        "three_quarter": "Три четверти",
        "elbow": "До локтей",
        "short": "Короткие",
        "none": "Без рукав",
        "skip": None,
    }
    if val != "skip":
        await state.update_data(own_variant_sleeve=sleeve_map.get(val, val))
    await state.set_state(CreateForm.waiting_own_variant_product_type)
    await _replace_with_text(
        callback,
        "👕 Что вы хотите сделать? Выберите категорию товара:",
        reply_markup=own_variant_category_keyboard()
    )
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_own_variant_product_type, F.data.startswith("own_variant_cat:"))
async def on_own_variant_category(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик выбора категории товара"""
    category = callback.data.split(":", 1)[1]
    logger.info(f"[on_own_variant_category] Выбрана категория: {category}")
    
    # Сохраняем категорию и явно устанавливаем состояние
    await state.update_data(own_variant_category=category)
    await state.set_state(CreateForm.waiting_own_variant_product_type)
    
    # Проверяем состояние после установки
    current_state = await state.get_state()
    logger.info(f"[on_own_variant_category] Состояние после установки: {current_state}")
    
    if category == "male":
        await _replace_with_text(callback, "👨 Выберите подкатегорию:", reply_markup=own_variant_male_subcategory_keyboard())
    elif category == "female":
        await _replace_with_text(callback, "👱‍♀️ Выберите подкатегорию:", reply_markup=own_variant_female_subcategory_keyboard())
    elif category == "boy":
        await _replace_with_text(callback, "👦 Выберите подкатегорию:", reply_markup=own_variant_boy_subcategory_keyboard())
    elif category == "girl":
        await _replace_with_text(callback, "👧 Выберите подкатегорию:", reply_markup=own_variant_girl_subcategory_keyboard())
    elif category == "other":
        await state.update_data(own_variant_product_type="Другое")
        # Переходим к выбору части товара на фото
        await state.set_state(CreateForm.waiting_own_variant_view)
        await _replace_with_text(
            callback,
            "✅ Тип изделия: Другое\n\n📸 Укажите, какая часть товара на фото:",
            reply_markup=own_variant_product_view_keyboard()
        )
    await _safe_answer(callback)


# Обработчик без фильтра состояния - будет работать всегда, но проверяет режим "Свой вариант"
@router.callback_query(F.data.startswith("own_variant_subcat:"))
async def on_own_variant_subcategory(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик выбора подкатегории"""
    logger.info(f"[on_own_variant_subcategory] Получен callback: {callback.data}")
    
    # Проверяем, что это действительно "Свой вариант"
    data = await state.get_data()
    if not data.get("own_variant_mode"):
        logger.warning(f"[on_own_variant_subcategory] Это не режим 'Свой вариант', игнорируем")
        await _safe_answer(callback)
        return
    
    current_state = await state.get_state()
    logger.info(f"[on_own_variant_subcategory] Текущее состояние: {current_state}")
    
    # Устанавливаем правильное состояние, если оно не установлено
    if current_state != CreateForm.waiting_own_variant_product_type:
        logger.info(f"[on_own_variant_subcategory] Устанавливаем состояние waiting_own_variant_product_type")
        await state.set_state(CreateForm.waiting_own_variant_product_type)
    
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        logger.error(f"[on_own_variant_subcategory] Неверный формат данных: {callback.data}")
        await _safe_answer(callback, "Ошибка: неверный формат данных", show_alert=True)
        return
    
    category = parts[1]
    subcategory = parts[2]
    logger.info(f"[on_own_variant_subcategory] Категория: {category}, Подкатегория: {subcategory}")
    
    # Сохраняем категорию и подкатегорию
    await state.update_data(own_variant_category=category, own_variant_subcategory=subcategory)
    
    # Если выбрано "Другое", сохраняем тип изделия и переходим к выбору части товара
    if subcategory == "other":
        category_names = {
            "male": "Мужская",
            "female": "Женская",
            "boy": "Мальчик",
            "girl": "Девочка",
        }
        category_name = category_names.get(category, "")
        product_type = f"{category_name}, Другое" if category_name else "Другое"
        await state.update_data(own_variant_product_type=product_type)
        # Переходим к выбору части товара на фото
        await state.set_state(CreateForm.waiting_own_variant_view)
        await _replace_with_text(
            callback,
            f"✅ Тип изделия: {product_type}\n\n📸 Укажите, какая часть товара на фото:",
            reply_markup=own_variant_product_view_keyboard()
        )
    else:
        # Показываем конкретные товары для выбранной подкатегории
        logger.info(f"[on_own_variant_subcategory] Показываем товары для категории {category}, подкатегории {subcategory}")
        try:
            keyboard = own_variant_subcategory_items_keyboard(category, subcategory)
            logger.info(f"[on_own_variant_subcategory] Создана клавиатура с {len(keyboard.inline_keyboard)} строками")
            if not keyboard.inline_keyboard or len(keyboard.inline_keyboard) == 0:
                logger.error(f"[on_own_variant_subcategory] Клавиатура пустая для категории {category}, подкатегории {subcategory}")
                await _safe_answer(callback, "Ошибка: не найдены товары для этой подкатегории", show_alert=True)
                return
            
            # Сначала отвечаем на callback, чтобы убрать индикатор загрузки
            await _safe_answer(callback)
            
            # Затем обновляем сообщение
            try:
                await _replace_with_text(
                    callback,
                    f"Выберите конкретный товар:",
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"[on_own_variant_subcategory] Ошибка при обновлении сообщения: {e}", exc_info=True)
                # Пробуем отправить новое сообщение
                try:
                    await callback.message.answer(
                        f"Выберите конкретный товар:",
                        reply_markup=keyboard
                    )
                except Exception as e2:
                    logger.error(f"[on_own_variant_subcategory] Ошибка при отправке нового сообщения: {e2}", exc_info=True)
                    await _safe_answer(callback, f"Ошибка: {str(e2)}", show_alert=True)
        except Exception as e:
            logger.error(f"[on_own_variant_subcategory] Ошибка при создании клавиатуры: {e}", exc_info=True)
            await _safe_answer(callback, f"Ошибка: {str(e)}", show_alert=True)
            return
    
    # Если это не "Другое", callback уже был обработан выше
    if subcategory != "other":
        return
    
    # Для "Другое" отвечаем на callback здесь
    try:
        await _safe_answer(callback)
    except Exception as e:
        logger.error(f"[on_own_variant_subcategory] Ошибка при ответе на callback: {e}", exc_info=True)


@router.callback_query(CreateForm.waiting_own_variant_product_type, F.data == "own_variant_subcat_back")
async def on_own_variant_subcategory_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик возврата к выбору подкатегории"""
    data = await state.get_data()
    category = data.get("own_variant_category", "")
    
    # Показываем подкатегории для выбранной категории
    if category == "male":
        await _replace_with_text(callback, "👨 Выберите подкатегорию:", reply_markup=own_variant_male_subcategory_keyboard())
    elif category == "female":
        await _replace_with_text(callback, "👱‍♀️ Выберите подкатегорию:", reply_markup=own_variant_female_subcategory_keyboard())
    elif category == "boy":
        await _replace_with_text(callback, "👦 Выберите подкатегорию:", reply_markup=own_variant_boy_subcategory_keyboard())
    elif category == "girl":
        await _replace_with_text(callback, "👧 Выберите подкатегорию:", reply_markup=own_variant_girl_subcategory_keyboard())
    else:
        # Если категория не найдена, возвращаемся к выбору категории
        await _replace_with_text(
            callback,
            "👕 Что вы хотите сделать? Выберите категорию товара:",
            reply_markup=own_variant_category_keyboard()
        )
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_own_variant_product_type, F.data.startswith("own_variant_item:"))
async def on_own_variant_item(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик выбора конкретного товара"""
    # Разбираем callback_data
    parts = callback.data.split(":", 3)
    if len(parts) < 4:
        await _safe_answer(callback, "Ошибка: неверный формат данных", show_alert=True)
        return
    
    category = parts[1]
    subcategory = parts[2]
    item_index_str = parts[3]
    
    # Получаем данные из состояния для проверки
    data = await state.get_data()
    # Если категория не передана в callback_data, берем из состояния
    if not category or category == "":
        category = data.get("own_variant_category", "")
    
    # Получаем список товаров для данной подкатегории
    from bot.keyboards import get_own_variant_items_map
    items_map = get_own_variant_items_map()
    items = items_map.get((category, subcategory), [])
    
    # Преобразуем индекс в число
    try:
        item_index = int(item_index_str)
        if item_index == -1:
            item = "Другое"
        elif 0 <= item_index < len(items):
            item = items[item_index]
        else:
            logger.error(f"[on_own_variant_item] Неверный индекс товара: {item_index} для списка длиной {len(items)}")
            await _safe_answer(callback, "Ошибка: неверный индекс товара", show_alert=True)
            return
    except ValueError:
        logger.error(f"[on_own_variant_item] Не удалось преобразовать индекс в число: {item_index_str}")
        await _safe_answer(callback, "Ошибка: неверный формат индекса", show_alert=True)
        return
    
    # Получаем данные из состояния для проверки
    data = await state.get_data()
    # Если категория не передана в callback_data, берем из состояния
    if not category or category == "":
        category = data.get("own_variant_category", "")
    
    # Формируем полное описание типа изделия
    category_names = {
        "male": "Мужская",
        "female": "Женская",
        "boy": "Мальчик",
        "girl": "Девочка",
    }
    
    subcategory_names = {
        "outerwear": "Верхняя одежда",
        "top": "Одежда для верха",
        "bottom": "Одежда для низа",
        "underwear": "Нижнее бельё",
        "sport": "Спортивная одежда",
        "sleepwear": "Одежда для сна",
        "swimwear": "Плавание",
        "shoes": "Обувь",
        "accessories": "Аксессуары",
        "socks": "Носки",
        "dresses": "Платья и комбинезоны" if category == "female" else "Платья и сарафаны",
        "other": "Другое",
    }
    
    category_name = category_names.get(category, "")
    subcategory_name = subcategory_names.get(subcategory, "")
    
    # Формируем строку типа изделия
    product_type_parts = []
    if category_name:
        product_type_parts.append(category_name)
    if subcategory_name:
        product_type_parts.append(subcategory_name)
    if item:
        product_type_parts.append(item)
    
    product_type = ", ".join(product_type_parts)
    await state.update_data(own_variant_product_type=product_type, own_variant_category=category, own_variant_subcategory=subcategory)
    
    # Переходим к выбору части товара на фото
    await state.set_state(CreateForm.waiting_own_variant_view)
    await _replace_with_text(
        callback,
        f"✅ Тип изделия: {product_type}\n\n📸 Укажите, какая часть товара на фото:",
        reply_markup=own_variant_product_view_keyboard()
    )
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_own_variant_view, F.data.startswith("own_variant_view:"))
async def on_own_variant_view(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик выбора части товара на фото"""
    view_val = callback.data.split(":", 1)[1]
    
    view_map = {
        "front": "Передняя",
        "back": "Задняя",
        "side": "Боковая",
        "skip": None,
    }
    
    if view_val != "skip":
        view_text = view_map.get(view_val, view_val)
        await state.update_data(own_variant_view=view_text)
        logger.info(f"[on_own_variant_view] Сохранена часть товара: {view_text}")
    else:
        await state.update_data(own_variant_view="")
        logger.info(f"[on_own_variant_view] Часть товара пропущена")
    
    # Получаем данные для отображения
    data = await state.get_data()
    product_type = data.get("own_variant_product_type", "")
    
    view_display = view_map.get(view_val, "не указана") if view_val != "skip" else "не указана"
    
    await _replace_with_text(
        callback,
        f"✅ Тип изделия: {product_type}\n"
        f"📸 Часть товара на фото: {view_display}\n\n"
        f"Нажмите 'Создать фото' для генерации:",
        reply_markup=confirm_generation_keyboard()
    )
    await _safe_answer(callback)


@router.message(CreateForm.waiting_ref_photo, F.photo)
async def on_own_ref_photo(message: Message, state: FSMContext, db: Database) -> None:
    ref_id = message.photo[-1].file_id
    await state.update_data(own_ref_photo_id=ref_id)
    # Генерируем текстовое описание модели из фото
    progress_msg = await message.answer("⏳ Анализирую фото...")
    try:
        file = await message.bot.get_file(ref_id)
        f = await message.bot.download_file(file.file_path)
        ref_bytes = f.read()
        # Берём промт из БД, если задан
        description_prompt = await db.get_own_prompt1() or (
            "You will receive a photo of a person.\n\n"
            "Your job is to produce an extremely precise, observational, high-resolution description strictly based on the visible contents of the image.\n\n"
            "Do NOT guess or infer anything not directly visible. Do NOT beautify, generalize, stylize, or interpret. Treat the image as scientific documentation for 3D reconstruction.\n\n"
            "Focus on measurable, observable, physical details only.\n\n"
            "Every statement must be grounded in what is clearly visible.\n\n"
            "Do NOT describe clothing design, materials, style, fashion elements, or construction.\n\n"
            "Only allowed clothing references: \"upper body covered,\" \"arms covered,\" \"legs covered,\" etc.\n\n"
            "Describe the following categories with maximum precision:\n\n"
            "[FACE]\n\n"
            "Provide a rigorous breakdown of visible bone structure, proportions, angles, skin tone, undertone, micro-texture, pores, highlights, shadows, eye color, eyelid anatomy, eyebrow density, nose structure, lips, expression, and any visible asymmetry.\n\n"
            "No interpretation. Only description of what is visible.\n\n"
            "[HAIR]\n\n"
            "Describe length, density, texture, direction of flow, exact part placement, color variations, how light interacts with strands.\n\n"
            "[BODY]\n\n"
            "Describe only what is visible in frame: proportions, posture, weight distribution, shoulder width, torso alignment.\n\n"
            "[POSE]\n\n"
            "Describe the mechanical position of head, neck, shoulders, torso, arms, hands, legs, feet.\n\n"
            "Give exact angles relative to camera when possible.\n\n"
            "[LIGHTING]\n\n"
            "Describe the type, direction, intensity, softness, color temperature, shadows, edge transitions, reflections, and micro-contrast on the skin.\n\n"
            "[CAMERA / FRAMING]\n\n"
            "Describe distance, crop, angle, focal-length impression, perspective distortion, and depth-of-field.\n\n"
            "[BACKGROUND]\n\n"
            "Describe textures, surfaces, environment type, materials, colors, depth layers, shadows, and reflected light.\n\n"
            "Your description must be strictly visual, extremely detailed, and fully grounded in the image.\n\n"
            "No assumptions. No simplifications. No clothing details."
        )
        settings = load_settings()
        keys_with_ids = await db.list_api_keys()
        tokens_order: list[tuple[int | None, str]] = [(kid, tok) for (kid, tok, is_active) in keys_with_ids if is_active]
        env_key = settings.gemini_api_key
        if env_key and all(tok != env_key for _kid, tok in tokens_order):
            tokens_order.append((None, env_key))
        description_text = None
        last_err: Exception | None = None
        for _kid, token in tokens_order:
            try:
                description_text = await generate_text(token, description_prompt, ref_bytes)
                if description_text:
                    last_err = None
                    break
            except Exception as e:
                last_err = e
                logger.error(f"[on_own_ref_photo] Ошибка generate_text с ключом {_kid}: {e}", exc_info=True)
                continue
        if not description_text:
            try:
                await progress_msg.delete()
            except Exception:
                pass
            # Логируем детальную ошибку для админов, но пользователю показываем простое сообщение
            if last_err:
                logger.error(f"[on_own_ref_photo] Все ключи исчерпаны. Последняя ошибка: {last_err}", exc_info=True)
            await message.answer("Произошла ошибка! Возможно фотография нарушает правила сервиса или произошёл сбой в случаи повторных ошибок напишите @bnbslow сюда")
            return
        await state.update_data(own_model_description=description_text)
        try:
            await progress_msg.delete()
        except Exception:
            pass
        await state.set_state(CreateForm.waiting_product_photo)
        await message.answer(
            "✅ Фото проанализировано. Теперь пришлите фото товара.\n\n"
            "Бот создаст изображение с той же моделью и сценой, используя ваш товар."
        )
    except Exception as e:
        logger.error(f"[on_own_ref_photo] Неожиданная ошибка: {e}", exc_info=True)
        try:
            await progress_msg.delete()
        except Exception:
            pass
        await message.answer("Произошла ошибка! Возможно фотография нарушает правила сервиса или произошёл сбой в случаи повторных ошибок напишите @bnbslow сюда")


@router.message(CreateForm.waiting_product_photo, F.photo)
async def on_own_product_photo(message: Message, state: FSMContext) -> None:
    prod_id = message.photo[-1].file_id
    await state.update_data(own_product_photo_id=prod_id)
    await state.set_state(CreateForm.waiting_own_length)
    await message.answer(
        "📏 Укажите длину изделия (числом см или словами) или нажмите 'Пропустить':",
        reply_markup=form_length_skip_keyboard(),
    )


@router.callback_query(F.data.startswith("own_view:"))
async def on_own_view(callback: CallbackQuery, state: FSMContext) -> None:
    view = callback.data.split(":", 1)[1]
    await state.update_data(own_view=view)
    # Сразу переходим к длине изделия (убираем вопрос о телосложении)
    await state.set_state(CreateForm.waiting_own_length)
    await _replace_with_text(
        callback,
        "📏 Укажите длину изделия (числом см или словами) или нажмите 'Пропустить':",
        reply_markup=form_length_skip_keyboard(),
    )
    await _safe_answer(callback)


@router.callback_query(CreateForm.waiting_own_size, F.data.startswith("form_size:"))
async def on_own_size(callback: CallbackQuery, state: FSMContext) -> None:
    # Переиспользуем общий размер и кладём в own_size, если own_mode
    val = callback.data.split(":", 1)[1]
    size_map = {"thin": "Худая", "curvy": "Пышная", "plus": "Очень пышная"}
    current = await state.get_data()
    if current.get("own_mode"):
        await state.update_data(own_size=size_map.get(val, ""))
        await state.set_state(CreateForm.waiting_own_length)
        await _replace_with_text(
            callback,
            "📏 Укажите длину изделия (числом см или словами) или нажмите 'Пропустить':",
            reply_markup=form_length_skip_keyboard(),
        )
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
async def on_own_sleeve(callback: CallbackQuery, state: FSMContext) -> None:
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
        # Предпросмотр и подтверждение без «телосложения» и «типа кроя»
        data = await state.get_data()
        length = data.get("own_length") or "—"
        sleeve = data.get("own_sleeve") or "—"
        preview = (
            "📋 Проверьте параметры:\n\n"
            f"📏 Длина изделия: {length}\n"
            f"🧥 Длина рукава: {sleeve}\n"
        )
        await _replace_with_text(callback, preview, reply_markup=confirm_generation_keyboard())
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
    else:
        await _replace_with_text(callback, "Выберите ракурс:", reply_markup=random_shot_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("rand_decor:"))
async def on_random_decor(callback: CallbackQuery, state: FSMContext) -> None:
    decor = callback.data.split(":", 1)[1]
    await state.update_data(rand_decor=decor)
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


@router.callback_query(F.data == "create_cat:female")
async def on_female_category(callback: CallbackQuery, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    text = "⚙️ Выберите режим генерации:"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    if not await db.get_category_enabled("female"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    await _replace_with_text(callback, text, reply_markup=female_mode_keyboard())
    await _safe_answer(callback)
@router.callback_query(F.data == "create_cat:child")
async def on_child_category(callback: CallbackQuery, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    text = "⚙️ Выберите режим генерации:"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    if not await db.get_category_enabled("child"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    await _replace_with_text(callback, text, reply_markup=boy_mode_keyboard())
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
        await state.set_state(State('waiting_pants_style'))
    else:
        if category == "child":
            # Сначала выбираем пол ребёнка
            from bot.keyboards import child_gender_keyboard
            await _replace_with_text(callback, "Выберите пол ребёнка:", reply_markup=child_gender_keyboard())
            await state.set_state(CreateForm.waiting_child_gender)
            await _safe_answer(callback)
            return
            if cloth == "shoes":
                # Детская обувь: сначала размер ноги (можно пропустить), потом рост, потом ракурс
                await _replace_with_text(callback, "Введите размер ноги ребенка (например: 31) или отправьте 'Пропустить':")
                await state.set_state(CreateForm.waiting_foot)
            else:
                # Детская одежда: сначала рост
                await _replace_with_text(callback, "Введите рост ребенка в см (например: 130):")
                await state.set_state(CreateForm.waiting_height)
        else:
            # Взрослые: обувь — рост → размер ноги → ракурс; одежда — телосложение → возраст → рост → длина → рукав → ракурс
            if cloth == "shoes":
                await _replace_with_text(callback, "Введите рост модели в см (например: 170):")
                await state.set_state(CreateForm.waiting_height)
            elif category == "storefront":
                # Для витринного фона: длина изделия → ракурс → фото
                await _replace_with_text(callback, "📏 Укажите длину изделия (например: 85 см) или нажмите 'Пропустить':", reply_markup=form_length_skip_keyboard())
                await state.set_state(CreateForm.waiting_length)
            else:
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
async def on_pants_style(callback: CallbackQuery, state: FSMContext) -> None:
    style = callback.data.split(":", 1)[1]
    await state.update_data(pants_style=style)
    data = await state.get_data()
    category = data.get("category")
    if (await state.get_data()).get("random_mode"):
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
async def form_set_age_message(message: Message, state: FSMContext) -> None:
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
            await state.set_state(CreateForm.waiting_length)
            await message.answer("📏 Укажите длину изделия (например: 85 см) или нажмите 'Пропустить':", reply_markup=form_length_skip_keyboard())
    else:
        # Взрослые: после возраста — к выбору телосложения
        await state.set_state(CreateForm.waiting_size)
        await message.answer("Выберите телосложение:", reply_markup=form_size_keyboard(data.get("category")))


@router.callback_query(CreateForm.waiting_size, F.data.startswith("form_size:"))
async def form_set_size(callback: CallbackQuery, state: FSMContext) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    category = data.get("category")
    if category == "male":
        size_map = {
            "thin": "Худой и стройный",
            "curvy": "Телосложение пышное и полные ноги, пухлое лицо.",
            "plus": "Size Plus очень крупное и пышное телосложение, полные ноги и круглое пухлое лицо.",
        }
    else:
        size_map = {
            "thin": "Худая и стройная",
            "curvy": "Телосложение пышное и полные ноги пухлое лицо.",
            "plus": "Size Plus очень крупное и пышное телосложение полные ноги и круглое и пухлое лицо.",
        }
    await state.update_data(size=size_map.get(val, ""))
    # После телосложения для взрослых — возраст кнопками; для детей телосложение не используется
    if data.get("random_mode"):
        # В рандоме после размера — длина изделия
        await _replace_with_text(callback, "📏 Укажите длину изделия (например: 85 см) или нажмите 'Пропустить':", reply_markup=form_length_skip_keyboard())
        await state.set_state(CreateForm.waiting_length)
    elif data.get("category") in ("female", "male") and (data.get("cloth") != "shoes"):
        await _replace_with_text(callback, "🎂 Пожалуйста выберите возраст модели:", reply_markup=form_age_keyboard())
        await state.set_state(CreateForm.waiting_age)
    else:
        await _replace_with_text(callback, "📏 Введите рост модели в см (например: 170):")
        await state.set_state(CreateForm.waiting_height)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_height)
async def form_set_height(message: Message, state: FSMContext) -> None:
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
        await state.set_state(CreateForm.waiting_length)
        await message.answer("📏 Укажите длину изделия (например: 85 см) или нажмите 'Пропустить':", reply_markup=form_length_skip_keyboard())
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
        await state.set_state(CreateForm.waiting_length)
        await message.answer("📏 Укажите длину изделия (например: 85 см) или нажмите 'Пропустить':", reply_markup=form_length_skip_keyboard())
        return
    # Детская обувь: после роста — сразу ракурс (размер уже спросили до роста)
    if category == "child" and cloth == "shoes":
        await state.set_state(CreateForm.waiting_view)
        await message.answer("👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())
        return
    # Прочие случаи: по умолчанию — длина изделия, затем рукав
    await state.set_state(CreateForm.waiting_length)
    await message.answer("📏 Укажите длину изделия (например: 85 см) или нажмите 'Пропустить':", reply_markup=form_length_skip_keyboard())


@router.message(CreateForm.waiting_length)
async def form_set_length(message: Message, state: FSMContext) -> None:
    length = message.text.strip()
    await state.update_data(length=length)
    data = await state.get_data()
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
        await state.set_state(State('waiting_pants_style'))
        await message.answer("Тип кроя штанов (опционально):", reply_markup=pants_style_keyboard())
    else:
        await state.set_state(CreateForm.waiting_view)
        await message.answer("👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())


@router.callback_query(F.data == "form_len:skip")
async def form_skip_length(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    # Собственная ветка (own_mode): пропуск длины изделия
    if data.get("own_mode"):
        await state.update_data(own_length="")
        await _replace_with_text(callback, "Выберите длину рукава:", reply_markup=sleeve_length_keyboard())
        await state.set_state(CreateForm.waiting_own_sleeve)
        await _safe_answer(callback)
        return
    await state.update_data(length="")
    cloth = data.get("cloth")
    plus_mode = bool(data.get("plus_mode"))
    if data.get("random_mode"):
        await _replace_with_text(callback, "Clothing Sleeve Length: выберите длину рукава или пропустите", reply_markup=sleeve_length_keyboard())
        await state.set_state(CreateForm.waiting_sleeve)
    elif cloth == "dress" or (plus_mode and cloth in ("top", "coat", "suit", "overall", "loungewear")):
        await _replace_with_text(callback, "Clothing Sleeve Length: выберите длину рукава или пропустите", reply_markup=sleeve_length_keyboard())
        await state.set_state(CreateForm.waiting_sleeve)
    elif plus_mode and cloth == "pants":
        await _replace_with_text(callback, "Тип кроя штанов (опционально):", reply_markup=pants_style_keyboard())
        await state.set_state(State('waiting_pants_style'))
    else:
        await _replace_with_text(callback, "👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())
        await state.set_state(CreateForm.waiting_view)
    await _safe_answer(callback)


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
    if data.get("random_mode"):
        await _replace_with_text(callback, "Тип кроя штанов (опционально):", reply_markup=pants_style_keyboard())
        await state.set_state(State('waiting_pants_style'))
    else:
        await _replace_with_text(callback, "👀 Пожалуйста выберите ракурс:", reply_markup=form_view_keyboard())
        await state.set_state(CreateForm.waiting_view)
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

    # Собираем параметры
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
        vibe_map = {"decor":"С декором элементами","plain":"Без декора","newyear":"Новый год","normal":"Обычный"}
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
        vibe_map = {"summer":"Лето","winter":"Зима","autumn":"Осень","spring":"Весна","newyear":"Новый год"}
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
    await message.answer(text, reply_markup=confirm_generation_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "form_cancel")
async def form_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _replace_with_text(callback, "🎯 Главное меню:", reply_markup=main_menu_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "form_generate")
async def get_final_prompt(data: dict, db: Database) -> str:
    """Формирует финальный промпт на основе шаблонов из БД или жесткой логики (fallback)"""
    category = data.get("category")
    own_variant = data.get("own_variant_mode", False)
    
    # 1. Сначала проверяем наличие пользовательского шаблона в БД
    # Ключи: template_female, template_male, template_child, template_whitebg, template_random, template_own, template_own_variant
    template_key = f"template_{category}"
    if own_variant:
        template_key = "template_own_variant"
    
    template = await db.get_prompt_template(template_key)
    
    # Маппинг для подстановки
    age_map = {
        "20_26": "20-26 лет",
        "30_38": "30-38 лет",
        "40_48": "40-48 лет",
        "55_60": "55-60 лет",
    }
    gender_map = {"male": "мужчина", "female": "женщина", "boy": "мальчик", "girl": "девочка"}
    view_map = {"back": "сзади", "front": "спереди", "side": "сбоку"}
    
    # Собираем данные для подстановки
    fill_data = {
        "Длина": data.get("length") or data.get("own_variant_length") or data.get("own_length") or "",
        "Возраст": age_map.get(data.get("age"), data.get("age") or ""),
        "Пол": gender_map.get(data.get("rand_gender") or data.get("own_variant_category") or data.get("category"), ""),
        "Стиль": data.get("own_variant_product_type") or data.get("pants_style") or "",
        "Рукав": data.get("sleeve") or data.get("own_variant_sleeve") or data.get("own_sleeve") or "",
        "Размер": data.get("size") or "",
        "Рост": str(data.get("height") or ""),
        "Описание": data.get("own_model_description") or "",
        "Ракурс": view_map.get(data.get("view") or data.get("own_variant_view"), "спереди"),
        "Место": data.get("rand_location") or data.get("plus_loc") or "",
        "Вайб": data.get("rand_vibe") or data.get("plus_vibe") or "",
        "Сезон": data.get("rand_vibe") or data.get("plus_season") or "",
    }

    if template:
        result_prompt = template
        for k, v in fill_data.items():
            result_prompt = result_prompt.replace(f"{{{k}}}", str(v))
        return Database.add_ai_room_branding(result_prompt)

    # 2. Fallback: Старая жесткая логика (если шаблона нет)
    prompt_filled = ""
    
    if own_variant:
        # Для 'Свой вариант' берем из настроек
        prompt_filled = await db.get_own_variant_prompt() or ""
        # Тут была сложная логика замены плейсхолдеров (она теперь покрыта шаблоном выше, 
        # но если шаблона нет, используем старые замены)
        ph_map = {
            "{Длина изделия}": fill_data["Длина"],
            "{Длина рукавов}": fill_data["Рукав"],
            "{тип изделия}": fill_data["Стиль"],
            "{view}": fill_data["Ракурс"]
        }
        for ph, val in ph_map.items():
            prompt_filled = prompt_filled.replace(ph, str(val))
            
    elif data.get("random_mode"):
        base_random = await db.get_random_prompt() or ""
        parts = [f"{fill_data['Пол']} {fill_data['Возраст']}. Рост {fill_data['Рост']} см. {fill_data['Размер']}."]
        if fill_data['Место']: parts.append(f" Место: {fill_data['Место']}.")
        if fill_data['Вайб']: parts.append(f" Вайб: {fill_data['Вайб']}.")
        parts.append(f" Ракурс: {fill_data['Ракурс']}. Профессиональное фото.")
        prompt_filled = (base_random + "\n\n" + "".join(parts)).strip()
        
    elif data.get("own_mode"):
        base = await db.get_own_prompt3() or "Create a professional fashion photo..."
        prompt_filled = base.replace("{Сюда нужно поставить полученное описание от Gemini}", fill_data["Описание"])\
                            .replace("{Длина изделия}", fill_data["Длина"])\
                            .replace("{Длина рукавов}", fill_data["Рукав"])
    else:
        # Обычные категории
        if data.get("category") == "whitebg":
            base = await db.get_whitebg_prompt() or ""
            prompt_filled = base + f" Ракурс: {fill_data['Ракурс']}. Белый фон."
        else:
            pid = data.get('prompt_id')
            prompt_text = await db.get_prompt_text(int(pid)) if pid else ""
            prompt_filled = prompt_text.replace("{длина изделия}", fill_data["Длина"])\
                                       .replace("{возраст}", fill_data["Возраст"])\
                                       .replace("{длина рукав}", fill_data["Рукав"])\
                                       .replace("{сзади/спереди}", fill_data["Ракурс"])
    
    return Database.add_ai_room_branding(prompt_filled)

async def form_generate(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    user_id = callback.from_user.id
    logger.info(f"[form_generate] Начало генерации для пользователя {user_id}")
    # Блокировка генерации при техработах (для не-админов)
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    data = await state.get_data()
    if not data:
        logger.warning(f"[form_generate] Сессия формы не найдена для пользователя {user_id}")
        await _safe_answer(callback, "Сессия формы не найдена", show_alert=True)
        return
    balance = await db.get_user_balance(user_id)
    own = bool(data.get("own_mode"))
    own_variant = bool(data.get("own_variant_mode"))
    # проверяем баланс с учётом десятых
    frac = await db.get_user_fraction(user_id)
    # Получаем цену категории из БД
    if own_variant:
        price_tenths = await db.get_category_price("own_variant")
    elif own:
        price_tenths = await db.get_category_price("own")
    else:
        # Определяем категорию для обычных режимов
        category = data.get("category") or "female"  # По умолчанию female
        price_tenths = await db.get_category_price(category)
    total_tenths = balance * 10 + frac
    if total_tenths < price_tenths:
        # Форматируем цену для сообщения об ошибке
        if price_tenths % 10 == 0:
            need_str = f"{price_tenths // 10}"
        else:
            need_str = f"{price_tenths / 10:.1f}"
        await _safe_answer(callback, f"Недостаточно генераций (нужно {need_str} токен(ов))", show_alert=True)
        return

    # Формируем финальный промпт через новую функцию (с поддержкой шаблонов из БД)
    prompt_filled = await get_final_prompt(data, db)
    
    await _replace_with_text(callback, "Запуск генерации...", reply_markup=None)
    await _safe_answer(callback)
    # Начальное сообщение с прогресс-баром
    initial_message = (
        "✏️ Редактирование\n\n"
        "Понимаю, что изменить\n\n"
        "⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️ 0%\n\n"
        "Прошло: 0с • Шаг 1/5\n\n"
        "Результат вас приятно удивит"
    )
    progress_msg = await callback.message.answer(initial_message)
    stop_event = asyncio.Event()
    asyncio.create_task(_run_generation_progress(callback.bot, callback.message.chat.id, progress_msg.message_id, stop_event))

    # Загрузка фото(ов)
    if own_variant:
        # Для "Своего варианта": photo1 - модель, photo2 - одежда
        # В Gemini API порядок: первое фото = user_image_bytes, второе = ref_image_bytes
        # Чтобы промт соответствовал (Photo 1 = модель), делаем:
        # - photo1 (модель) идет как user_image_bytes (первое фото)
        # - photo2 (одежда) идет как ref_image_bytes (второе фото)
        photo1_id = data.get("own_variant_photo1_id")
        photo2_id = data.get("own_variant_photo2_id")
        if not photo1_id or not photo2_id:
            await _replace_with_text(callback, "Фото не найдены. Начните заново.", reply_markup=back_main_keyboard())
            await _safe_answer(callback)
            return
        # photo1 (модель) идет первым фото (user_image_bytes) - это Photo 1 в промте
        photo1_file = await callback.bot.get_file(photo1_id)
        photo1_bytes = await callback.bot.download_file(photo1_file.file_path)
        image_bytes = photo1_bytes.read()  # Первое фото = модель (Photo 1)
        # photo2 (одежда) идет вторым фото (ref_image_bytes) - это Photo 2 в промте
        photo2_file = await callback.bot.get_file(photo2_id)
        photo2_bytes = await callback.bot.download_file(photo2_file.file_path)
        reference_bytes = photo2_bytes.read()  # Второе фото = одежда (Photo 2)
    elif data.get("own_mode"):
        prod_id = data.get("own_product_photo_id")
        model_description = data.get("own_model_description")
        if not prod_id:
            await _replace_with_text(callback, "Фото товара не найдено. Начните заново.", reply_markup=back_main_keyboard())
            await _safe_answer(callback)
            return
        if not model_description:
            await _replace_with_text(callback, "Описание модели не найдено. Начните заново.", reply_markup=back_main_keyboard())
            await _safe_answer(callback)
            return
        # product image
        prod_file = await callback.bot.get_file(prod_id)
        prod_bytes = await callback.bot.download_file(prod_file.file_path)
        image_bytes = prod_bytes.read()
        reference_bytes = None  # В новом режиме не используем референсное фото
    else:
        user_photo_id = data.get("user_photo_id")
        if not user_photo_id:
            await _replace_with_text(callback, "Фото не найдено в сессии", reply_markup=back_main_keyboard())
            await _safe_answer(callback)
            return
        file = await callback.bot.get_file(user_photo_id)
        file_bytes = await callback.bot.download_file(file.file_path)
        image_bytes = file_bytes.read()
        # Загружаем референсное фото, если есть
        reference_bytes = None
        ref_photo_id = data.get("ref_photo_id")
        if ref_photo_id:
            try:
                ref_file = await callback.bot.get_file(ref_photo_id)
                ref_file_bytes = await callback.bot.download_file(ref_file.file_path)
                reference_bytes = ref_file_bytes.read()
            except Exception as e:
                logger.warning(f"[form_generate] Не удалось загрузить референсное фото: {e}")
                reference_bytes = None

    # Вызов Gemini с ротацией ключей
    settings = load_settings()
    # Для own_variant используем отдельные API-ключи
    if own_variant:
        keys_with_ids = await db.list_own_variant_api_keys()
        tokens_order: list[tuple[int | None, str]] = [(kid, tok) for (kid, tok, is_active) in keys_with_ids if is_active]
        env_key = settings.gemini_api_key
        if env_key and all(tok != env_key for _kid, tok in tokens_order):
            tokens_order.append((None, env_key))
    else:
        # Берем активные ключи из БД, добавляем env-ключ в конец, если он ещё не в списке
        keys_with_ids = await db.list_api_keys()
        tokens_order: list[tuple[int | None, str]] = [(kid, tok) for (kid, tok, is_active) in keys_with_ids if is_active]
        env_key = settings.gemini_api_key
        if env_key and all(tok != env_key for _kid, tok in tokens_order):
            tokens_order.append((None, env_key))
    
    logger.info(f"[form_generate] Найдено {len(tokens_order)} активных ключей для генерации")
    if not tokens_order:
        logger.error("[form_generate] Нет активных API ключей!")
        stop_event.set()
        error_text = "Произошла ошибка! Возможно фотография нарушает правила сервиса или произошёл сбой в случаи повторных ошибок напишите @bnbslow сюда"
        try:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=progress_msg.message_id, text=error_text)
        except Exception:
            pass
        await callback.message.answer(error_text)
        await state.clear()
        return
    
    result_bytes = None
    last_error: Exception | None = None
    for key_id, token in tokens_order:
        try:
            # Проверка rate limiting для own_variant
            if own_variant and key_id is not None:
                is_allowed, error_msg = await db.check_own_variant_rate_limit(key_id, tokens_needed=2)
                if not is_allowed:
                    logger.warning(f"[form_generate] Rate limit exceeded для ключа {key_id}: {error_msg}")
                    continue
            
            # own_mode: не используем референсное фото, только описание модели в промте
            # own_variant: используем photo1 как reference, photo2 как image
            ref_bytes = reference_bytes if (own_variant or not data.get("own_mode")) else None
            # Используем модель gemini-3-pro-image-preview для всех категорий
            model_name = "gemini-3-pro-image-preview"
            logger.info(f"[form_generate] Попытка генерации с ключом {key_id}, own_mode={data.get('own_mode')}, own_variant={own_variant}, model={model_name}, prompt_len={len(prompt_filled)}, image_size={len(image_bytes)}, ref_size={len(ref_bytes) if ref_bytes else 0}")
            if own_variant:
                logger.info(f"[form_generate] Финальный промт для 'Свой вариант' перед отправкой в API:")
                logger.info(f"[form_generate] Промт (первые 1000 символов): {prompt_filled[:1000]}")
                logger.info(f"[form_generate] Промт (последние 1000 символов): {prompt_filled[-1000:]}")
                logger.info(f"[form_generate] Полная длина финального промта: {len(prompt_filled)} символов")
            result_bytes = await generate_image(token, prompt_filled, image_bytes, ref_bytes, model_name)
            
            # Записываем использование для rate limiting
            if own_variant and key_id is not None and result_bytes:
                await db.record_own_variant_usage(key_id, tokens_used=2)
            if result_bytes:
                logger.info(f"[form_generate] Успешная генерация с ключом {key_id}, размер результата: {len(result_bytes)}")
                last_error = None
                break
        except Exception as e:
            last_error = e
            logger.error(f"[form_generate] Ошибка generate_image с ключом {key_id}: {e}", exc_info=True)
            # Если известная ошибка квоты — деактивируем ключ
            msg = str(e).lower()
            if key_id is not None and ("quota" in msg or "429" in msg or "permission" in msg or "api key" in msg):
                try:
                    await db.update_api_key(key_id, is_active=0)
                    logger.warning(f"[form_generate] Ключ {key_id} деактивирован из-за ошибки квоты")
                except Exception:
                    pass
            continue
    if last_error is not None and not result_bytes:
        stop_event.set()
        logger.error(f"[form_generate] Все ключи исчерпаны. Последняя ошибка: {last_error}", exc_info=True)
        error_text = "Произошла ошибка! Возможно фотография нарушает правила сервиса или произошёл сбой в случаи повторных ошибок напишите @bnbslow сюда"
        try:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=progress_msg.message_id, text=error_text)
        except Exception:
            pass
        await callback.message.answer(error_text)
        await state.clear()
        return

    if not result_bytes:
        stop_event.set()
        logger.error(f"[form_generate] result_bytes пустой после всех попыток. Попыток было: {len(tokens_order)}, последняя ошибка: {last_error}")
        error_text = "Произошла ошибка! Возможно фотография нарушает правила сервиса или произошёл сбой в случаи повторных ошибок напишите @bnbslow сюда"
        try:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=progress_msg.message_id, text=error_text)
        except Exception:
            pass
        await callback.message.answer(error_text)
        await state.clear()
        return

    try:
        # Списываем генерации при успехе (с поддержкой десятых)
        before_balance = balance
        before_frac = frac
        total_after = total_tenths - price_tenths
        new_balance = total_after // 10
        new_frac = total_after % 10
        delta = new_balance - before_balance
        if delta != 0:
            await db.increment_user_balance(user_id, delta)
        await db.set_user_fraction(user_id, new_frac)
        try:
            # Фиксируем целочисленную часть списания; дробная учтена во фракции
            reason = "generation_own_variant_2.0" if own_variant else ("generation_own_1.2" if own else "generation")
            if delta != 0:
                await db.add_transaction(user_id, delta, "spend", reason)
            else:
                # на всякий случай фиксируем событие нулевой строкой с adjust
                await db.add_transaction(user_id, 0, "adjust", reason)
        except Exception:
            pass
        photo_file = BufferedInputFile(result_bytes, filename="result.png")
        stop_event.set()
        try:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=progress_msg.message_id, text="✅ Готово")
        except TelegramRetryAfter:
            try:
                await callback.message.answer("✅ Готово")
            except Exception:
                pass
        except Exception:
            pass
        if own_variant or data.get("own_mode"):
            await callback.message.answer_document(document=photo_file, caption="Готово", reply_markup=result_actions_own_keyboard())
        else:
            await callback.message.answer_document(document=photo_file, caption="Готово", reply_markup=result_actions_keyboard())
    except Exception as e:
        stop_event.set()
        try:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=progress_msg.message_id, text=f"❌ Ошибка отправки: {e}")
        except TelegramRetryAfter:
            try:
                await callback.message.answer(f"❌ Ошибка отправки: {e}")
            except Exception:
                pass
        except Exception:
            pass
        await callback.message.answer(f"Ошибка отправки изображения: {e}")
    # Не очищаем состояние, чтобы была возможность «Внести правки»
    await state.set_state(CreateForm.result_ready)


@router.callback_query(F.data == "result_edit")
async def on_result_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateForm.waiting_edit_text)
    # Не трогаем предыдущее сообщение с фото, отправляем новое
    await callback.message.answer("Опишите коротко, какие правки нужны (текстом):")
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
        vibe_map = {"summer":"летний", "winter":"зимний", "autumn":"осенний", "spring":"весенний", "newyear":"новогодний"}
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

    from bot.config import load_settings
    from bot.gemini import generate_image
    settings = load_settings()
    try:
        result_bytes = await generate_image(settings.gemini_api_key, prompt_filled, user_image_bytes, None)
    except Exception as e:
        await message.answer("Произошла ошибка! Возможно фотография нарушает правила сервиса или произошёл сбой в случаи повторных ошибок напишите @bnbslow сюда")
        await state.clear()
        return
    if not result_bytes:
        await message.answer("Произошла ошибка! Возможно фотография нарушает правила сервиса или произошёл сбой в случаи повторных ошибок напишите @bnbslow сюда")
        await state.clear()
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
        await message.answer_document(document=photo_file, caption="Готово", reply_markup=back_main_keyboard())
    except Exception as e:
        await message.answer(f"Ошибка отправки изображения: {e}")
    await state.clear()


@router.callback_query(F.data == "result_repeat")
async def on_result_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await _safe_answer(callback, "Сессия не найдена", show_alert=True)
        return
    # Сохраняем предыдущие настройки и просим новое фото
    await state.set_state(CreateForm.waiting_view)
    # Не удаляем предыдущее фото, отправляем новый запрос
    await callback.message.answer("📸 Пришлите следующее фото товара с теми же параметрами.")
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


# removed old duplicate handler (replaced by FSM version above)


@router.callback_query(F.data == "create_cat:male")
async def on_male_category(callback: CallbackQuery, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    text = "⚙️ Выберите режим генерации:"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    if not await db.get_category_enabled("male"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    await _replace_with_text(callback, text, reply_markup=male_mode_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "male_mode:model_bg")
async def on_male_mode_model_bg(callback: CallbackQuery) -> None:
    text = "👕 Выберите тип одежды:"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=male_clothes_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "male_mode:plus")
async def on_male_mode_plus(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(plus_mode=True)
    text = "🚻 Выберите пол для большого размера:"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=plus_gender_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data.startswith("plus_gender:"))
async def on_plus_gender(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    gender = callback.data.split(":", 1)[1]
    if gender not in ("female", "male"):
        await _safe_answer(callback)
        return
    if not await db.get_category_enabled(gender):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    if gender == "female":
        await _replace_with_text(callback, "👕 Выберите тип одежды:", reply_markup=female_clothes_keyboard())
    else:
        await _replace_with_text(callback, "👕 Выберите тип одежды:", reply_markup=male_clothes_keyboard())
    await _safe_answer(callback)

@router.callback_query(F.data == "create_cat:child")
async def on_child_category(callback: CallbackQuery, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    text = "⚙️ Выберите режим генерации:"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=boy_mode_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "child_mode:model_bg")
async def on_child_mode_model_bg(callback: CallbackQuery) -> None:
    text = "👕 Выберите тип одежды:"
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=boy_clothes_keyboard())
    await _safe_answer(callback)


# Убраны отдельные сценарии мальчик/девочка; используем единый child


@router.callback_query(F.data == "create_cat:storefront")
async def on_storefront(callback: CallbackQuery, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    if not await db.get_category_enabled("storefront"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    # Ищем доступные фоны для витринного фото. По умолчанию используем cloth='bg'.
    candidate_cloths = ["bg", "coat", "top", "dress", "overall", "loungewear", "suit", "skirt", "pants", "shorts"]
    chosen_cloth = None
    total = 0
    for c in candidate_cloths:
        cnt = await db.count_models("storefront", c)
        if cnt > 0:
            chosen_cloth = c
            total = cnt
            break
    if not chosen_cloth:
        await _safe_answer(callback, "Фоны для витринного фото пока не добавлены", show_alert=True)
        return
    text = _model_header(0, total)
    model = await db.get_model_by_index("storefront", chosen_cloth, 0)
    if model and model[3]:
        await _answer_model_photo(
            callback,
            model[3],
            text,
            model_select_keyboard("storefront", chosen_cloth, 0, total),
        )
    else:
        await _replace_with_text(callback, text, reply_markup=model_select_keyboard("storefront", chosen_cloth, 0, total))
    await _safe_answer(callback)


@router.callback_query(F.data == "create_cat:whitebg")
async def on_whitebg(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    if not await db.get_category_enabled("whitebg"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    # Помечаем режим белого фона, чтобы использовать базовый промт
    await state.update_data(category="whitebg")
    text = "👀 Выберите ракурс для фото на белом фоне:"
    await _replace_with_text(callback, text, reply_markup=whitebg_view_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "storefront_len")
async def on_storefront_len(callback: CallbackQuery, state: FSMContext) -> None:
    # Позволяем запросить длину изделия отдельно для витринного сценария
    await state.set_state(CreateForm.waiting_length)
    await _replace_with_text(
        callback,
        "📏 Укажите длину изделия (например: 85 см) или нажмите 'Пропустить':",
        reply_markup=form_length_skip_keyboard(),
    )
    await _safe_answer(callback)


@router.callback_query(F.data == "menu_balance")
async def on_balance_open(callback: CallbackQuery, db: Database) -> None:
    balance = await db.get_user_balance(callback.from_user.id)
    frac = await db.get_user_fraction(callback.from_user.id)
    balance_str = f"{balance}" if not frac else f"{balance}.{frac}"
    user_id = callback.from_user.id
    text = (
        f"💰 Ваш текущий баланс: {balance_str} генераций\n\n"
        "Для пополнения баланса напишите нашему менеджеру:\n"
        "@bnbslow\n\n"
        f"Укажите ваш ID для зачисления: {user_id}"
    )
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=balance_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "balance_topup")
async def on_balance_topup(callback: CallbackQuery, db: Database) -> None:
    balance = await db.get_user_balance(callback.from_user.id)
    frac = await db.get_user_fraction(callback.from_user.id)
    balance_str = f"{balance}" if not frac else f"{balance}.{frac}"
    user_id = callback.from_user.id
    text = (
        "💳 Пополнение баланса\n\n"
        f"Текущий баланс: {balance_str} генераций\n\n"
        "Для пополнения баланса напишите нашему менеджеру:\n"
        "@bnbslow\n\n"
        f"Укажите ваш ID для зачисления: {user_id}"
    )
    if callback.message and callback.message.text == text:
        await _safe_answer(callback)
        return
    await _replace_with_text(callback, text, reply_markup=balance_keyboard())
    await _safe_answer(callback)


@router.callback_query(F.data == "menu_howto")
async def on_howto(callback: CallbackQuery, db: Database) -> None:
    text = await db.get_howto_text()
    if not text:
        text = (
            "Как пользоваться ботом:\n\n"
            "1. Нажмите 'Создать фото' и выберите категорию.\n"
            "2. Следуйте инструкциям и загрузите фото товара.\n"
            "3. Подтвердите параметры и дождитесь результата."
        )
    await _replace_with_text(callback, text, reply_markup=back_main_keyboard())
    await _safe_answer(callback)


