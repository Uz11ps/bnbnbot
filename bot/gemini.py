from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
from typing import Optional

import httpx
import requests  # для совместимости с generate_text

logger = logging.getLogger(__name__)

# Макс. размер по длинной стороне (уменьшает payload для медленных прокси)
MAX_IMAGE_DIM = 960
JPEG_QUALITY = 85


def _compress_image(img_bytes: bytes) -> bytes:
    """Сжимает изображение для ускорения передачи через прокси."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        w, h = img.size
        if w <= MAX_IMAGE_DIM and h <= MAX_IMAGE_DIM:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
            return buf.getvalue()
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


def _build_proxies(proxy_url: str | None) -> dict:
    if not proxy_url or not _valid_proxy(proxy_url):
        return {}
    return {"http": proxy_url, "https": proxy_url}


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
    # Используем gemini-3-pro-image-preview (NANO PRO) для всех категорий
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent?key={api_key}"
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
            compressed = _compress_image(img_bytes)
            if i == 1:
                label = "[SCENE_AND_MODEL_REFERENCE_IMAGE]:"
            elif i == 2:
                label = "[CLOTHING_ITEM_TO_WEAR_IMAGE]:"
            else:
                label = f"Photo {i}:"
            parts.append({"text": label})
            parts.append({
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": base64.b64encode(compressed).decode("utf-8"),
                }
            })
            
    if ref_image_bytes:
        parts.append({"text": "STYLE_REFERENCE:"})
        parts.append({
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": base64.b64encode(ref_image_bytes).decode("utf-8"),
            }
        })

    # Промпт и финальные правила
    final_aspect = (aspect_ratio or "1:1").replace("x", ":")
    
    parts.append({"text": prompt})
    
    # Финальная директива, которая идет ПОСЛЕ промпта и имеет наивысший приоритет
    parts.append({"text": f"CRITICAL RULE: Generate ONLY ONE image. NO COLLAGES. NO SIDE-BY-SIDE. NO REPETITION. NO COMPARISONS. Output MUST be a single holistic scene. Use [SCENE_AND_MODEL_REFERENCE_IMAGE] as the base and put [CLOTHING_ITEM_TO_WEAR_IMAGE] on the person. Final aspect ratio: {final_aspect}. FILL ENTIRE FRAME."})

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
    timeout_cfg = httpx.Timeout(connect=30.0, read=600.0)  # 10 мин на чтение

    logger.info(
        "[Gemini] NANO PRO (v1beta generateContent) start: prompt_len=%d, images_count=%d, ref_img=%s, proxy=%s, model=gemini-3-pro-image-preview",
        len(prompt or ""),
        len(img_list),
        bool(ref_image_bytes),
        (proxy_url_used[:30] + "...") if proxy_url_used else "none",
    )
    if prompt:
        logger.info(f"[Gemini] Промт (первые 500 символов): {prompt[:500]}")
        if len(prompt) > 1000:
            logger.info(f"[Gemini] Промт (последние 500 символов): {prompt[-500:]}")

    resp = None
    last_text = None
    last_exception = None
    is_network_error = False
    for attempt in range(1, 3):
        try:
            is_network_error = False
            use_proxy = None if attempt == 1 else proxy_url_used
            if attempt == 2 and proxy_url_used:
                logger.info("[Gemini] Retry WITH proxy (direct failed)")
            with httpx.Client(proxy=use_proxy, timeout=timeout_cfg, verify=True) as client:
                resp = client.post(endpoint, headers=headers, json=payload)
            if resp.status_code >= 500:
                last_text = resp.text
                logger.warning("[Gemini] 5xx on attempt %d: %s", attempt, (resp.text or '')[:200])
                import time as _t
                _t.sleep(1)
                continue
            break
        except (httpx.ProxyError, httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            last_exception = e
            last_text = str(e)
            is_network_error = True
            logger.warning("[Gemini] proxy/network error on attempt %d: %s", attempt, e)
            if attempt == 1 and proxy_url_used:
                continue
            import time as _t
            _t.sleep(1)
        except httpx.HTTPError as e:
            last_exception = e
            last_text = str(e)
            is_network_error = True
            logger.warning("[Gemini] HTTP error on attempt %d: %s", attempt, e)
            if attempt == 1 and proxy_url_used:
                continue
            import time as _t
            _t.sleep(1)
    
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
        if status_code == 429:
            error_type = "429"
            error_message = f"Rate limit exceeded. Проверьте ключ, возможно закончился баланс. {snippet[:200]}"
        elif status_code == 400:
            error_type = "400"
            error_message = f"Bad request. Проверьте параметры или ключ. {snippet[:200]}"
        elif "quota" in snippet.lower() or "quota" in str(last_exception).lower():
            error_type = "quota"
            error_message = f"Quota exceeded. Проверьте ключ, возможно закончился баланс. {snippet[:200]}"
        elif is_network_error or status_code is None:
            error_type = "network"
            error_message = f"Proxy/Network error: {snippet[:200]}"
        
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

    data = resp.json()
    # Извлечение inlineData из ответа
    for cand in data.get("candidates", []) or []:
        content = cand.get("content") or {}
        for part in content.get("parts", []) or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])  

    # Если вернулся текст вместо картинки — пробуем взять любой текст для диагностики
    text_parts = []
    for cand in data.get("candidates", []) or []:
        for part in (cand.get("content") or {}).get("parts", []) or []:
            if part.get("text"):
                text_parts.append(part.get("text"))
    if text_parts:
        logger.warning("[Gemini] returned text instead of image: %s", (text_parts[0] or '')[:500])
        raise RuntimeError("Gemini returned text instead of image: " + text_parts[0][:200])

    return None


def is_proxy_error(e: Exception) -> bool:
    """Проверяет, является ли ошибка ошибкой прокси/сети"""
    return getattr(e, 'is_proxy_error', False)


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
        
    # Выбираем прокси из БД если есть db_instance
    selected_proxy = None
    if db_instance:
        try:
            active_proxies = await db_instance.get_active_proxies_urls()
            if active_proxies:
                import random
                selected_proxy = random.choice(active_proxies)
                logger.info(f"[Gemini] Using proxy from DB: {selected_proxy[:30]}...")
        except Exception as e:
            logger.error(f"[Gemini] Error getting proxies from DB: {e}")

    # Вызываем синхронную обертку
    result_bytes = await asyncio.to_thread(
        _generate_sync, 
        api_key, 
        final_prompt, 
        images_bytes, 
        None, # ref_image_bytes (not used here)
        model_name, 
        aspect_ratio, 
        key_id, 
        db_instance,
        selected_proxy
    )
    
    if result_bytes:
        # Сохраняем результат во временный файл
        out_path = f"data/result_{uuid.uuid4()}.jpg"
        os.makedirs("data", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(result_bytes)
        return out_path
        
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

    proxies = _build_proxies(proxy_url)
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
    if db_instance:
        try:
            active_proxies = await db_instance.get_active_proxies_urls()
            if active_proxies:
                import random
                selected_proxy = random.choice(active_proxies)
        except Exception: pass

    return await asyncio.to_thread(_generate_text_sync, api_key, prompt, image_bytes, selected_proxy)
