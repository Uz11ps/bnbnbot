from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import time
from typing import Optional

import httpx
import requests  # для совместимости с generate_text

logger = logging.getLogger(__name__)

# Макс. размер по длинной стороне. Раньше было 960 и давало заметную деградацию.
# Увеличиваем примерно в 2 раза для лучшего качества.
MAX_IMAGE_DIM = 1920
JPEG_QUALITY = 92


def _prepare_image_for_upload(img_bytes: bytes) -> tuple[bytes, str]:
    """Нормализует изображение и возвращает (bytes, mimeType) для Gemini."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        fmt = (img.format or "").upper()
        w, h = img.size

        # Если картинка слишком большая, сжимаем и приводим к JPEG.
        if w > MAX_IMAGE_DIM or h > MAX_IMAGE_DIM:
            scale = min(MAX_IMAGE_DIM / w, MAX_IMAGE_DIM / h, 1.0)
            nw, nh = int(w * scale), int(h * scale)
            img = img.convert("RGB").resize((nw, nh), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
            out = buf.getvalue()
            logger.info("[Gemini] Image resized: %d -> %d bytes", len(img_bytes), len(out))
            return out, "image/jpeg"

        # Без ресайза отправляем с корректным mime.
        if fmt in ("JPEG", "JPG"):
            return img_bytes, "image/jpeg"
        if fmt == "PNG":
            return img_bytes, "image/png"
        if fmt == "WEBP":
            return img_bytes, "image/webp"

        # Неизвестный формат: конвертируем в JPEG.
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
        out = buf.getvalue()
        logger.info("[Gemini] Image converted to JPEG: %d -> %d bytes", len(img_bytes), len(out))
        return out, "image/jpeg"
    except Exception as e:
        logger.warning("[Gemini] Image prepare failed, fallback to JPEG bytes: %s", e)
        return img_bytes, "image/jpeg"


def _compress_image(img_bytes: bytes) -> bytes:
    """Сжимает изображение для ускорения передачи через прокси."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        w, h = img.size
        # Если картинка уже в допустимых размерах — НЕ пережимаем повторно,
        # чтобы не терять качество на лишнем JPEG-кодировании.
        if w <= MAX_IMAGE_DIM and h <= MAX_IMAGE_DIM:
            return img_bytes
        scale = min(MAX_IMAGE_DIM / w, MAX_IMAGE_DIM / h, 1.0)
        nw, nh = int(w * scale), int(h * scale)
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
        out = buf.getvalue()
        logger.info("[Gemini] Image compressed: %d -> %d bytes", len(img_bytes), len(out))
        return out
    except Exception as e:
        logger.warning("[Gemini] Compression failed, using original: %s", e)
        return img_bytes


def _valid_proxy(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        return p.scheme in ("http", "https", "socks5", "socks5h") and bool(p.hostname) and bool(p.port)
    except Exception:
        return False


def _normalize_proxy_for_httpx(raw: str) -> str | None:
    """Приводит прокси к формату http://user:pass@host:port для httpx."""
    if not raw or not raw.strip():
        return None
    raw = raw.strip().split(",")[0].strip()
    from urllib.parse import urlparse

    if raw.startswith("http://") or raw.startswith("https://"):
        try:
            p = urlparse(raw)
            if p.hostname and p.port is not None:
                if p.username is not None and p.password is not None:
                    return f"{p.scheme}://{p.username}:{p.password}@{p.hostname}:{p.port}"
                return f"{p.scheme}://{p.hostname}:{p.port}"
        except (ValueError, TypeError):
            pass
        rest = raw.split("://", 1)[-1].split("/")[0]
        if "@" in rest:
            auth_part, host_part = rest.rsplit("@", 1)
            hp = host_part.split(":")
            if len(hp) == 2 and hp[1].isdigit():
                up = auth_part.split(":", 1)
                user, password = up[0], up[1] if len(up) > 1 else ""
                scheme = raw.split("://", 1)[0]
                return f"{scheme}://{user}:{password}@{hp[0]}:{hp[1]}"
        parts = rest.split(":")
        if len(parts) == 4 and parts[1].isdigit():
            return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        if len(parts) == 3 and parts[2].isdigit():
            return f"http://{parts[0]}:@{parts[1]}:{parts[2]}"
        if len(parts) == 2 and parts[1].isdigit():
            return f"http://{parts[0]}:{parts[1]}"
    else:
        parts = raw.split(":")
        if len(parts) == 4:
            try:
                int(parts[1])
                return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            except ValueError:
                return None
        if len(parts) == 2:
            try:
                int(parts[1])
                return f"http://{parts[0]}:{parts[1]}"
            except ValueError:
                return None
    return None


def _build_proxies(proxy_url: str | None) -> dict:
    if not proxy_url or not _valid_proxy(proxy_url):
        return {}
    return {"http": proxy_url, "https": proxy_url}


def _normalize_image_model_name(raw_model_name: str | None) -> str:
    raw = (raw_model_name or "").strip()
    if not raw:
        return "gemini-3-pro-image-preview"

    alias_map = {
        "gemini-2.5-flash-image-preview": "nano-banana-pro-preview",
        "gemini-2.5-flash-image": "nano-banana-pro-preview",
        "gemini-2.0-flash-preview-image-generation": "nano-banana-pro-preview",
    }
    mapped = alias_map.get(raw, raw)
    if "2.5" in mapped.lower():
        logger.warning("[Gemini] Model '%s' blocked, forced to nano-banana-pro-preview", raw)
        return "nano-banana-pro-preview"
    return mapped




def _generate_sync(
    api_key: str,
    prompt: str,
    images: list[bytes] | bytes,
    ref_image_bytes: bytes | None = None,
    model_name: str | None = None,
    aspect_ratio: str | None = None,
    key_id: int | None = None,
    db_instance = None,
    proxy_url: str | None = None,
) -> Optional[bytes]:
    # По умолчанию используем NANO PRO, но allow fallback по переданному model_name.
    model_used = _normalize_image_model_name(model_name)
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_used}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    parts = []
    
    # Обработка основного изображения или списка изображений
    if isinstance(images, bytes):
        img_list = [images]
    else:
        img_list = images or []
        
    # ЛОГИРОВАНИЕ: Проверка размера первого фото
    if img_list and len(img_list) > 0:
        logger.info("[Gemini] First image size: %.2f KB", len(img_list[0]) / 1024)

    # Сжимаем изображения для ускорения передачи через прокси
    for i, img_bytes in enumerate(img_list, 1):
        if img_bytes:
            prepared_bytes, prepared_mime = _prepare_image_for_upload(img_bytes)
            # Если фото одно — трактуем его как товар/объект (не как сцену)
            if len(img_list) == 1:
                label = "[CLOTHING_ITEM_TO_WEAR_IMAGE]:"
            else:
                if i == 1:
                    label = "[SCENE_AND_MODEL_REFERENCE_IMAGE]:"
                elif i == 2:
                    label = "[CLOTHING_ITEM_TO_WEAR_IMAGE]:"
                else:
                    label = f"Photo {i}:"
            parts.append({"text": label})
            parts.append({
                "inlineData": {
                    "mimeType": prepared_mime,
                    "data": base64.b64encode(prepared_bytes).decode("utf-8"),
                }
            })
            
    if ref_image_bytes:
        ref_prepared_bytes, ref_prepared_mime = _prepare_image_for_upload(ref_image_bytes)
        parts.append({"text": "STYLE_REFERENCE:"})
        parts.append({
            "inlineData": {
                "mimeType": ref_prepared_mime,
                "data": base64.b64encode(ref_prepared_bytes).decode("utf-8"),
            }
        })

    # Промпт и финальные правила
    final_aspect = (aspect_ratio or "1:1").replace("x", ":")
    
    parts.append({"text": prompt})
    
    # Финальная директива, которая идет ПОСЛЕ промпта и имеет наивысший приоритет
    if len(img_list) >= 2:
        parts.append({"text": f"CRITICAL RULE: Generate ONLY ONE image. NO COLLAGES. NO SIDE-BY-SIDE. NO REPETITION. NO COMPARISONS. Output MUST be a single holistic scene. Use [SCENE_AND_MODEL_REFERENCE_IMAGE] as the base and put [CLOTHING_ITEM_TO_WEAR_IMAGE] on the person. Final aspect ratio: {final_aspect}. FILL ENTIRE FRAME."})
    else:
        parts.append({"text": f"CRITICAL RULE: Generate ONLY ONE image. NO COLLAGES. NO SIDE-BY-SIDE. NO REPETITION. NO COMPARISONS. Output MUST be a single holistic image. Use the provided product image as the main reference. Final aspect ratio: {final_aspect}. FILL ENTIRE FRAME."})

    # Для Gemini 3 Pro Image (Imagen 3) используем минимальный конфиг
    generation_config = {
        "temperature": 0.1,
    }
    
    # Пытаемся передать аспект через параметры, но в v1beta для Imagen 3 
    # иногда требуется другой формат или только через промпт.
    # Попробуем передать через aspect_ratio в правильном формате.
    if aspect_ratio:
        # В некоторых версиях API это может быть в корне payload или в config
        # Но если 400 ошибка была на aspectRatio, попробуем передать через промпт более агрессивно
        pass
        generation_config["temperature"] = 0.1
    
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": generation_config,
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    }

    proxy_url_used = proxy_url if _valid_proxy(proxy_url or "") else None
    # Таймауты должны быть согласованы с внешним wait_for, иначе получаем ложные timeout с нашей стороны.
    connect_timeout_s = float(os.getenv("GEMINI_CONNECT_TIMEOUT_SECONDS", "20"))
    read_timeout_s = float(os.getenv("GEMINI_READ_TIMEOUT_SECONDS", "80"))
    write_timeout_s = float(os.getenv("GEMINI_WRITE_TIMEOUT_SECONDS", "40"))
    pool_timeout_s = float(os.getenv("GEMINI_POOL_TIMEOUT_SECONDS", "20"))
    timeout_cfg = httpx.Timeout(
        connect=max(5.0, min(connect_timeout_s, 60.0)),
        read=max(20.0, min(read_timeout_s, 240.0)),
        write=max(10.0, min(write_timeout_s, 120.0)),
        pool=max(5.0, min(pool_timeout_s, 60.0)),
    )

    logger.info(
        "[Gemini] generateContent start: prompt_len=%d, images_count=%d, ref_img=%s, proxy=%s, model=%s",
        len(prompt or ""),
        len(img_list),
        bool(ref_image_bytes),
        (proxy_url_used[:30] + "...") if proxy_url_used else "none",
        model_used,
    )
    if prompt:
        logger.info(f"[Gemini] Промт (первые 500 символов): {prompt[:500]}")
        if len(prompt) > 1000:
            logger.info(f"[Gemini] Промт (последние 500 символов): {prompt[-500:]}")

    resp = None
    last_text = None
    last_exception = None
    is_network_error = False
    try:
        max_attempts = int(os.getenv("GEMINI_REQUEST_MAX_ATTEMPTS", "2"))
    except Exception:
        max_attempts = 2
    max_attempts = max(1, min(max_attempts, 4))
    # На одном маршруте делаем несколько попыток для временных 503/сетевых ошибок.
    for attempt in range(1, max_attempts + 1):
        try:
            is_network_error = False
            use_proxy = proxy_url_used
            with httpx.Client(proxy=use_proxy, timeout=timeout_cfg, verify=True) as client:
                resp = client.post(endpoint, headers=headers, json=payload)
            if resp.status_code == 503:
                last_text = resp.text
                logger.warning("[Gemini] 503 on attempt %d/%d: %s", attempt, max_attempts, (resp.text or '')[:200])
                if attempt < max_attempts:
                    import time as _t
                    _t.sleep(2 * attempt)
                    continue
            if resp.status_code >= 500:
                last_text = resp.text
                logger.warning("[Gemini] 5xx on attempt %d/%d: %s", attempt, max_attempts, (resp.text or '')[:200])
                if attempt < max_attempts:
                    import time as _t
                    _t.sleep(2 * attempt)
                    continue
                continue
            break
        except (httpx.ProxyError, httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            last_exception = e
            last_text = str(e)
            is_network_error = True
            logger.warning("[Gemini] proxy/network error on attempt %d/%d: %s", attempt, max_attempts, e)
            if attempt < max_attempts:
                import time as _t
                _t.sleep(1.5 * attempt)
                continue
        except httpx.HTTPError as e:
            last_exception = e
            last_text = str(e)
            is_network_error = True
            logger.warning("[Gemini] HTTP error on attempt %d/%d: %s", attempt, max_attempts, e)
            if attempt < max_attempts:
                import time as _t
                _t.sleep(1.5 * attempt)
                continue
    
    if resp is None or resp.status_code != 200:
        # Detailed diagnostics for non-200 responses
        status_code = getattr(resp, 'status_code', None) if resp else None
        body_text = (getattr(resp, 'text', None) or last_text or '')
        snippet = (body_text or '')[:1000]
        response_headers = {}
        try:
            # Log useful rate-limit headers when present
            h = getattr(resp, 'headers', {}) or {}
            for k in h.keys():
                lk = str(k).lower()
                if lk.startswith('x-ratelimit') or lk in ('retry-after', 'www-authenticate'):
                    response_headers[k] = h.get(k)
        except Exception:
            pass
        
        # Определяем тип ошибки
        error_type = "unknown"
        error_message = snippet
        snippet_l = snippet.lower()
        if status_code == 429:
            error_type = "429"
            error_message = f"Rate limit exceeded. Проверьте ключ, возможно закончился баланс. {snippet[:200]}"
        elif status_code == 401:
            error_type = "key_invalid"
            error_message = f"Unauthorized API key. {snippet[:200]}"
        elif status_code == 403:
            if "suspended" in snippet_l:
                error_type = "key_suspended"
                error_message = f"API key suspended. {snippet[:200]}"
            elif "api key not valid" in snippet_l or "api_key_invalid" in snippet_l or "invalid api key" in snippet_l:
                error_type = "key_invalid"
                error_message = f"API key invalid. {snippet[:200]}"
            else:
                error_type = "permission_denied"
                error_message = f"Permission denied for API key/project. {snippet[:200]}"
        elif status_code == 400:
            if "user location is not supported" in snippet.lower():
                error_type = "region"
                error_message = "User location is not supported for API use (нужен рабочий прокси для Gemini)."
                # Для обработчика это сетево-региональная проблема, а не "битый промпт".
                is_network_error = True
            else:
                error_type = "400"
                error_message = f"Bad request. Проверьте параметры или ключ. {snippet[:200]}"
        elif "quota" in snippet.lower() or "quota" in str(last_exception).lower():
            error_type = "quota"
            error_message = f"Quota exceeded. Проверьте ключ, возможно закончился баланс. {snippet[:200]}"
        elif is_network_error or status_code is None:
            error_type = "network"
            error_message = f"Network error: {snippet[:200]}"
        
        api_key_preview = api_key[:10] + "..." if len(api_key) > 10 else api_key
        
        # Логируем ошибку с информацией о ключе
        logger.error(
            "[Gemini] ERROR - Key ID: %s, Key Preview: %s, Status: %s, Type: %s, Message: %s, Headers: %s",
            key_id or "N/A", api_key_preview, status_code or "N/A", error_type, error_message[:200], response_headers,
        )
        
        # Записываем ошибку в базу данных если есть db_instance
        # Примечание: record_api_error вызывается из async контекста в handlers/start.py
        # Здесь мы только логируем, запись в БД происходит в обработчике
        
        error_obj = RuntimeError(f"Gemini API error {status_code or 'network'}: {error_message}")
        error_obj.is_proxy_error = is_network_error
        error_obj.status_code = status_code
        error_obj.error_type = error_type
        raise error_obj

    logger.info("[Gemini] Response 200 OK, parsing JSON...")
    data = resp.json()
    logger.info("[Gemini] JSON parsed, candidates: %d", len(data.get("candidates") or []))
    # Извлечение inlineData из ответа
    for cand in data.get("candidates", []) or []:
        content = cand.get("content") or {}
        for part in content.get("parts", []) or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                img_bytes = base64.b64decode(inline["data"])
                logger.info("[Gemini] Image extracted, size: %d bytes", len(img_bytes))
                return img_bytes

    # Если вернулся текст вместо картинки — пробуем взять любой текст для диагностики
    text_parts = []
    for cand in data.get("candidates", []) or []:
        for part in (cand.get("content") or {}).get("parts", []) or []:
            if part.get("text"):
                text_parts.append(part.get("text"))
    if text_parts:
        logger.warning("[Gemini] returned text instead of image: %s", (text_parts[0] or '')[:500])
        raise RuntimeError("Gemini returned text instead of image: " + text_parts[0][:200])

    logger.warning("[Gemini] No inlineData in response, keys: %s", list(data.keys())[:10])
    return None


def is_proxy_error(e: Exception) -> bool:
    """Проверяет, является ли ошибка ошибкой прокси/сети"""
    return getattr(e, 'is_proxy_error', False)


def is_fatal_key_error(e: Exception) -> bool:
    """Фатальные ошибки ключа: ключ нужно вывести из ротации."""
    err_type = str(getattr(e, "error_type", "") or "").lower()
    if err_type in ("key_suspended", "key_invalid", "permission_denied", "key_revoked"):
        return True
    msg = str(e or "").lower()
    fatal_markers = (
        "has been suspended",
        "permission denied",
        "api key not valid",
        "api_key_invalid",
        "invalid api key",
        "consumer invalid",
        "key expired",
        "api key expired",
    )
    return any(marker in msg for marker in fatal_markers)


async def generate_image(
    api_key: str,
    prompt: str,
    image_paths: list[str] = None,
    aspect_ratio: str | None = None,
    quality: str | None = None,
    model_name: str | None = "gemini-3-pro-image-preview",
    key_id: int | None = None,
    db_instance = None,
    images_bytes: list[bytes] = None,
) -> Optional[str]:
    """
    Генерирует изображение через Gemini API.
    Принимает пути к файлам ИЛИ байты изображений напрямую.
    """
    import uuid
    
    # Если переданы пути, читаем их (для обратной совместимости)
    if not images_bytes:
        images_bytes = []
        if image_paths:
            for p in image_paths:
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        images_bytes.append(f.read())
    
    # Модифицируем промпт под качество и аспект если нужно
    final_prompt = prompt
    if aspect_ratio and aspect_ratio != "auto":
        final_prompt += f" Aspect ratio: {aspect_ratio}."
        
    if quality == '4K':
        final_prompt += " High detail, 4k resolution, professional photography."

    # Цепочка моделей для автоматического fallback при 503.
    # Реально доступные image-модели для вашего ключа (проверено через /v1beta/models).
    default_model_chain = [
        "gemini-3-pro-image-preview",
        "nano-banana-pro-preview",
    ]
    model_candidates: list[str] = []
    if model_name:
        model_candidates.append(_normalize_image_model_name(str(model_name)))
    for m in default_model_chain:
        if m not in model_candidates:
            model_candidates.append(m)
        
    # По умолчанию работаем БЕЗ прокси.
    proxy_candidates: list[str | None] = [None]
    # Опционально можно вернуть прокси-режим через env GEMINI_USE_PROXY=1.
    use_proxy_mode = str(os.getenv("GEMINI_USE_PROXY", "")).lower() in ("1", "true", "yes")
    if use_proxy_mode:
        proxy_candidates = []
        if db_instance:
            try:
                # Если прокси привязаны к конкретному ключу — используем их.
                active_proxies = []
                if key_id is not None and hasattr(db_instance, "get_api_key_proxy_urls"):
                    try:
                        active_proxies = await db_instance.get_api_key_proxy_urls(int(key_id))
                    except Exception:
                        active_proxies = []
                if not active_proxies:
                    active_proxies = await db_instance.get_active_proxies_urls()
                if not active_proxies:
                    bot_proxy = await db_instance.get_app_setting("bot_proxy")
                    if bot_proxy:
                        active_proxies = [bot_proxy]
                valid_urls: list[str] = []
                for raw in (active_proxies or []):
                    url = _normalize_proxy_for_httpx(raw)
                    if url and _valid_proxy(url):
                        valid_urls.append(url)
                if valid_urls:
                    seen = set()
                    for u in valid_urls:
                        if u not in seen:
                            seen.add(u)
                            proxy_candidates.append(u)
            except Exception as e:
                logger.error(f"[Gemini] Error getting proxies: {e}")
        else:
            env_proxy = _normalize_proxy_for_httpx(os.getenv("BOT_PROXY", "") or os.getenv("HTTP_PROXY", ""))
            if env_proxy and _valid_proxy(env_proxy):
                proxy_candidates = [env_proxy]
        if not proxy_candidates:
            proxy_candidates = [None]

    import time as _time
    gen_started = _time.monotonic()
    selected_proxy: str | None = None
    selected_model: str | None = None
    result_bytes = None
    last_err: Exception | None = None

    # Пробуем несколько маршрутов (direct/прокси) и fallback по моделям.
    try:
        import random as _random
        _random.shuffle(proxy_candidates)
    except Exception:
        pass
    max_proxy_attempts = min(5, len(proxy_candidates))
    for current_model in model_candidates:
        selected_model = current_model
        logger.info("[Gemini] Trying model: %s", current_model)
        for proxy_url in proxy_candidates[:max_proxy_attempts]:
            selected_proxy = proxy_url
            route_label = f"proxy: {proxy_url[:50]}..." if proxy_url else "direct"
            logger.info("[Gemini] Using route: %s", route_label)
            try:
                result_bytes = await asyncio.to_thread(
                    _generate_sync,
                    api_key,
                    final_prompt,
                    images_bytes,
                    None,  # ref_image_bytes (not used here)
                    current_model,
                    aspect_ratio,
                    key_id,
                    db_instance,
                    proxy_url,
                )
                break
            except Exception as e:
                last_err = e
                if is_fatal_key_error(e):
                    raise
                msg_l = str(e).lower()
                status_code = getattr(e, "status_code", None)
                is_503 = status_code == 503 or " 503" in msg_l or "high demand" in msg_l or "unavailable" in msg_l
                if is_503:
                    logger.warning("[Gemini] Model %s unavailable (503), switching model.", current_model)
                    break
                logger.warning("[Gemini] Route attempt failed for model %s: %s", current_model, e)
                continue
        if result_bytes is not None:
            break

    if result_bytes is None and last_err is not None:
        raise last_err

    # Если генерация с прокси заняла слишком долго — только логируем (без авто-деактивации).
    gen_elapsed = _time.monotonic() - gen_started
    if selected_proxy and gen_elapsed >= 180:
        logger.warning(
            "[Gemini] Slow generation via proxy=%s model=%s elapsed=%.1fs",
            selected_proxy[:50],
            selected_model or "unknown",
            gen_elapsed,
        )
    
    if result_bytes:
        # Сжимаем для быстрой загрузки в Telegram (через прокси может быть медленно)
        result_bytes = _compress_image(result_bytes)
        _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(_base, "data")
        os.makedirs(data_dir, exist_ok=True)
        out_path = os.path.join(data_dir, f"result_{uuid.uuid4()}.jpg")
        with open(out_path, "wb") as f:
            f.write(result_bytes)
        return f"data/{os.path.basename(out_path)}"
        
    return None


def _generate_text_sync(
    api_key: str,
    prompt: str,
    image_bytes: bytes,
    proxy_url: str | None = None,
) -> Optional[str]:
    """Получает текстовый ответ от Gemini на основе изображения и промта"""
    # Используем gemini-2.0-flash для быстрого анализа текста
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    parts = [
        {"text": prompt},
        {
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            }
        },
    ]

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.1, "topK": 32, "topP": 1, "maxOutputTokens": 8192},
    }

    proxies = _build_proxies(proxy_url) if proxy_url and _valid_proxy(proxy_url) else {}
    session = requests.Session()
    session.trust_env = False

    logger.info(
        "[Gemini] text generation start: prompt_len=%d, img=%d, proxy=%s",
        len(prompt or ""),
        len(image_bytes or b""),
        proxies or "none",
    )

    resp = None
    last_text = None
    for attempt in range(1, 4):
        try:
            resp = session.post(endpoint, headers=headers, json=payload, timeout=90, proxies=proxies or None)
            if resp.status_code >= 500:
                last_text = resp.text
                logger.warning("[Gemini] 5xx on attempt %d: %s", attempt, (resp.text or '')[:200])
                import time as _t
                _t.sleep(2 * attempt)
                continue
            break
        except requests.RequestException as e:
            last_text = str(e)
            logger.warning("[Gemini] network error on attempt %d: %s", attempt, e)
            import time as _t
            _t.sleep(2 * attempt)
    if resp is None or resp.status_code != 200:
        body_text = (getattr(resp, 'text', None) or last_text or '')
        snippet = (body_text or '')[:1000]
        logger.error("[Gemini] text error status=%s body=%s", getattr(resp, 'status_code', 'n/a'), snippet)
        raise RuntimeError(f"Gemini API error {getattr(resp,'status_code', 'n/a')}: {snippet}")

    data = resp.json()
    text_parts = []
    for cand in data.get("candidates", []) or []:
        for part in (cand.get("content") or {}).get("parts", []) or []:
            if part.get("text"):
                text_parts.append(part.get("text"))
    if text_parts:
        return "\n".join(text_parts)
    return None


async def generate_text(
    api_key: str,
    prompt: str,
    image_bytes: bytes,
    db_instance = None,
) -> Optional[str]:
    """Асинхронная обёртка для получения текстового ответа от Gemini"""
    selected_proxy = None
    use_proxy_mode = str(os.getenv("GEMINI_USE_PROXY", "")).lower() in ("1", "true", "yes")
    if use_proxy_mode and db_instance:
        try:
            active_proxies = await db_instance.get_active_proxies_urls()
            if active_proxies:
                import random
                valid_urls = []
                for raw in active_proxies:
                    url = _normalize_proxy_for_httpx(raw)
                    if url and _valid_proxy(url):
                        valid_urls.append(url)
                if valid_urls:
                    selected_proxy = random.choice(valid_urls)
        except Exception:
            pass

    return await asyncio.to_thread(_generate_text_sync, api_key, prompt, image_bytes, selected_proxy)
