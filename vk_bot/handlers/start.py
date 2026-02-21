import logging
import os
import time
import asyncio
from dataclasses import dataclass, field

import httpx
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler
from vkbottle.bot import Message
from vkbottle.dispatch.rules import ABCRule
from vkbottle.exception_factory.base_exceptions import VKAPIError

from bot.db import Database
from bot.gemini import generate_image
from bot.strings import get_string
from vk_bot.context import get_db
from vk_bot.keyboards import (
    back_to_main_keyboard,
    language_keyboard,
    main_menu_keyboard,
    marketplace_keyboard,
    settings_keyboard,
    terms_keyboard,
)

router = BotLabeler()
logger = logging.getLogger(__name__)

STATE_IDLE = "idle"
STATE_WAIT_PHOTO = "wait_photo"
STATE_WAIT_PROMPT = "wait_prompt"
STATE_CONSTRUCTOR_STEP = "constructor_step"
STATE_CONSTRUCTOR_CONFIRM = "constructor_confirm"
STATE_TTL_SECONDS = 20 * 60


@dataclass
class VkUserState:
    stage: str = STATE_IDLE
    category: str | None = None
    image_bytes_list: list[bytes] | None = None
    constructor_category_id: int | None = None
    constructor_steps: list[tuple] = field(default_factory=list)
    current_step_index: int = 0
    current_step_id: int | None = None
    current_step_key: str | None = None
    waiting_custom_for: str | None = None
    step_values: dict[str, str] = field(default_factory=dict)
    step_labels: dict[str, str] = field(default_factory=dict)
    step_photos: dict[str, list[bytes]] = field(default_factory=dict)
    model_choices: dict[int, tuple[int, str, int, str | None]] = field(default_factory=dict)
    last_incoming_msg_id: int | None = None
    updated_at: float = 0.0


_states: dict[int, VkUserState] = {}


class IsPrivate(ABCRule):
    async def check(self, message: Message) -> bool:
        return message.peer_id == message.from_id


def _norm(text: str | None) -> str:
    return (text or "").strip().lower()


def _is_start(text: str) -> bool:
    return text in {"/start", "start", "старт"}


def _is_help(text: str) -> bool:
    return text in {"/help", "help", "помощь"}


async def _ensure_user(db: Database, user_id: int) -> None:
    await db.upsert_user(user_id=user_id, username=None, first_name=None, last_name=None, referrer_id=None)


def _get_state(user_id: int) -> VkUserState:
    st = _states.get(user_id)
    if st is None:
        st = VkUserState(stage=STATE_IDLE, image_bytes_list=None, updated_at=time.time())
        _states[user_id] = st
        return st
    if (time.time() - st.updated_at) > STATE_TTL_SECONDS:
        st = VkUserState(stage=STATE_IDLE, updated_at=time.time())
        _states[user_id] = st
    st.updated_at = time.time()
    return st


def _reset_state(user_id: int) -> None:
    _states[user_id] = VkUserState(stage=STATE_IDLE, category=None, image_bytes_list=None, updated_at=time.time())


async def _reply(message: Message, text: str, keyboard: str | None = None) -> bool:
    """
    Безопасная отправка: если в группе выключен Chat Bot feature (VK error 912),
    автоматически отправляем сообщение без клавиатуры.
    """
    # Важно: используем один и тот же random_id для retries, чтобы VK не дублировал сообщения.
    # Если первая отправка фактически дошла, но VK вернул ошибку на клавиатуру — вторая отправка
    # с тем же random_id будет проигнорирована.
    rid = int(time.time() * 1000)
    try:
        if keyboard:
            await message.ctx_api.messages.send(peer_id=message.peer_id, random_id=rid, message=text, keyboard=keyboard)
        else:
            await message.ctx_api.messages.send(peer_id=message.peer_id, random_id=rid, message=text)
        return True
    except VKAPIError as e:
        err = str(e).lower()
        if (
            "chat bot feature" in err
            or "error_code=912" in err
            or "error_code=911" in err
            or "keyboard format is invalid" in err
            or "too much rows" in err
        ):
            # Retry without keyboard (same random_id)
            await message.ctx_api.messages.send(peer_id=message.peer_id, random_id=rid, message=text)
            return False
        else:
            raise
    except Exception as e:
        # fallback по тексту ошибки для совместимости с разными версиями SDK
        if "chat bot feature" in str(e).lower():
            await message.ctx_api.messages.send(peer_id=message.peer_id, random_id=rid, message=text)
            return False
        else:
            raise


async def _get_lang(db: Database, user_id: int) -> str:
    lang = await db.get_user_language(user_id)
    if lang not in {"ru", "en", "vi"}:
        return "ru"
    return lang


async def _send_main_menu(message: Message, db: Database, user_id: int) -> None:
    lang = await _get_lang(db, user_id)
    ok = await _reply(message, get_string("main_menu_title", lang), keyboard=main_menu_keyboard(lang))
    if not ok:
        if lang == "en":
            fallback = (
                "VK buttons are disabled in community settings.\n"
                "Use text commands:\n"
                "- Profile\n- Top up balance\n- Support\n- Instructions\n- Settings\n"
                "- NORMAL GENERATION\n- Marketplaces"
            )
        elif lang == "vi":
            fallback = (
                "Nút VK đang bị tắt trong cài đặt cộng đồng.\n"
                "Hãy dùng lệnh văn bản:\n"
                "- Hồ sơ\n- Nạp tiền\n- Hỗ trợ kỹ thuật\n- Hướng dẫn\n- Cài đặt\n"
                "- TẠO ẢNH THƯỜNG\n- Cho sàn thương mại"
            )
        else:
            fallback = (
                "Кнопки VK выключены в настройках сообщества.\n"
                "Используйте текстовые команды:\n"
                "- Профиль\n- Пополнить баланс\n- Тех.поддержка\n- Инструкция\n- Настройки\n"
                "- ОБЫЧНАЯ ГЕНЕРАЦИЯ\n- Для маркетплейсов"
            )
        await _reply(message, fallback)


async def _send_marketplace_menu(message: Message, db: Database, user_id: int) -> None:
    lang = await _get_lang(db, user_id)
    try:
        enabled = await db.list_categories_enabled()
    except Exception:
        enabled = {}
    await _reply(message, get_string("marketplace_menu", lang), keyboard=marketplace_keyboard(enabled, lang))


async def _get_category_prefix_prompt(db: Database, category: str | None) -> str:
    if not category:
        return ""
    key_map = {
        "presets": "presets_prompt",
        "random": "random_prompt",
        "random_other": "random_other_prompt",
        "infographic_clothing": "infographic_clothing_prompt",
        "infographic_other": "infographic_other_prompt",
        "storefront": "storefront_prompt",
        "whitebg": "whitebg_prompt",
        "own": "own_prompt",
        "own_variant": "own_variant_prompt",
    }
    setting_key = key_map.get(category)
    if not setting_key:
        return ""
    return (await db.get_app_setting(setting_key, "") or "").strip()


async def _send_agreement(message: Message, db: Database, user_id: int) -> None:
    lang = await _get_lang(db, user_id)
    agreement_text = await db.get_app_setting("agreement_text", "") or ""
    body = agreement_text.strip() or get_string("agreement", lang)
    await _reply(message, body, keyboard=back_to_main_keyboard(lang))


async def _send_support(message: Message, db: Database, user_id: int) -> None:
    lang = await _get_lang(db, user_id)
    contact = (await db.get_app_setting("support_contact", "") or "").strip()
    if not contact:
        contact = "@bnbslow"
    await _reply(message, f"{get_string('menu_support', lang)}\n\n{contact}", keyboard=back_to_main_keyboard(lang))


async def _send_howto(message: Message, db: Database, user_id: int) -> None:
    lang = await _get_lang(db, user_id)
    howto_text = (await db.get_app_setting("howto_text", "") or "").strip()
    body = howto_text or get_string("how_to", lang)
    await _reply(message, body, keyboard=back_to_main_keyboard(lang))


async def _send_profile(message: Message, db: Database, user_id: int) -> None:
    lang = await _get_lang(db, user_id)
    balance = await db.get_user_balance(user_id)
    price = await db.get_user_generation_price(user_id)
    text = get_string("profile_info", lang).format(id=user_id, balance=balance, price=price)
    await _reply(message, text, keyboard=back_to_main_keyboard(lang))


async def _send_topup(message: Message, db: Database, user_id: int) -> None:
    lang = await _get_lang(db, user_id)
    balance = await db.get_user_balance(user_id)
    price = await db.get_user_generation_price(user_id)
    text = get_string("top_up_info", lang).format(id=user_id, balance=balance, price=price)
    contact = (await db.get_app_setting("support_contact", "") or "").strip() or "@bnbslow"
    await _reply(message, f"{text}\n{contact}", keyboard=back_to_main_keyboard(lang))


async def _send_proxy(message: Message, db: Database, user_id: int) -> None:
    lang = await _get_lang(db, user_id)
    running = (await db.get_app_setting("mtproxy_running", "0") or "0") == "1"
    secret = (await db.get_app_setting("mtproxy_secret", "") or "").strip()
    port = (await db.get_app_setting("mtproxy_port", "8888") or "8888").strip()
    server_ip = (await db.get_app_setting("mtproxy_server_ip", "") or "").strip()
    if not server_ip:
        import os

        server_ip = os.getenv("MTPROXY_SERVER_IP", "130.49.148.147")

    if not running or not secret:
        await _reply(message, get_string("proxy_not_available", lang), keyboard=back_to_main_keyboard(lang))
        return

    secret_hex = secret.replace("-", "")
    if secret_hex.startswith("dd") and len(secret_hex) == 34:
        secret_hex = secret_hex[2:]
    if len(secret_hex) != 32:
        await _reply(message, get_string("proxy_not_available", lang), keyboard=back_to_main_keyboard(lang))
        return

    link = f"tg://proxy?server={server_ip}&port={port}&secret=dd{secret_hex}"
    text = f"{get_string('proxy_title', lang)}\n\n{get_string('proxy_link', lang)}\n{link}"
    await _reply(message, text, keyboard=back_to_main_keyboard(lang))


def _extract_photo_urls(message: Message) -> list[str]:
    urls: list[str] = []
    attachments = getattr(message, "attachments", None) or []
    for att in attachments:
        photo = getattr(att, "photo", None)
        if photo is None and getattr(att, "type", None) == "photo":
            photo = getattr(att, "value", None) or getattr(att, "photo", None)
        if photo is None:
            continue

        sizes = getattr(photo, "sizes", None) or []
        best_url = None
        best_area = -1
        for s in sizes:
            url = getattr(s, "url", None) or getattr(s, "src", None)
            w = getattr(s, "width", 0) or 0
            h = getattr(s, "height", 0) or 0
            area = int(w) * int(h)
            if url and area >= best_area:
                best_area = area
                best_url = url
        if best_url:
            urls.append(best_url)
    return urls


async def _download_photo_bytes_list(message: Message) -> list[bytes]:
    urls = _extract_photo_urls(message)
    if not urls:
        return []
    timeout = httpx.Timeout(connect=20.0, read=60.0, write=20.0, pool=20.0)
    images: list[bytes] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and resp.content:
                    images.append(resp.content)
            except Exception:
                continue
    return images


def _kb_options(options: list[str], include_back: bool, include_skip: bool, include_create: bool, lang: str) -> str:
    keyboard = Keyboard(one_time=False, inline=False)
    # VK ограничивает размер клавиатуры, поэтому показываем только часть опций кнопками.
    # Полный список вариантов всегда есть в тексте сообщения, пользователь может ответить номером.
    max_buttons = 6
    for opt in options[:max_buttons]:
        keyboard.add(Text(opt), color=KeyboardButtonColor.PRIMARY)
        keyboard.row()
    if include_skip:
        keyboard.add(Text(get_string("skip", lang)), color=KeyboardButtonColor.SECONDARY)
        keyboard.row()
    if include_create:
        keyboard.add(Text("✅ Создать"), color=KeyboardButtonColor.POSITIVE)
        keyboard.row()
    if include_back:
        keyboard.add(Text(get_string("back", lang)), color=KeyboardButtonColor.NEGATIVE)
    return keyboard.get_json()


def _market_category_by_text(text: str, lang: str) -> str | None:
    mapping = {
        _norm(get_string("cat_presets", lang)): "presets",
        _norm(get_string("cat_random", lang)): "random",
        _norm(get_string("cat_random_other", lang)): "random_other",
        _norm(get_string("cat_infographic_clothing", lang)): "infographic_clothing",
        _norm(get_string("cat_infographic_other", lang)): "infographic_other",
        _norm(get_string("cat_storefront", lang)): "storefront",
        _norm(get_string("cat_whitebg", lang)): "whitebg",
        _norm(get_string("cat_own", lang)): "own",
        _norm(get_string("cat_own_variant", lang)): "own_variant",
    }
    return mapping.get(text)


def _should_skip_step(step_key: str, values: dict[str, str]) -> bool:
    if step_key == "age" and values.get("has_person") == "no":
        return True
    if step_key == "gender" and values.get("has_person") == "no":
        return True
    if step_key == "rand_location_indoor" and values.get("rand_loc_group") != "indoor":
        return True
    if step_key == "rand_location_outdoor" and values.get("rand_loc_group") != "outdoor":
        return True
    return False


async def _load_model_photo_bytes(raw: str | None) -> bytes | None:
    if not raw:
        return None
    # Telegram file_id в VK недоступен напрямую
    if raw.startswith("AgAC"):
        return None
    try:
        if raw.startswith("http://") or raw.startswith("https://"):
            timeout = httpx.Timeout(connect=20.0, read=60.0, write=20.0, pool=20.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                r = await client.get(raw)
                if r.status_code == 200 and r.content:
                    return r.content
            return None
        import os

        p = raw if os.path.isabs(raw) else os.path.join("/app", raw.lstrip("/"))
        if os.path.exists(p):
            with open(p, "rb") as f:
                return f.read()
    except Exception:
        return None
    return None


async def _start_constructor_flow(message: Message, db: Database, user_id: int, lang: str, category_key: str) -> None:
    cat = await db.get_category_by_key(category_key)
    if not cat:
        await _reply(message, "Категория не найдена.", keyboard=back_to_main_keyboard(lang))
        return
    steps = await db.list_steps(int(cat[0]))
    if not steps:
        await _reply(message, "Для категории не настроены шаги.", keyboard=back_to_main_keyboard(lang))
        return

    st = _get_state(user_id)
    st.stage = STATE_CONSTRUCTOR_STEP
    st.category = category_key
    st.constructor_category_id = int(cat[0])
    st.constructor_steps = steps
    st.current_step_index = 0
    st.current_step_id = None
    st.current_step_key = None
    st.waiting_custom_for = None
    st.step_values = {}
    st.step_labels = {}
    st.step_photos = {}
    st.model_choices = {}
    st.updated_at = time.time()
    await _show_constructor_step(message, db, user_id, lang)


async def _show_constructor_step(message: Message, db: Database, user_id: int, lang: str) -> None:
    st = _get_state(user_id)
    while st.current_step_index < len(st.constructor_steps):
        step_id, step_key, _q, input_type, is_optional, _order = st.constructor_steps[st.current_step_index]
        step_key = str(step_key)
        if _should_skip_step(step_key, st.step_values):
            st.current_step_index += 1
            continue

        st.current_step_id = int(step_id)
        st.current_step_key = step_key
        question = (await db.get_step_text(int(step_id), lang) or "").strip() or str(_q or "Введите значение")
        optional = int(is_optional) == 1

        if input_type == "buttons":
            opts = await db.list_step_options_localized(int(step_id), lang)
            option_texts = [str(o[1]) for o in opts]
            numbered = "\n".join([f"{i}. {t}" for i, t in enumerate(option_texts, 1)])
            text = f"{question}\n\n{numbered}\n\nОтветьте номером или текстом варианта."
            await _reply(message, text, keyboard=_kb_options(option_texts, include_back=True, include_skip=optional, include_create=False, lang=lang))
            return

        if input_type == "model_select":
            cloth = st.step_values.get("gender")
            if cloth == "unisex":
                cloth = "all"
            count = await db.count_models("presets", cloth)
            choices: dict[int, tuple[int, str, int, str | None]] = {}
            labels: list[str] = []
            for idx in range(min(count, 20)):
                model = await db.get_model_by_index("presets", cloth, idx)
                if not model:
                    continue
                num = idx + 1
                choices[num] = model
                labels.append(f"{num}. {model[1]}")
            st.model_choices = choices
            if not choices:
                await _reply(message, "Нет доступных моделей для этой категории.", keyboard=_kb_options([], include_back=True, include_skip=False, include_create=False, lang=lang))
                return
            await _reply(message, f"{question}\n\n" + "\n".join(labels) + "\n\nОтветьте номером модели.", keyboard=_kb_options(labels, include_back=True, include_skip=False, include_create=False, lang=lang))
            return

        if input_type == "photo":
            await _reply(message, question, keyboard=_kb_options([], include_back=True, include_skip=optional, include_create=False, lang=lang))
            return

        await _reply(message, question, keyboard=_kb_options([], include_back=True, include_skip=optional, include_create=False, lang=lang))
        return

    await _show_constructor_confirmation(message, db, user_id, lang)


async def _show_constructor_confirmation(message: Message, db: Database, user_id: int, lang: str) -> None:
    st = _get_state(user_id)
    lines = ["Проверьте данные перед генерацией:\n"]
    for step in st.constructor_steps:
        _id, step_key, question, _input_type, _opt, _ord = step
        key = str(step_key)
        if key in st.step_labels:
            lines.append(f"- {question}: {st.step_labels[key]}")
        elif key in st.step_values:
            lines.append(f"- {question}: {st.step_values[key]}")
    lines.append("\nНажмите «✅ Создать» или «⬅️ Назад».")
    st.stage = STATE_CONSTRUCTOR_CONFIRM
    await _reply(message, "\n".join(lines), keyboard=_kb_options([], include_back=True, include_skip=False, include_create=True, lang=lang))


async def _constructor_back(message: Message, db: Database, user_id: int, lang: str) -> None:
    st = _get_state(user_id)
    if st.stage == STATE_CONSTRUCTOR_CONFIRM:
        st.stage = STATE_CONSTRUCTOR_STEP
        st.current_step_index = max(0, len(st.constructor_steps) - 1)
        await _show_constructor_step(message, db, user_id, lang)
        return
    st.current_step_index = max(0, st.current_step_index - 1)
    st.stage = STATE_CONSTRUCTOR_STEP
    await _show_constructor_step(message, db, user_id, lang)


async def _constructor_advance(message: Message, db: Database, user_id: int, lang: str) -> None:
    st = _get_state(user_id)
    st.current_step_index += 1
    st.stage = STATE_CONSTRUCTOR_STEP
    st.current_step_id = None
    st.current_step_key = None
    await _show_constructor_step(message, db, user_id, lang)


async def _build_constructor_prompt(db: Database, st: VkUserState) -> str:
    base = await _get_category_prefix_prompt(db, st.category)
    # Совместимость по ключам с TG prompt-builder
    values = dict(st.step_values)
    if "rand_height" in values and "height_cm" not in values:
        values["height_cm"] = values["rand_height"]
    if "rand_width" in values and "width_cm" not in values:
        values["width_cm"] = values["rand_width"]
    if "rand_length" in values and "length_cm" not in values:
        values["length_cm"] = values["rand_length"]
    if "info_angle" in values and "view" not in values:
        values["view"] = values["info_angle"]
    if st.category == "random":
        values["random_mode"] = True
    if st.category == "random_other":
        values["random_other_mode"] = True
    if st.category in {"infographic_clothing", "infographic_other"}:
        values["infographic_mode"] = True
    if st.category == "storefront":
        values["storefront_mode"] = True
    if st.category == "own":
        values["own_mode"] = True
    if st.category == "presets":
        values["is_preset"] = True
    values["category"] = st.category
    values["aspect"] = "1:1"

    # Используем тот же builder, что в Telegram, чтобы форма из конструктора работала одинаково
    from bot.handlers.start import _build_final_prompt as tg_build_final_prompt

    tg_prompt = (await tg_build_final_prompt(values, db) or "").strip()

    # Если в форме есть поле со свободным текстом (свой вариант), добавляем его в конец промпта.
    extra_keys = ("prompt", "custom_prompt", "user_prompt", "extra_prompt", "note", "notes", "comment", "description")
    extra = ""
    for k in extra_keys:
        v = (values.get(k) or "").strip()
        if v:
            extra = v
            break
    if extra:
        tg_prompt = f"{tg_prompt}\n\nДополнительно: {extra}".strip()

    return tg_prompt or base


async def _collect_constructor_images(db: Database, st: VkUserState) -> list[bytes]:
    photos: list[bytes] = []
    if st.category == "own_variant":
        # Совместимость: в админке ключи шагов могли быть как в TG (own_bg_photo_id/own_product_photo_id)
        bg_keys = ["bg_photo", "own_bg_photo_id", "own_bg_photo", "background_photo", "background", "bg"]
        product_keys = ["photo", "own_product_photo_id", "own_product_photo", "product_photo", "product", "item_photo"]
        bg: list[bytes] = []
        product: list[bytes] = []
        for k in bg_keys:
            cand = st.step_photos.get(k) or []
            if cand:
                bg = cand[:1]
                break
        for k in product_keys:
            cand = st.step_photos.get(k) or []
            if cand:
                product = cand[:1]
                break
        photos.extend(bg + product)
        return [p for p in photos if p]

    if st.category in {"presets", "storefront"} and st.step_values.get("model_select_photo"):
        model_bytes = await _load_model_photo_bytes(st.step_values.get("model_select_photo"))
        if model_bytes:
            photos.append(model_bytes)

    for step in st.constructor_steps:
        key = str(step[1])
        if key in st.step_photos:
            photos.extend(st.step_photos.get(key, []))
    return [p for p in photos if p]


async def _run_constructor_generation(message: Message, db: Database, user_id: int, lang: str) -> None:
    st = _get_state(user_id)
    images = await _collect_constructor_images(db, st)
    if not images:
        await _reply(message, "Не хватает фото для генерации.", keyboard=back_to_main_keyboard(lang))
        return

    prompt = await _build_constructor_prompt(db, st)
    if not prompt:
        await _reply(message, "Не удалось сформировать промпт.", keyboard=back_to_main_keyboard(lang))
        return

    balance = await db.get_user_balance(user_id)
    price = await db.get_user_generation_price(user_id)
    if balance < price:
        await _send_topup(message, db, user_id)
        _reset_state(user_id)
        return

    key_id, api_key = await _pick_api_key(db)
    if not api_key:
        await _reply(message, get_string("api_limit_reached", lang), keyboard=back_to_main_keyboard(lang))
        _reset_state(user_id)
        return

    await _reply(message, get_string("gen_in_progress", lang))
    try:
        try:
            total_timeout_s = int(os.getenv("GENERATION_TOTAL_TIMEOUT_SECONDS", "30"))
        except Exception:
            total_timeout_s = 30
        total_timeout_s = max(15, min(total_timeout_s, 60))
        result_path = await asyncio.wait_for(
            generate_image(
                api_key=api_key,
                prompt=prompt,
                images_bytes=images,
                aspect_ratio="1x1",
                key_id=key_id,
                db_instance=db,
            ),
            timeout=total_timeout_s,
        )
        if not result_path:
            await _reply(message, get_string("gen_no_image", lang), keyboard=back_to_main_keyboard(lang))
            _reset_state(user_id)
            return
        await db.subtract_user_balance(user_id=user_id, amount=price, reason="generation")
        if key_id is not None:
            try:
                await db.record_api_usage(key_id)
            except Exception:
                pass
        # HTTPS на домене может быть не настроен; отдаем рабочую http-ссылку.
        base_url = (await db.get_app_setting("public_base_url", "http://g-box.space") or "http://g-box.space").strip().rstrip("/")
        result_url = f"{base_url}/{result_path}".replace("//data", "/data")
        await _reply(message, f"{get_string('gen_success', lang)}\n\n{result_url}", keyboard=back_to_main_keyboard(lang))
    except Exception:
        logger.exception("VK constructor generation failed for user_id=%s", user_id)
        await _reply(message, get_string("gen_error_contact_support", lang), keyboard=back_to_main_keyboard(lang))
    finally:
        _reset_state(user_id)


async def _handle_constructor_message(message: Message, db: Database, user_id: int, lang: str) -> bool:
    st = _get_state(user_id)
    if st.stage not in {STATE_CONSTRUCTOR_STEP, STATE_CONSTRUCTOR_CONFIRM}:
        return False

    text_raw = (message.text or "").strip()
    text = _norm(text_raw)
    back_text = _norm(get_string("back", lang))
    skip_text = _norm(get_string("skip", lang))

    if text in {back_text, _norm(get_string("back_main", lang))}:
        await _constructor_back(message, db, user_id, lang)
        return True

    if st.stage == STATE_CONSTRUCTOR_CONFIRM:
        if text in {"создать", "✅ создать", "generate"}:
            await _run_constructor_generation(message, db, user_id, lang)
            return True
        await _show_constructor_confirmation(message, db, user_id, lang)
        return True

    # Если предыдущая кнопка требовала "свой вариант" — сохраняем текст в текущий step_key
    if st.waiting_custom_for:
        step_key = st.waiting_custom_for
        if not text_raw:
            await _reply(message, "Введите текст для этого шага.", keyboard=_kb_options([], include_back=True, include_skip=False, include_create=False, lang=lang))
            return True
        st.step_values[step_key] = text_raw
        st.step_labels[step_key] = text_raw
        st.waiting_custom_for = None
        await _constructor_advance(message, db, user_id, lang)
        return True

    if st.current_step_id is None or st.current_step_key is None:
        await _show_constructor_step(message, db, user_id, lang)
        return True

    step_key = st.current_step_key
    step = st.constructor_steps[st.current_step_index]
    input_type = str(step[3])
    optional = int(step[4]) == 1

    if optional and text == skip_text:
        st.step_values[step_key] = ""
        st.step_labels[step_key] = "Пропущено"
        await _constructor_advance(message, db, user_id, lang)
        return True

    if input_type == "photo":
        images = await _download_photo_bytes_list(message)
        if not images:
            await _reply(message, "Пришлите фото для этого шага.", keyboard=_kb_options([], include_back=True, include_skip=optional, include_create=False, lang=lang))
            return True
        st.step_photos[step_key] = images
        st.step_values[step_key] = "photo_uploaded"
        st.step_labels[step_key] = "Фото загружено"
        await _constructor_advance(message, db, user_id, lang)
        return True

    if input_type == "model_select":
        model = None
        if text_raw.isdigit():
            model = st.model_choices.get(int(text_raw))
        if not model:
            for idx, item in st.model_choices.items():
                if text == _norm(f"{idx}. {item[1]}") or text == _norm(item[1]):
                    model = item
                    break
        if not model:
            await _reply(message, "Выберите модель по номеру или названию.")
            return True
        model_id, model_name, prompt_id, photo_ref = model
        st.step_values["model_id"] = str(model_id)
        st.step_values["prompt_id"] = str(prompt_id)
        st.step_values["model_select_photo"] = photo_ref or ""
        st.step_values[step_key] = str(model_id)
        st.step_labels[step_key] = model_name
        await _constructor_advance(message, db, user_id, lang)
        return True

    if input_type == "buttons":
        opts = await db.list_step_options_localized(int(st.current_step_id), lang)
        selected = None
        if text_raw.isdigit():
            idx = int(text_raw) - 1
            if 0 <= idx < len(opts):
                selected = opts[idx]
        if not selected:
            for o in opts:
                if text == _norm(str(o[1])):
                    selected = o
                    break
        if not selected:
            await _reply(message, "Выберите один из вариантов кнопкой, номером или текстом.")
            return True
        _opt_id, opt_text, opt_value, _order, custom_prompt = selected
        custom_prompt = (custom_prompt or "").strip()
        if custom_prompt:
            st.waiting_custom_for = step_key
            await _reply(message, custom_prompt, keyboard=_kb_options([], include_back=True, include_skip=False, include_create=False, lang=lang))
            return True
        st.step_values[step_key] = str(opt_value)
        st.step_labels[step_key] = str(opt_text)
        await _constructor_advance(message, db, user_id, lang)
        return True

    if not text_raw:
        await _reply(message, "Введите значение для этого шага.")
        return True
    st.step_values[step_key] = text_raw
    st.step_labels[step_key] = text_raw
    await _constructor_advance(message, db, user_id, lang)
    return True


async def _pick_api_key(db: Database) -> tuple[int | None, str | None]:
    rows = await db.list_api_keys()
    for row in rows:
        # (id, token, is_active, priority, ...)
        if int(row[2]) == 1:
            return int(row[0]), str(row[1])
    return None, None


async def _start_generation_mode(
    message: Message,
    db: Database,
    user_id: int,
    lang: str,
    category: str | None = None,
) -> None:
    st = _get_state(user_id)
    st.stage = STATE_WAIT_PHOTO
    st.category = category
    st.image_bytes_list = None
    st.updated_at = time.time()
    await _reply(message, get_string("upload_photo", lang), keyboard=back_to_main_keyboard(lang))


async def _handle_generation_photo_step(message: Message, db: Database, user_id: int, lang: str) -> bool:
    st = _get_state(user_id)
    if st.stage != STATE_WAIT_PHOTO:
        return False
    images = await _download_photo_bytes_list(message)
    if not images:
        await _reply(message, get_string("upload_photo", lang), keyboard=back_to_main_keyboard(lang))
        return True
    st.image_bytes_list = images
    st.stage = STATE_WAIT_PROMPT
    st.updated_at = time.time()
    await _reply(message, get_string("enter_prompt", lang), keyboard=back_to_main_keyboard(lang))
    return True


async def _handle_generation_prompt_step(message: Message, db: Database, user_id: int, lang: str) -> bool:
    st = _get_state(user_id)
    if st.stage != STATE_WAIT_PROMPT:
        return False

    prompt = (message.text or "").strip()
    if not prompt:
        await _reply(message, get_string("enter_prompt", lang), keyboard=back_to_main_keyboard(lang))
        return True
    if len(prompt) > 2500:
        await _reply(message, get_string("enter_prompt_error", lang), keyboard=back_to_main_keyboard(lang))
        return True
    if not st.image_bytes_list:
        st.stage = STATE_WAIT_PHOTO
        await _reply(message, get_string("upload_photo", lang), keyboard=back_to_main_keyboard(lang))
        return True

    balance = await db.get_user_balance(user_id)
    price = await db.get_user_generation_price(user_id)
    if balance < price:
        await _send_topup(message, db, user_id)
        _reset_state(user_id)
        return True

    key_id, api_key = await _pick_api_key(db)
    if not api_key:
        await _reply(message, get_string("api_limit_reached", lang), keyboard=back_to_main_keyboard(lang))
        _reset_state(user_id)
        return True

    await _reply(message, get_string("gen_in_progress", lang))
    try:
        category_prompt = await _get_category_prefix_prompt(db, st.category)
        final_prompt = f"{category_prompt}\n\n{prompt}".strip() if category_prompt else prompt
        try:
            total_timeout_s = int(os.getenv("GENERATION_TOTAL_TIMEOUT_SECONDS", "30"))
        except Exception:
            total_timeout_s = 30
        total_timeout_s = max(15, min(total_timeout_s, 60))
        result_path = await asyncio.wait_for(
            generate_image(
                api_key=api_key,
                prompt=final_prompt,
                images_bytes=st.image_bytes_list,
                aspect_ratio="1x1",
                key_id=key_id,
                db_instance=db,
            ),
            timeout=total_timeout_s,
        )
        if not result_path:
            await _reply(message, get_string("gen_no_image", lang), keyboard=back_to_main_keyboard(lang))
            _reset_state(user_id)
            return True

        await db.subtract_user_balance(user_id=user_id, amount=price, reason="generation")
        if key_id is not None:
            try:
                await db.record_api_usage(key_id)
            except Exception:
                pass

        # HTTPS на домене может быть не настроен; отдаем рабочую http-ссылку.
        base_url = (await db.get_app_setting("public_base_url", "http://g-box.space") or "http://g-box.space").strip().rstrip("/")
        result_url = f"{base_url}/{result_path}".replace("//data", "/data")
        await _reply(
            message,
            f"{get_string('gen_success', lang)}\n\n{result_url}",
            keyboard=back_to_main_keyboard(lang),
        )
    except Exception:
        logger.exception("VK generation failed for user_id=%s", user_id)
        await _reply(message, get_string("gen_error_contact_support", lang), keyboard=back_to_main_keyboard(lang))
    finally:
        _reset_state(user_id)
    return True


@router.message(IsPrivate())
async def handle_private_message(message: Message) -> None:
    db: Database = get_db()
    user_id = int(message.from_id)

    try:
        # VK иногда может прислать одно и то же входящее сообщение повторно.
        # Дедупим по message.id / conversation_message_id на короткой памяти.
        st = _get_state(user_id)
        incoming_id = getattr(message, "id", None) or getattr(message, "conversation_message_id", None)
        if incoming_id is not None and st.last_incoming_msg_id == int(incoming_id):
            return
        if incoming_id is not None:
            st.last_incoming_msg_id = int(incoming_id)

        await _ensure_user(db, user_id)
        lang = await _get_lang(db, user_id)

        if await db.get_user_blocked(user_id):
            await _reply(message, get_string("user_blocked", lang))
            return

        text = _norm(message.text)

        # До принятия соглашения пропускаем только старт/принятие/просмотр соглашения
        accepted = await db.get_user_accepted_terms(user_id)
        accept_text = _norm(get_string("accept_terms", lang))
        agreement_text = _norm(get_string("agreement", lang))
        if not accepted:
            if text == accept_text:
                await db.set_terms_acceptance(user_id, True)
                await _send_main_menu(message, db, user_id)
                return
            if text == agreement_text:
                await _send_agreement(message, db, user_id)
                return
            if _is_start(text):
                ok = await _reply(message, get_string("start_welcome", lang), keyboard=terms_keyboard(lang))
                if not ok:
                    await _reply(
                        message,
                        f"Напишите текстом:\n- {get_string('accept_terms', lang)}\n- {get_string('agreement', lang)}",
                    )
                return

            ok = await _reply(message, get_string("start_welcome", lang), keyboard=terms_keyboard(lang))
            if not ok:
                await _reply(
                    message,
                    f"Напишите текстом:\n- {get_string('accept_terms', lang)}\n- {get_string('agreement', lang)}",
                )
            return

        # Базовые команды
        if _is_start(text):
            _reset_state(user_id)
            await _send_main_menu(message, db, user_id)
            return
        if _is_help(text):
            _reset_state(user_id)
            await _send_howto(message, db, user_id)
            return

        # В режиме конструктора ответы пользователя обрабатываем раньше обычного меню
        if await _handle_constructor_message(message, db, user_id, lang):
            return

        # Меню по локализованным кнопкам
        if text == _norm(get_string("create_normal_gen", lang)):
            await _start_generation_mode(message, db, user_id, lang, category=None)
            return
        if text == _norm(get_string("menu_market", lang)):
            _reset_state(user_id)
            await _send_marketplace_menu(message, db, user_id)
            return
        market_cat = _market_category_by_text(text, lang)
        if market_cat:
            await _start_constructor_flow(message, db, user_id, lang, market_cat)
            return
        if text == _norm(get_string("menu_settings", lang)):
            _reset_state(user_id)
            await _reply(message, get_string("menu_settings", lang), keyboard=settings_keyboard(lang))
            return
        if text == _norm(get_string("menu_profile", lang)):
            _reset_state(user_id)
            await _send_profile(message, db, user_id)
            return
        if text == _norm(get_string("buy_plan", lang)) or text == _norm(get_string("menu_subscription", lang)):
            _reset_state(user_id)
            await _send_topup(message, db, user_id)
            return
        if text == _norm(get_string("menu_support", lang)):
            _reset_state(user_id)
            await _send_support(message, db, user_id)
            return
        if text == _norm(get_string("menu_howto", lang)):
            _reset_state(user_id)
            await _send_howto(message, db, user_id)
            return
        if text == _norm(get_string("agreement", lang)):
            _reset_state(user_id)
            await _send_agreement(message, db, user_id)
            return
        if text == _norm(get_string("menu_proxy", lang)):
            _reset_state(user_id)
            await _send_proxy(message, db, user_id)
            return

        # Смена языка
        if text == _norm(get_string("select_lang", lang)):
            _reset_state(user_id)
            await _reply(message, get_string("select_lang", lang), keyboard=language_keyboard(lang))
            return
        if text == _norm(get_string("lang_ru", lang)):
            await db.set_user_language(user_id, "ru")
            _reset_state(user_id)
            await _send_main_menu(message, db, user_id)
            return
        if text == _norm(get_string("lang_en", lang)):
            await db.set_user_language(user_id, "en")
            _reset_state(user_id)
            await _send_main_menu(message, db, user_id)
            return
        if text == _norm(get_string("lang_vi", lang)):
            await db.set_user_language(user_id, "vi")
            _reset_state(user_id)
            await _send_main_menu(message, db, user_id)
            return

        # Назад в меню
        if text == _norm(get_string("back_main", lang)) or text == _norm(get_string("back", lang)):
            _reset_state(user_id)
            await _send_main_menu(message, db, user_id)
            return

        # Шаги генерации
        if await _handle_generation_photo_step(message, db, user_id, lang):
            return
        if await _handle_generation_prompt_step(message, db, user_id, lang):
            return

        # Пустой текст вне активного FSM шага — возвращаем главное меню
        if not text:
            await _send_main_menu(message, db, user_id)
            return

        # Пока остальные ветки Telegram-бота не перенесены, даем стабильный fallback
        await _send_main_menu(message, db, user_id)
    except Exception:
        logger.exception("VK handler error for user_id=%s", user_id)
        try:
            await _reply(message, "Временная ошибка. Попробуйте еще раз через несколько секунд.")
        except Exception:
            pass
