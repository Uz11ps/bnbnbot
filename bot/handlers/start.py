from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import BufferedInputFile
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from bot.keyboards import (
    terms_keyboard,
    main_menu_keyboard,
    balance_keyboard,
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
)
from bot.db import Database
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
    plus_loc = State()
    plus_season = State()
    plus_vibe = State()
    category = State()
    cloth = State()
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
async def on_child_gender(callback: CallbackQuery, state: FSMContext) -> None:
    gender_key = callback.data.split(":", 1)[1]
    await state.update_data(gender=("мальчик" if gender_key == "boy" else "девочка"))
    await _replace_with_text(callback, "Введите рост ребенка в см (например: 130):")
    await state.set_state(CreateForm.waiting_height)
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
    await message.answer(WELCOME_TEXT, reply_markup=terms_keyboard())


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
            await _replace_with_text(callback, text, reply_markup=create_product_keyboard_dynamic(statuses))
    except Exception:
        # на случай отсутствия настроек — показать стандартное меню
        await _replace_with_text(callback, text, reply_markup=create_product_keyboard())
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
    text = (
        "Пришлите фото, которое вам нравится.\n\n"
        "Бот проанализирует модель, позу, свет и фон, чтобы создать похожее изображение с вашим товаром.\n\n"
        "Нужно понимать, что эта функция не создаёт точную копию человека или фона. Похожесть составляет примерно 50–60%. Если вы ожидаете 100% совпадения, возврат средств в таких ситуациях не предусмотрен.

За исключением несходства вашей одежды"
    )
    await _replace_with_text(callback, text)
    await state.set_state(CreateForm.waiting_ref_photo)
    await _safe_answer(callback)


# Own Background Variant Flow
@router.callback_query(F.data == "create_cat:own_variant")
async def on_create_own_variant(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if await db.get_maintenance():
        settings = load_settings()
        if callback.from_user.id not in (settings.admin_ids or []):
            await _safe_answer(callback, "Идут техработы. Пожалуйста, попробуйте позже.", show_alert=True)
            return
    if not await db.get_category_enabled("own_variant"):
        await _safe_answer(callback, "Категория временно недоступна", show_alert=True)
        return
    await state.clear()
    await state.update_data(category="own_variant")
    await _replace_with_text(callback, "📸 Пожалуйста, пришлите фотографию фона, который вам нравится.\n\nБот перенесет ваш товар на этот фон.")
    await state.set_state(CreateForm.waiting_own_bg_photo)
    await _safe_answer(callback)


@router.message(CreateForm.waiting_own_bg_photo, F.photo)
async def on_own_bg_photo(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    await state.update_data(own_bg_photo_id=photo_id)
    await message.answer("📸 Теперь пришлите фотографию вашего товара.")
    await state.set_state(CreateForm.waiting_own_product_photo)


@router.message(CreateForm.waiting_own_product_photo, F.photo)
async def on_own_product_photo(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    await state.update_data(own_product_photo_id=photo_id)
    await message.answer("🖼️ Выберите формат изображения:", reply_markup=aspect_ratio_keyboard())
    await state.set_state(CreateForm.waiting_aspect)


@router.callback_query(CreateForm.waiting_aspect, F.data.startswith("form_aspect:"))
async def on_own_aspect(callback: CallbackQuery, state: FSMContext) -> None:
    aspect = callback.data.split(":", 1)[1]
    await state.update_data(aspect=aspect)
    
    data = await state.get_data()
    # Собираем текст подтверждения для own_variant
    parts = [
        "📋 Проверьте выбранные параметры:\n\n",
        "📦 **Категория**: 🖼️ Свой вариант ФОНА\n",
        f"🖼️ **Формат**: {aspect.replace('x', ':')}\n\n",
        "Все верно? Нажмите кнопку ниже для генерации."
    ]
    await _replace_with_text(callback, "".join(parts), reply_markup=form_generate_keyboard())
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
            await message.answer("❌ Ошибка генерации.\n\nПопробуйте другое изображение или начните заново.")
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
        await message.answer("❌ Ошибка генерации.\n\nПопробуйте другое изображение или начните заново.")


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


@router.callback_query(F.data == "back_step", CreateForm.waiting_own_bg_photo)
async def on_back_from_own_bg(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    lang = await db.get_user_language(callback.from_user.id)
    await on_menu_create(callback, db)

@router.callback_query(F.data == "back_step", CreateForm.waiting_own_product_photo)
async def on_back_from_own_product(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await on_create_own_variant(callback, state, db)

@router.callback_query(F.data == "back_step", CreateForm.waiting_aspect)
async def on_back_from_own_aspect(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    if data.get("category") == "own_variant":
        await _replace_with_text(callback, "📸 Пожалуйста, пришлите фотографию вашего товара.")
        await state.set_state(CreateForm.waiting_own_product_photo)
    else:
        # fallback for other flows
        pass


@router.callback_query(F.data == "form_generate")
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
    category = data.get("category")
    price_tenths = await db.get_category_price(category)
    
    # проверяем баланс с учётом десятых
    frac = await db.get_user_fraction(user_id)
    total_tenths = balance * 10 + frac
    if total_tenths < price_tenths:
        need_str = f"{price_tenths/10:.1f}"
        await _safe_answer(callback, f"Недостаточно генераций (нужно {need_str})", show_alert=True)
        return

    # Подстановка параметров в промт
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
    # Вставляем телосложение, если это взрослые и не обувь
    size_text = data.get('size') or ""
    if data.get("own_mode"):
        # Собираем специализированный промт для собственного референса (финальный), с админ-настройкой
        own_length = (data.get("own_length") or "")
        own_sleeve = (data.get("own_sleeve") or "")
        model_description = data.get("own_model_description") or ""
        base = await db.get_own_prompt3() or (
            "Create a professional high-quality fashion photo. The outfit must be an exact visual copy of the clothes shown in the attached reference image. The shape, proportions, structure, texture, pattern, and material must match each other exactly. Reproduce the seams, lines, and construction without rethinking. Fabrics should look freshly ironed, realistic, with soft natural folds. Observe photorealistic lighting and natural color balance.\n\n"
            "The color should be exactly the same as in the photo that I attached.\n\n"
            "Model:\n\n"
            "{Сюда нужно поставить полученное описание от Gemini}\n\n"
            "Clothing length (parameters are given in centimeters): {Длина изделия}\n\n"
            "Sleeve length (parameters are given in centimeters): {Длина рукавов}\n\n"
            "If some parts of the model's body remain naked (for example, the torso, legs, or feet), automatically add suitable clothing that matches the style and season of the main garment. Additional items should be harmonious in style and slightly different in color — without sharp contrasts. Shoes are selected according to the season and the general style of the image (for example, do not use summer options for a winter look).\n\n"
            "Photo angle / framing (choose one): Big Angle\n\n"
            "– If Foreshortening = Close-up → focus primarily on the details of clothing (for shoes: from feet to knees).\n\n"
            "– If Foreshortening = Full-length → vertical framing from head to toe so that the model is fully visible, not too far from the camera.\n\n"
            "Additional rules:\n\n"
            "* The hands should remain visible; the model can lightly touch the hair.\n\n"
            "* Reproduce the outfit exactly as shown in the picture — the geometry, the direction of the seams, the patterns and the materials must be identical.\n\n"
            "* Lighting: soft natural/ daytime, photorealistic, without harsh orange tones.\n\n"
            "* Do not choose a specific type of shoe — it can be different (boots, sneakers, flip-flops, etc.).\n\n"
            "* If item = shoes, add realistic small footprints in the snow if the area is snowy."
        )
        prompt_filled = base.replace("{Сюда нужно поставить полученное описание от Gemini}", model_description).replace("{Длина изделия}", own_length).replace("{Длина рукавов}", own_sleeve)
    elif data.get("random_mode"):
        # Собираем промт на основе выбранных параметров
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
            if loc == 'custom':
                custom = (data.get('rand_location_custom') or '').strip()
                if custom:
                    parts.append(f"Съёмка {custom}. ")
            else:
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
        prompt_filled = (base_random + "\n\n" + ''.join(parts)).strip()
    else:
        # Поддержка ракурса для белого фона и общего шаблона
        view_key = data.get("view")
        view_word = {"back": "сзади", "front": "спереди", "side": "сбоку"}.get(view_key, "спереди")
        prompt_filled = (
            (prompt_text or "")
            .replace("{размер}", size_text)
            .replace("{рост}", str(data.get("height", "")))
            .replace("{длина изделия}", str(data.get("length", "")))
            .replace("{возраст}", age_text)
            .replace("{длина рукав}", sleeve_text)
            .replace("{сзади/спереди}", view_word)
        )
        # Для whitebg гарантируем явное указание ракурса и белого фона
        if (data.get("category") == "whitebg"):
            extra = f" Ракурс: {view_word}. Белый фон, студийный свет."
            if prompt_filled.strip():
                prompt_filled = (prompt_filled.strip() + extra)
            else:
                prompt_filled = ("Профессиональное фото одежды на модели. " + extra).strip()
        # Плюс-режим: добавим локацию/сезон/вайб в конец промта
        if data.get('plus_mode'):
            loc_map = {
                "outdoor":"на улице",
                "wall":"возле стены",
                "car":"возле машины",
                "park":"в парке",
                "bench":"у лавочки",
                "restaurant":"возле ресторана",
                "studio":"в фотостудии",
            }
            season_map = {"winter":"зима","summer":"лето","spring":"весна","autumn":"осень"}
            vibe_map = {"decor":"с декором элементами","plain":"без декора","newyear":"новогодний","normal":"обычный"}
            extra_parts: list[str] = []
            if data.get('plus_loc'):
                extra_parts.append(f" Съёмка {loc_map.get(data.get('plus_loc'))}.")
            if data.get('plus_season'):
                extra_parts.append(f" Сезон: {season_map.get(data.get('plus_season'))}.")
            if data.get('plus_vibe'):
                extra_parts.append(f" Вайб: {vibe_map.get(data.get('plus_vibe'))}.")
            if extra_parts:
                prompt_filled = prompt_filled + " " + ''.join(extra_parts)
    await _replace_with_text(callback, "Запуск генерации...", reply_markup=None)
    await _safe_answer(callback)
    progress_msg = await callback.message.answer("⏳ Генерация изображения…")
    stop_event = asyncio.Event()
    asyncio.create_task(_run_generation_progress(callback.bot, callback.message.chat.id, progress_msg.message_id, stop_event))

    # Загрузка фото(ов)
    if data.get("category") == "own_variant":
        bg_id = data.get("own_bg_photo_id")
        prod_id = data.get("own_product_photo_id")
        if not bg_id or not prod_id:
            await _replace_with_text(callback, "Фото не найдены. Начните заново.", reply_markup=back_main_keyboard())
            await _safe_answer(callback)
            return
        
        # background image
        bg_file = await callback.bot.get_file(bg_id)
        bg_f = await callback.bot.download_file(bg_file.file_path)
        reference_bytes = bg_f.read()
        
        # product image
        prod_file = await callback.bot.get_file(prod_id)
        prod_f = await callback.bot.download_file(prod_file.file_path)
        image_bytes = prod_f.read()
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
        error_text = "у сервиса ошибки с api. скоро всё решим\n\nОшибка: Нет активных API ключей"
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
            # own_mode: не используем референсное фото, только описание модели в промте
            ref_bytes = reference_bytes if not data.get("own_mode") else None
            logger.info(f"[form_generate] Попытка генерации с ключом {key_id}, own_mode={data.get('own_mode')}, prompt_len={len(prompt_filled)}, image_size={len(image_bytes)}, ref_size={len(ref_bytes) if ref_bytes else 0}")
            result_bytes = await generate_image(token, prompt_filled, image_bytes, ref_bytes)
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
        error_text = f"у сервиса ошибки с api. скоро всё решим\n\nОшибка: {str(last_error)[:200]}"
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
        error_text = "у сервиса ошибки с api. скоро всё решим"
        if last_error:
            error_text += f"\n\nОшибка: {str(last_error)[:200]}"
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
            reason = f"generation_{category}"
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
        if category == "own_variant" or data.get("own_mode"):
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
        await message.answer(f"Ошибка генерации: {e}")
        await state.clear()
        return
    if not result_bytes:
        await message.answer("Генерация не вернула изображение")
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


