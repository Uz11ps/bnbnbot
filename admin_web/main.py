from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, BackgroundTasks, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import aiosqlite
import os
import asyncio
import httpx
import json
import shutil
from aiogram import Bot
from bot.config import load_settings
from bot.strings import get_string
from datetime import datetime, timedelta
import re
from contextlib import asynccontextmanager

# --- Настройки путей ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Используем тот же DATABASE_URL, что и бот, чтобы админка и бот читали одну БД
db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db").strip()
if "sqlite+aiosqlite:///" in db_url:
    db_path = db_url.replace("sqlite+aiosqlite:///", "")
else:
    db_path = "data/bot.db"
if not os.path.isabs(db_path) and not db_path.startswith("/app"):
    db_path = os.path.join(BASE_DIR, db_path)
DB_PATH = db_path
# Создаем папку если ее нет (на случай если volume не примонтирован)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads", "models")
STATIC_DIR = os.path.join(BASE_DIR, "admin_web", "static")

async def run_migrations(db: aiosqlite.Connection):
    # Проверка и добавление недостающих колонок
    async with db.execute("PRAGMA table_info(subscriptions)") as cur:
        cols = [row[1] for row in await cur.fetchall()]
    if cols and "plan_id" not in cols:
        try:
            await db.execute("ALTER TABLE subscriptions ADD COLUMN plan_id INTEGER")
            await db.commit()
        except Exception as e:
            print(f"Migration error (subscriptions.plan_id): {e}")

    if cols and "individual_api_key" not in cols:
        try:
            await db.execute("ALTER TABLE subscriptions ADD COLUMN individual_api_key TEXT")
            await db.commit()
        except Exception as e:
            print(f"Migration error (subscriptions.individual_api_key): {e}")

    async with db.execute("PRAGMA table_info(users)") as cur:
        cols = [row[1] for row in await cur.fetchall()]
    if cols and "trial_used" not in cols:
        try:
            await db.execute("ALTER TABLE users ADD COLUMN trial_used INTEGER NOT NULL DEFAULT 0")
            await db.commit()
        except Exception as e:
            print(f"Migration error (users.trial_used): {e}")

    # Миграция для step_options (custom_prompt)
    async with db.execute("PRAGMA table_info(step_options)") as cur:
        cols = [row[1] for row in await cur.fetchall()]
    if cols and "custom_prompt" not in cols:
        try:
            await db.execute("ALTER TABLE step_options ADD COLUMN custom_prompt TEXT")
            await db.commit()
            print("Migration: Added custom_prompt to step_options")
        except Exception as e:
            print(f"Migration error (step_options.custom_prompt): {e}")

    # Гарантируем системные кнопки в библиотеке и наличие шага выбора модели
    try:
        # Системная категория кнопок
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Системные",)) as cur:
            row = await cur.fetchone()
        if row:
            sys_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Системные",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Системные",)) as cur:
                sys_cat_id = (await cur.fetchone())[0]

        system_buttons = [
            ("Свой вариант", "custom", "Введите ваш вариант текста:"),
            ("Пропустить", "skip", None),
            ("Назад", "back", None),
        ]
        for text, value, prompt in system_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (sys_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (sys_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library system buttons): {e}")

    try:
        # Библиотека вопросов: выбор модели
        async with db.execute("SELECT id FROM library_steps WHERE step_key=?", ("model_select",)) as cur:
            if not await cur.fetchone():
                await db.execute(
                    "INSERT INTO library_steps (step_key, question_text, input_type) VALUES (?, ?, ?)",
                    ("model_select", "💃 Выберите модель:", "model_select")
                )
                await db.commit()
    except Exception as e:
        print(f"Migration error (library_steps.model_select): {e}")

    try:
        # Категория пресетов: добавить шаг выбора модели, если его нет
        async with db.execute("SELECT id FROM categories WHERE key=?", ("presets",)) as cur:
            cat_row = await cur.fetchone()
        if cat_row:
            presets_id = cat_row[0]
            async with db.execute(
                "SELECT id FROM steps WHERE category_id=? AND step_key=?",
                (presets_id, "model_select")
            ) as cur:
                exists = await cur.fetchone()
            if not exists:
                await db.execute(
                    "UPDATE steps SET order_index = order_index + 1 WHERE category_id=? AND order_index >= 13",
                    (presets_id,)
                )
                await db.execute(
                    "INSERT INTO steps (category_id, step_key, question_text, input_type, is_optional, order_index) VALUES (?, ?, ?, ?, 0, 13)",
                    (presets_id, "model_select", "💃 Выберите модель (пресет):", "model_select")
                )
                await db.commit()
    except Exception as e:
        print(f"Migration error (presets.model_select): {e}")

    async with db.execute("PRAGMA table_info(subscription_plans)") as cur:
        p_cols = [row[1] for row in await cur.fetchall()]
    
    for lang_code in ["ru", "en", "vi"]:
        col_name = f"description_{lang_code}"
        if p_cols and col_name not in p_cols:
            try:
                await db.execute(f"ALTER TABLE subscription_plans ADD COLUMN {col_name} TEXT")
                await db.commit()
                print(f"Migration: Added {col_name} to subscription_plans")
            except Exception as e:
                print(f"Migration error (subscription_plans.{col_name}): {e}")


def _normalize_placeholder_label(text: str, fallback: str) -> str:
    if not text:
        return fallback
    # Убираем эмодзи и пунктуацию, оставляем буквы/цифры/пробелы
    clean = re.sub(r"[^0-9A-Za-zА-Яа-яЁё ]+", "", text).strip()
    # Убираем типовые префиксы
    for prefix in ("Выберите ", "Введите ", "Пришлите ", "Загрузите "):
        if clean.lower().startswith(prefix.lower()):
            clean = clean[len(prefix):].strip()
            break
    return clean or fallback


async def _get_prompt_placeholders(db: aiosqlite.Connection) -> list[dict]:
    placeholders: list[dict] = []
    async with db.execute(
        "SELECT id, step_key, question_text FROM steps ORDER BY step_key"
    ) as cur:
        rows = await cur.fetchall()
    for step_id, step_key, question_text in rows:
        label = _normalize_placeholder_label(question_text, step_key)
        placeholders.append({
            "id": step_id,
            "label": label,
            "token": f"{{{label}}}"
        })
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique = []
    for p in placeholders:
        key = p["token"]
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique

async def cleanup_old_history():
    """Фоновая задача для очистки истории старше 7 дней"""
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Находим записи старше 7 дней
                async with db.execute("SELECT pid, input_paths, result_path FROM generation_history WHERE created_at < datetime('now', '-7 days')") as cur:
                    old_records = await cur.fetchall()
                
                if old_records:
                    print(f"Cleanup: Found {len(old_records)} old generations to delete")
                    for pid, inps_json, res_path in old_records:
                        # Удаляем файлы
                        if res_path and os.path.exists(res_path):
                            try: os.remove(res_path)
                            except: pass
                        if inps_json:
                            try:
                                inps = json.loads(inps_json)
                                for p in inps:
                                    if p and os.path.exists(p):
                                        try: os.remove(p)
                                        except: pass
                            except: pass
                        
                        # Удаляем из БД
                        await db.execute("DELETE FROM generation_history WHERE pid=?", (pid,))
                    await db.commit()
        except Exception as e:
            print(f"Cleanup history error: {e}")
        
        # Спим 1 час перед следующей проверкой
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "data", "history"), exist_ok=True)
    
    # Запуск миграций при старте
    async with aiosqlite.connect(DB_PATH) as db:
        await run_migrations(db)
        
        async with db.execute("PRAGMA table_info(generation_history)") as cur:
            h_cols = [row[1] for row in await cur.fetchall()]
        if h_cols:
            if "input_paths" not in h_cols:
                try:
                    await db.execute("ALTER TABLE generation_history ADD COLUMN input_paths TEXT")
                    await db.commit()
                except Exception as e: print(f"Migration error (history.input_paths): {e}")
            if "result_path" not in h_cols:
                try:
                    await db.execute("ALTER TABLE generation_history ADD COLUMN result_path TEXT")
                    await db.commit()
                except Exception as e: print(f"Migration error (history.result_path): {e}")
    
    # Запуск очистки в фоне
    asyncio.create_task(cleanup_old_history())
        
    yield

app = FastAPI(title="AI-ROOM Admin Panel", lifespan=lifespan)

# --- Статика ---
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/data", StaticFiles(directory=os.path.join(BASE_DIR, "data")), name="data")

# --- Шаблоны ---
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "admin_web", "templates"))
templates.env.filters["from_json"] = json.loads
security = HTTPBasic()

try:
    settings = load_settings()
except Exception as e:
    print(f"Error loading settings: {e}")
    class MockSettings:
        bot_token = "MOCK"
        class MockProxy:
            def as_url(self): return None
        proxy = MockProxy()
    settings = MockSettings()

ADMIN_USER = "123"
ADMIN_PASS = "123"

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if os.path.exists(os.path.join(BASE_DIR, "data", "uploads")):
    app.mount("/uploads", StaticFiles(directory=os.path.join(BASE_DIR, "data", "uploads")), name="uploads")

# --- Зависимости ---
def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USER)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

async def get_db():
    db = await aiosqlite.connect(DB_PATH, timeout=30)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

CATEGORIES = ["presets", "female", "male", "child", "storefront", "whitebg", "random", "random_other", "own", "own_variant", "infographic_clothing", "infographic_other"]

@app.get("/models/delete/{model_id}")
async def delete_model(model_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT prompt_id, photo_file_id FROM models WHERE id=?", (model_id,)) as cur:
        row = await cur.fetchone()
        if row:
            prompt_id, photo_path = row
            await db.execute("DELETE FROM models WHERE id=?", (model_id,))
            await db.execute("DELETE FROM prompts WHERE id=?", (prompt_id,))
            if photo_path and photo_path.startswith("data/"):
                full_path = os.path.join(BASE_DIR, photo_path)
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except Exception as e:
                        print(f"Error removing file {full_path}: {e}")
            await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

@app.post("/models/delete_bulk")
async def delete_bulk_models(model_ids: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    ids = [int(x) for x in model_ids.split(",") if x.isdigit()]
    for model_id in ids:
        async with db.execute("SELECT prompt_id, photo_file_id FROM models WHERE id=?", (model_id,)) as cur:
            row = await cur.fetchone()
            if row:
                prompt_id, photo_path = row
                await db.execute("DELETE FROM models WHERE id=?", (model_id,))
                await db.execute("DELETE FROM prompts WHERE id=?", (prompt_id,))
                if photo_path and photo_path.startswith("data/"):
                    full_path = os.path.join(BASE_DIR, photo_path)
                    if os.path.exists(full_path):
                        try: os.remove(full_path)
                        except Exception: pass
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

# --- Вспомогательные функции ---
async def get_proxy_url(db: aiosqlite.Connection = None):
    if db:
        async with db.execute("SELECT value FROM app_settings WHERE key='bot_proxy'") as cur:
            row = await cur.fetchone()
            if row and row[0]:
                proxy_val = row[0]
                if "://" not in proxy_val:
                    parts = proxy_val.split(":")
                    if len(parts) == 4:
                        return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                    elif len(parts) == 2:
                        return f"http://{parts[0]}:{parts[1]}"
                return proxy_val
    return settings.proxy.as_url()

async def check_proxy(db: aiosqlite.Connection = None):
    try:
        proxy_url = await get_proxy_url(db)
        if not proxy_url: return "❌ Не настроен"
        test_urls = ["http://api.ipify.org", "https://api.ipify.org", "http://google.com"]
        async with httpx.AsyncClient(proxy=proxy_url, timeout=15, follow_redirects=True, verify=False) as client:
            for url in test_urls:
                try:
                    resp = await client.get(url)
                    if resp.status_code < 500:
                        return f"✅ Работает (код {resp.status_code})"
                except Exception: continue
            return "❌ Прокси не отвечает (Timeout/Auth/IP Block)"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:50]}"

async def run_broadcast(message_text: str):
    if settings.bot_token == "MOCK": return
    bot = Bot(token=settings.bot_token)
    db = await aiosqlite.connect(DB_PATH)
    async with db.execute("SELECT id FROM users") as cur:
        users = await cur.fetchall()
    for user in users:
        try:
            await bot.send_message(user[0], message_text)
            await asyncio.sleep(0.05)
        except Exception: continue
    await bot.session.close()
    await db.close()

async def send_subscription_notification(user_id: int, plan_name: str, expires_at_str: str, daily_limit: int, lang: str):
    """Отправляет уведомление пользователю об активации подписки"""
    if settings.bot_token == "MOCK": return
    
    try:
        # Форматируем дату и время
        try:
            expires_str = expires_at_str.replace('Z', '') if 'Z' in expires_at_str else expires_at_str
            if 'T' in expires_str:
                expires_dt = datetime.fromisoformat(expires_str)
            else:
                expires_dt = datetime.fromisoformat(expires_str + "T00:00:00")
            expires_date = expires_dt.strftime("%d.%m.%Y")
            expires_time = expires_dt.strftime("%H:%M")
        except Exception:
            if 'T' in expires_at_str:
                parts = expires_at_str.split('T')
                date_part = parts[0]
                time_part = parts[1][:5] if len(parts[1]) >= 5 else "00:00"
                expires_date = ".".join(reversed(date_part.split("-")))
                expires_time = time_part
            else:
                expires_date = expires_at_str[:10]
                expires_time = "00:00"

        text = get_string("sub_success_congrats", lang, 
                         plan_name=plan_name,
                         expires_date=expires_date,
                         expires_time=expires_time,
                         daily_limit=daily_limit)
        
        bot = Bot(token=settings.bot_token)
        await bot.send_message(user_id, text)
        await bot.session.close()
    except Exception as e:
        print(f"Error sending subscription notification to {user_id}: {e}")

# --- Роуты ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    try:
        # Всего пользователей
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        
        # Новые сегодня
        async with db.execute("SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')") as cur:
            today_users = (await cur.fetchone())[0]
        
        # Генераций сегодня
        async with db.execute("SELECT COUNT(*) FROM generation_history WHERE date(created_at) = date('now')") as cur:
            today_gens = (await cur.fetchone())[0]

        # Общий баланс лимитов (активные подписки)
        async with db.execute("SELECT SUM(MAX(0, daily_limit - daily_usage)) FROM subscriptions WHERE expires_at > CURRENT_TIMESTAMP") as cur:
            row = await cur.fetchone()
            total_balance = row[0] if row and row[0] else 0
            
    except Exception as e:
        print(f"Stats error: {e}")
        total_users = today_users = today_gens = total_balance = 0

    maintenance = False
    try:
        async with db.execute("SELECT value FROM app_settings WHERE key='maintenance'") as cur:
            row = await cur.fetchone()
            maintenance = row[0] == '1' if row else False
    except Exception: pass

    proxy_status = await check_proxy(db)
    
    # Получаем последние ошибки API ключей
    recent_errors = []
    proxy_errors_count = 0
    try:
        async with db.execute(
            "SELECT key_id, api_key_preview, error_type, error_message, status_code, is_proxy_error, created_at FROM api_key_errors ORDER BY created_at DESC LIMIT 10"
        ) as cur:
            recent_errors = await cur.fetchall()
        
        async with db.execute(
            "SELECT COUNT(*) FROM api_key_errors WHERE is_proxy_error=1 AND created_at > datetime('now', '-24 hours')"
        ) as cur:
            row = await cur.fetchone()
            proxy_errors_count = int(row[0]) if row else 0
    except Exception as e:
        print(f"Error fetching API errors: {e}")
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "total_users": total_users, "today_users": today_users,
        "today_gens": today_gens, "total_balance": total_balance,
        "maintenance": maintenance, "proxy_status": proxy_status,
        "recent_errors": recent_errors, "proxy_errors_count": proxy_errors_count
    })

@app.get("/users", response_class=HTMLResponse)
async def list_users(request: Request, q: str = "", db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    if q:
        query = """
            SELECT u.id, u.username, u.blocked, s.plan_id, s.plan_type, s.expires_at, s.daily_limit, s.daily_usage, s.individual_api_key
            FROM users u 
            LEFT JOIN (
                SELECT * FROM subscriptions 
                GROUP BY user_id 
                HAVING MAX(expires_at)
            ) s ON u.id = s.user_id 
            WHERE u.id LIKE ? OR u.username LIKE ? 
            ORDER BY u.created_at DESC LIMIT 100
        """
        async with db.execute(query, (f"%{q}%", f"%{q}%")) as cur:
            users = await cur.fetchall()
    else:
        query = """
            SELECT u.id, u.username, u.blocked, s.plan_id, s.plan_type, s.expires_at, s.daily_limit, s.daily_usage, s.individual_api_key
            FROM users u 
            LEFT JOIN (
                SELECT * FROM subscriptions 
                GROUP BY user_id 
                HAVING MAX(expires_at)
            ) s ON u.id = s.user_id 
            ORDER BY u.created_at DESC LIMIT 50
        """
        async with db.execute(query) as cur:
            users = await cur.fetchall()
            
    async with db.execute("SELECT id, name_ru, duration_days, daily_limit FROM subscription_plans WHERE is_active=1") as cur:
        plans = await cur.fetchall()
        
    return templates.TemplateResponse("users.html", {
        "request": request, 
        "users": users, 
        "q": q, 
        "plans": plans,
        "now": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.post("/cancel_subscription")
async def cancel_subscription(user_id: int = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    await db.commit()
    return RedirectResponse(url=f"/users?q={user_id}", status_code=303)

@app.post("/users/add_requests")
async def add_requests(
    user_id: int = Form(...),
    extra: int = Form(...),
    db: aiosqlite.Connection = Depends(get_db),
    user: str = Depends(get_current_username)
):
    if extra <= 0:
        return RedirectResponse(url=f"/users?q={user_id}", status_code=303)
    await db.execute(
        "UPDATE subscriptions SET daily_limit = daily_limit + ? WHERE user_id=? AND datetime(expires_at) > CURRENT_TIMESTAMP",
        (extra, user_id)
    )
    await db.commit()
    return RedirectResponse(url=f"/users?q={user_id}", status_code=303)

@app.get("/mailing", response_class=HTMLResponse)
async def mailing_page(request: Request, user: str = Depends(get_current_username)):
    return templates.TemplateResponse("mailing.html", {"request": request})

@app.post("/mailing/send")
async def send_mailing(background_tasks: BackgroundTasks, text: str = Form(...), user: str = Depends(get_current_username)):
    background_tasks.add_task(run_broadcast, text)
    return RedirectResponse(url="/mailing?status=sent", status_code=303)

@app.get("/prompts", response_class=HTMLResponse)
async def list_prompts(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    try:
        async with db.execute("SELECT m.*, p.text as prompt_text, p.title as prompt_title FROM models m JOIN prompts p ON m.prompt_id = p.id") as cur:
            models = await cur.fetchall()
    except Exception: models = []
    
    categorized_models = {}
    for m in models:
        cat = m['category']
        if cat not in categorized_models:
            categorized_models[cat] = []
        categorized_models[cat].append(m)
    prompt_placeholders = await _get_prompt_placeholders(db)
    return templates.TemplateResponse("prompts.html", {
        "request": request, 
        "categorized_models": categorized_models, 
        "categories": CATEGORIES,
        "prompt_placeholders": prompt_placeholders
    })

@app.post("/prompts/edit_model")
async def edit_model_prompt(
    model_id: int = Form(...), 
    name: str = Form(...), 
    prompt_text: str = Form(...), 
    photo: UploadFile = File(None),
    db: aiosqlite.Connection = Depends(get_db), 
    user: str = Depends(get_current_username)
):
    await db.execute("UPDATE models SET name=? WHERE id=?", (name, model_id))
    if photo and photo.filename:
        file_path = f"{UPLOAD_DIR}/model_{model_id}.jpg"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        rel_path = os.path.relpath(file_path, BASE_DIR).replace("\\", "/")
        await db.execute("UPDATE models SET photo_file_id=? WHERE id=?", (rel_path, model_id))
    async with db.execute("SELECT prompt_id FROM models WHERE id=?", (model_id,)) as cur:
        row = await cur.fetchone()
        if row:
            await db.execute("UPDATE prompts SET text=? WHERE id=?", (prompt_text, row[0]))
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

@app.post("/models/add_full")
async def add_full_model(
    category: str = Form(...),
    name: str = Form(...),
    prompt_text: str = Form(...),
    cloth: str = Form("all"),
    photo: UploadFile = File(None),
    db: aiosqlite.Connection = Depends(get_db),
    user: str = Depends(get_current_username)
):
    await db.execute("INSERT INTO prompts (title, text) VALUES (?, ?)", (f"Prompt for {name}", prompt_text))
    async with db.execute("SELECT last_insert_rowid()") as cur:
        prompt_id = (await cur.fetchone())[0]
    await db.execute("INSERT INTO models (category, cloth, name, prompt_id) VALUES (?, ?, ?, ?)", 
                     (category, cloth, name, prompt_id))
    async with db.execute("SELECT last_insert_rowid()") as cur:
        model_id = (await cur.fetchone())[0]
    
    if photo and photo.filename:
        file_path = f"{UPLOAD_DIR}/model_{model_id}.jpg"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        
        rel_path = os.path.relpath(file_path, BASE_DIR).replace("\\", "/")
        await db.execute("UPDATE models SET photo_file_id=? WHERE id=?", (rel_path, model_id))
    
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

@app.get("/models/delete_photo/{model_id}")
async def delete_model_photo(model_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT photo_file_id FROM models WHERE id=?", (model_id,)) as cur:
        row = await cur.fetchone()
        if row and row[0]:
            photo_path = row[0]
            if photo_path.startswith("data/"):
                full_path = os.path.join(BASE_DIR, photo_path)
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except Exception as e:
                        print(f"Error removing file {full_path}: {e}")
            await db.execute("UPDATE models SET photo_file_id=NULL WHERE id=?", (model_id,))
            await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    try:
        async with db.execute("SELECT key, value FROM app_settings WHERE key IN ('agreement_text', 'howto_text', 'required_channel_id', 'required_channel_url')") as cur:
            rows = await cur.fetchall()
            settings_dict = {r[0]: r[1] for r in rows}
    except Exception: settings_dict = {}
    return templates.TemplateResponse("settings.html", {
        "request": request, 
        "agreement": settings_dict.get('agreement_text', ""), 
        "howto": settings_dict.get('howto_text', ""),
        "channel_id": settings_dict.get('required_channel_id', ""),
        "channel_url": settings_dict.get('required_channel_url', "https://t.me/bnbslow")
    })

@app.post("/settings/update")
async def update_app_settings(
    agreement: str = Form(...), 
    howto: str = Form(...), 
    channel_id: str = Form(None),
    channel_url: str = Form(None),
    db: aiosqlite.Connection = Depends(get_db), 
    user: str = Depends(get_current_username)
):
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('agreement_text', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (agreement,))
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('howto_text', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (howto,))
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('required_channel_id', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (channel_id or "",))
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('required_channel_url', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (channel_url or "https://t.me/bnbslow",))
    await db.commit()
    return RedirectResponse(url="/settings", status_code=303)

@app.get("/api_keys", response_class=HTMLResponse)
async def list_keys(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    try:
        async with db.execute("SELECT * FROM api_keys") as cur:
            gemini_keys = await cur.fetchall()
    except Exception: gemini_keys = []
    
    try:
        async with db.execute("SELECT * FROM own_variant_api_keys") as cur:
            own_keys = await cur.fetchall()
    except Exception: own_keys = []
    
    return templates.TemplateResponse("api_keys.html", {"request": request, "gemini_keys": gemini_keys, "own_keys": own_keys})

@app.post("/api_keys/add")
async def add_key(token: str = Form(...), table: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    # Очистка токена от всего лишнего
    # 1. Убираем пробелы, табы, переносы строк
    token = "".join(token.split())
    
    # 2. Исправляем кириллицу (частые ошибки при копировании)
    cyr_to_lat = {
        'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H', 
        'О': 'O', 'Р': 'P', 'С': 'C', 'Т': 'T', 'У': 'y', 'Х': 'X',
        'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x'
    }
    new_token = ""
    for char in token:
        new_token += cyr_to_lat.get(char, char)
    token = new_token

    # 3. Оставляем только допустимые символы для API ключа (A-Z, a-z, 0-9, _, -)
    import re
    token = re.sub(r'[^A-Za-z0-9_\-]', '', token)
    
    table_name = "api_keys" if table == "gemini" else "own_variant_api_keys"
    await db.execute(f"INSERT INTO {table_name} (token) VALUES (?)", (token,))
    await db.commit()
    return RedirectResponse(url="/api_keys", status_code=303)

@app.get("/api_keys/delete/{table}/{key_id}")
async def delete_key(table: str, key_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    table_name = "api_keys" if table == "gemini" else "own_variant_api_keys"
    await db.execute(f"DELETE FROM {table_name} WHERE id=?", (key_id,))
    await db.commit()
    return RedirectResponse(url="/api_keys", status_code=303)

@app.get("/tg_img/{file_id}")
async def get_telegram_image(file_id: str, user: str = Depends(get_current_username)):
    """Прокси-роут для отображения фото из Telegram по file_id"""
    if not file_id or file_id == "None" or file_id == "FILE_ID_MOCK":
        return Response(status_code=404)
    if settings.bot_token == "MOCK":
        return Response(status_code=500, content="Bot token not configured")
    
    bot = Bot(token=settings.bot_token)
    try:
        # Получаем путь к файлу через Telegram API
        file = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{settings.bot_token}/{file.file_path}"
        
        # Используем httpx для скачивания
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Настраиваем прокси для запроса к Telegram, если они есть
            proxy_url = settings.proxy.as_url() if hasattr(settings, "proxy") else None
            
            # Важно: для httpx прокси передаются в конструктор или через mount
            # Но здесь мы можем просто попробовать без них, если прокси только для Gemini
            resp = await client.get(file_url, timeout=30)
            
            if resp.status_code == 200:
                return Response(content=resp.content, media_type="image/jpeg")
            
            # Если без прокси не вышло и прокси есть, пробуем с ними
            if proxy_url:
                async with httpx.AsyncClient(proxy=proxy_url, follow_redirects=True) as p_client:
                    resp = await p_client.get(file_url, timeout=30)
                    if resp.status_code == 200:
                        return Response(content=resp.content, media_type="image/jpeg")
            
            print(f"Telegram image {file_id} error: {resp.status_code}")
            return Response(status_code=resp.status_code)
            
    except Exception as e:
        print(f"Critical error proxying Telegram image {file_id}: {e}")
        return Response(status_code=500, content=str(e))
    finally:
        await bot.session.close()

@app.get("/history", response_class=HTMLResponse)
async def list_history(request: Request, q: str = "", db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    try:
        if q:
            query = "SELECT * FROM generation_history WHERE pid LIKE ? OR user_id LIKE ? ORDER BY created_at DESC LIMIT 50"
            async with db.execute(query, (f"%{q}%", f"%{q}%")) as cur:
                history = await cur.fetchall()
        else:
            async with db.execute("SELECT * FROM generation_history ORDER BY created_at DESC LIMIT 50") as cur:
                history = await cur.fetchall()
    except Exception: history = []
    return templates.TemplateResponse("history.html", {"request": request, "history": history, "q": q})

@app.get("/payments", response_class=HTMLResponse)
async def list_payments(request: Request, q: str = "", db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    try:
        if q:
            query = """
                SELECT p.*, sp.name_ru as plan_name 
                FROM payments p 
                LEFT JOIN subscription_plans sp ON p.plan_id = sp.id 
                WHERE p.user_id LIKE ? 
                ORDER BY p.created_at DESC LIMIT 100
            """
            async with db.execute(query, (f"%{q}%",)) as cur:
                payments = await cur.fetchall()
        else:
            query = """
                SELECT p.*, sp.name_ru as plan_name 
                FROM payments p 
                LEFT JOIN subscription_plans sp ON p.plan_id = sp.id 
                ORDER BY p.created_at DESC LIMIT 100
            """
            async with db.execute(query) as cur:
                payments = await cur.fetchall()
    except Exception as e:
        print(f"Payments error: {e}")
        payments = []
        
    return templates.TemplateResponse("payments.html", {"request": request, "payments": payments, "q": q})

@app.get("/prices", response_class=HTMLResponse)
async def list_prices(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    status_data = []
    for cat in CATEGORIES:
        status_key = f"{cat}" # Ключ статуса в БД: female, male и т.д.
        
        async with db.execute("SELECT value FROM app_settings WHERE key=?", (status_key,)) as cur:
            row = await cur.fetchone()
            # По умолчанию все включены (1), если не задано иное
            status_val = row[0] if row else "1"
            
        status_data.append({
            "status_key": status_key,
            "cat": cat, 
            "is_enabled": status_val == "1"
        })
            
    async with db.execute("SELECT * FROM subscription_plans") as cur:
        plans = await cur.fetchall()
        
    return templates.TemplateResponse("prices.html", {"request": request, "category_status": status_data, "plans": plans})

@app.post("/plans/edit")
async def edit_plan(
    plan_id: int = Form(...),
    name_ru: str = Form(...),
    name_en: str = Form(...),
    name_vi: str = Form(...),
    price: int = Form(...),
    duration: int = Form(...),
    limit: int = Form(...),
    desc_ru: str = Form(None),
    desc_en: str = Form(None),
    desc_vi: str = Form(None),
    db: aiosqlite.Connection = Depends(get_db),
    user: str = Depends(get_current_username)
):
    try:
        await db.execute(
            """UPDATE subscription_plans 
               SET name_ru=?, name_en=?, name_vi=?, price=?, duration_days=?, daily_limit=?, 
                   description_ru=?, description_en=?, description_vi=? 
               WHERE id=?""",
            (name_ru, name_en, name_vi, price, duration, limit, 
             desc_ru, desc_en, desc_vi, plan_id)
        )
        await db.commit()
        return RedirectResponse(url="/prices", status_code=303)
    except Exception as e:
        print(f"Error in edit_plan: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/categories/toggle")
async def toggle_category(key: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT value FROM app_settings WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
        current = row[0] if row else "1"
    
    new_val = "0" if current == "1" else "1"
    await db.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, new_val))
    await db.commit()
    return RedirectResponse(url="/prices", status_code=303)

@app.post("/edit_subscription")
async def edit_subscription(
    user_id: int = Form(...), 
    plan_id: str = Form(None),
    days: int = Form(...), 
    limit: int = Form(...), 
    api_key: str = Form(None),
    db: aiosqlite.Connection = Depends(get_db), 
    user: str = Depends(get_current_username)
):
    try:
        expires_at = datetime.utcnow() + timedelta(days=days)
        expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")
        plan_type = "custom"
        
        plan_id_val = None
        if plan_id and plan_id.isdigit():
            plan_id_val = int(plan_id)
            async with db.execute("SELECT name_ru FROM subscription_plans WHERE id=?", (plan_id_val,)) as cur:
                row = await cur.fetchone()
                if row:
                    plan_type = row[0]
        elif plan_id == "custom":
            plan_type = "custom"
        
        # Строгая очистка индивидуального API ключа
        safe_api_key = None
        if api_key and api_key.strip():
            # 1. Убираем пробелы, табы, переносы строк
            token = "".join(api_key.split())
            # 2. Исправляем кириллицу
            cyr_to_lat = {
                'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H', 
                'О': 'O', 'Р': 'P', 'С': 'C', 'Т': 'T', 'У': 'y', 'Х': 'X',
                'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x'
            }
            new_token = ""
            for char in token:
                new_token += cyr_to_lat.get(char, char)
            # 3. Только допустимые символы
            import re
            safe_api_key = re.sub(r'[^A-Za-z0-9_\-]', '', new_token)
        
        # Очищаем все старые подписки пользователя перед выдачей новой, 
        # чтобы избежать дублей и конфликтов
        await db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        
        await db.execute(
            "INSERT INTO subscriptions (user_id, plan_id, plan_type, expires_at, daily_limit, daily_usage, last_usage_reset, individual_api_key) VALUES (?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, ?)",
            (user_id, plan_id_val, plan_type, expires_str, limit, safe_api_key)
        )
        
        # Сбрасываем флаг триала при выдаче подписки
        await db.execute("UPDATE users SET trial_used=1 WHERE id=?", (user_id,))
        
        # Добавляем запись в историю платежей
        amount = 0
        if plan_id_val:
            async with db.execute("SELECT price FROM subscription_plans WHERE id=?", (plan_id_val,)) as cur:
                row = await cur.fetchone()
                if row:
                    amount = row[0]
        
        await db.execute(
            "INSERT INTO payments (user_id, plan_id, amount, status) VALUES (?, ?, ?, 'admin_granted')",
            (user_id, plan_id_val, amount)
        )
            
        await db.commit()

        # Отправляем уведомление пользователю
        try:
            async with db.execute("SELECT language FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                lang = row[0] if row and row[0] else "ru"
            
            await send_subscription_notification(user_id, plan_type, expires_str, limit, lang)
        except Exception as e:
            print(f"Error in post-grant notification: {e}")

        return RedirectResponse(url=f"/users?q={user_id}", status_code=303)
    except Exception as e:
        print(f"Error in edit_subscription: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/proxy", response_class=HTMLResponse)
async def proxy_page(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    current_proxy = ""
    try:
        async with db.execute("SELECT value FROM app_settings WHERE key='bot_proxy'") as cur:
            row = await cur.fetchone()
            current_proxy = row[0] if row else ""
    except Exception: pass
    status_text = await check_proxy(db)
    return templates.TemplateResponse("proxy.html", {"request": request, "current_proxy": current_proxy, "status": status_text})

@app.post("/proxy/edit")
async def edit_proxy(proxy_url: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('bot_proxy', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (proxy_url,))
    await db.commit()
    return RedirectResponse(url="/proxy", status_code=303)

@app.post("/maintenance/toggle")
async def toggle_maintenance(db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    current = False
    try:
        async with db.execute("SELECT value FROM app_settings WHERE key='maintenance'") as cur:
            row = await cur.fetchone()
            current = row[0] == '1' if row else False
    except Exception: pass
    
    new_val = '0' if current else '1'
    now_str = datetime.now().isoformat()

    if new_val == '1':
        await db.execute("INSERT INTO app_settings (key, value) VALUES ('maintenance_start', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (now_str,))
    else:
        try:
            async with db.execute("SELECT value FROM app_settings WHERE key='maintenance_start'") as cur:
                row = await cur.fetchone()
                if row:
                    start_time = datetime.fromisoformat(row[0])
                    duration_seconds = int((datetime.now() - start_time).total_seconds())
                    if duration_seconds > 0:
                        await db.execute(
                            "UPDATE subscriptions SET expires_at = datetime(expires_at, '+' || ? || ' seconds') WHERE expires_at > CURRENT_TIMESTAMP",
                            (str(duration_seconds),)
                        )
        except Exception:
            pass

    await db.execute("INSERT INTO app_settings (key, value) VALUES ('maintenance', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (new_val,))
    await db.commit()
    return RedirectResponse(url="/", status_code=303)

# --- Конструктор категорий и шагов ---
@app.get("/constructor", response_class=HTMLResponse)
async def constructor_page(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT id, key, name_ru, is_active, order_index FROM categories ORDER BY order_index, id") as cur:
        categories = await cur.fetchall()
    return templates.TemplateResponse("constructor.html", {"request": request, "categories": categories})

@app.post("/constructor/category/add")
async def admin_add_category(key: str = Form(...), name: str = Form(...), order: int = Form(0), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute(
        "INSERT OR IGNORE INTO categories (key, name_ru, is_active, order_index) VALUES (?, ?, 1, ?)",
        (key, name, order)
    )
    await db.commit()
    return RedirectResponse("/constructor", status_code=303)

@app.post("/constructor/category/delete/{cat_id}")
async def admin_delete_category(cat_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    # Удаляем все связанные данные
    await db.execute("DELETE FROM step_options WHERE step_id IN (SELECT id FROM steps WHERE category_id=?)", (cat_id,))
    await db.execute("DELETE FROM steps WHERE category_id=?", (cat_id,))
    await db.execute("DELETE FROM categories WHERE id=?", (cat_id,))
    await db.commit()
    return RedirectResponse("/constructor", status_code=303)

@app.get("/constructor/category/{cat_id}", response_class=HTMLResponse)
async def category_steps_page(request: Request, cat_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT id, key, name_ru, is_active, order_index FROM categories WHERE id=?", (cat_id,)) as cur:
        category = await cur.fetchone()
    if not category:
        return RedirectResponse("/constructor")
    
    async with db.execute(
        "SELECT id, step_key, question_text, input_type, is_optional, order_index FROM steps WHERE category_id=? ORDER BY order_index, id",
        (cat_id,)
    ) as cur:
        steps = await cur.fetchall()
    
    steps_with_options = []
    for step in steps:
        async with db.execute(
            "SELECT id, option_text, option_value, order_index, custom_prompt FROM step_options WHERE step_id=? ORDER BY order_index, id",
            (step['id'],)
        ) as cur_opt:
            options = await cur_opt.fetchall()
        
        steps_with_options.append({
            "id": step['id'],
            "key": step['step_key'],
            "question": step['question_text'],
            "type": step['input_type'],
            "optional": step['is_optional'],
            "order": step['order_index'],
            "options": options
        })

    # Получаем библиотеки для конструктора
    async with db.execute("SELECT id, step_key, question_text, input_type FROM library_steps ORDER BY id") as cur:
        lib_steps = await cur.fetchall()

    async with db.execute("SELECT id, name FROM button_categories ORDER BY id") as cur:
        button_cats = await cur.fetchall()

    lib_buttons = {}
    for bcat in button_cats:
        async with db.execute("SELECT id, option_text, option_value, custom_prompt FROM library_options WHERE category_id=? ORDER BY id", (bcat['id'],)) as cur:
            lib_buttons[bcat['name']] = await cur.fetchall()

    prompt_placeholders = await _get_prompt_placeholders(db)
    
    return templates.TemplateResponse("category_edit.html", {
        "request": request, 
        "category": category, 
        "steps": steps_with_options,
        "lib_steps": lib_steps,
        "lib_buttons": lib_buttons,
        "prompt_placeholders": prompt_placeholders
    })

@app.post("/constructor/step/add/{cat_id}")
async def admin_add_step(cat_id: int, step_key: str = Form(...), question: str = Form(...), input_type: str = Form(...), is_optional: int = Form(0), order: int = Form(0), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    if order == 0:
        async with db.execute("SELECT MAX(order_index) FROM steps WHERE category_id=?", (cat_id,)) as cur:
            row = await cur.fetchone()
            order = (row[0] or 0) + 1
            
    await db.execute(
        "INSERT INTO steps (category_id, step_key, question_text, input_type, is_optional, order_index) VALUES (?, ?, ?, ?, ?, ?)",
        (cat_id, step_key, question, input_type, is_optional, order)
    )
    await db.commit()
    return RedirectResponse(f"/constructor/category/{cat_id}", status_code=303)

@app.post("/constructor/step/delete/{cat_id}/{step_id}")
async def admin_delete_step(cat_id: int, step_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("DELETE FROM step_options WHERE step_id=?", (step_id,))
    await db.execute("DELETE FROM steps WHERE id=?", (step_id,))
    await db.commit()
    return RedirectResponse(f"/constructor/category/{cat_id}", status_code=303)

@app.post("/constructor/option/add/{cat_id}/{step_id}")
async def admin_add_option(cat_id: int, step_id: int, text: str = Form(...), value: str = Form(...), order: int = Form(0), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute(
        "INSERT INTO step_options (step_id, option_text, option_value, order_index) VALUES (?, ?, ?, ?)",
        (step_id, text, value, order)
    )
    await db.commit()
    return RedirectResponse(f"/constructor/category/{cat_id}", status_code=303)

@app.post("/constructor/option/delete/{cat_id}/{opt_id}")
async def admin_delete_option(cat_id: int, opt_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("DELETE FROM step_options WHERE id=?", (opt_id,))
    await db.commit()
    return RedirectResponse(f"/constructor/category/{cat_id}", status_code=303)

@app.post("/constructor/steps/reorder/{cat_id}")
async def admin_reorder_steps(cat_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    data = await request.json()
    step_ids = data.get("step_ids", [])
    
    # Обновляем order_index для каждого шага
    for index, step_id in enumerate(step_ids, 1):
        await db.execute("UPDATE steps SET order_index=? WHERE id=?", (index, step_id))
    
    await db.commit()
    return JSONResponse({"status": "ok"})

@app.post("/constructor/category/{cat_id}/save_all")
async def admin_save_all_steps(cat_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    data = await request.json()
    steps_data = data.get("steps", [])
    
    # Получаем текущие ID шагов этой категории
    async with db.execute("SELECT id FROM steps WHERE category_id=?", (cat_id,)) as cur:
        existing_step_ids = [row[0] for row in await cur.fetchall()]
    
    received_step_ids = []
    
    for s_data in steps_data:
        step_id = s_data.get("id")
        step_key = s_data.get("key")
        question = s_data.get("question")
        input_type = s_data.get("type")
        is_optional = s_data.get("optional")
        order_index = s_data.get("order")
        buttons = s_data.get("buttons", [])
        
        if step_id and step_id in existing_step_ids:
            # Обновляем существующий шаг
            await db.execute(
                "UPDATE steps SET question_text=?, input_type=?, is_optional=?, order_index=?, step_key=? WHERE id=?",
                (question, input_type, is_optional, order_index, step_key, step_id)
            )
            received_step_ids.append(step_id)
        else:
            # Создаем новый шаг
            await db.execute(
                "INSERT INTO steps (category_id, step_key, question_text, input_type, is_optional, order_index) VALUES (?, ?, ?, ?, ?, ?)",
                (cat_id, step_key, question, input_type, is_optional, order_index)
            )
            async with db.execute("SELECT last_insert_rowid()") as cur:
                step_id = (await cur.fetchone())[0]
            received_step_ids.append(step_id)
            
        # Работа с кнопками (опциями) этого шага
        async with db.execute("SELECT id FROM step_options WHERE step_id=?", (step_id,)) as cur:
            existing_opt_ids = [row[0] for row in await cur.fetchall()]
            
        received_opt_ids = []
        for b_data in buttons:
            opt_id = b_data.get("id")
            opt_text = b_data.get("text")
            opt_value = b_data.get("value")
            opt_prompt = b_data.get("prompt")
            opt_order = b_data.get("order")
            
            # Если opt_id - строка 'null', приводим к None
            if opt_id == 'null':
                opt_id = None
            else:
                opt_id = int(opt_id) if opt_id else None
            
            if opt_id and opt_id in existing_opt_ids:
                await db.execute(
                    "UPDATE step_options SET option_text=?, option_value=?, order_index=?, custom_prompt=? WHERE id=?",
                    (opt_text, opt_value, opt_order, opt_prompt, opt_id)
                )
                received_opt_ids.append(opt_id)
            else:
                await db.execute(
                    "INSERT INTO step_options (step_id, option_text, option_value, order_index, custom_prompt) VALUES (?, ?, ?, ?, ?)",
                    (step_id, opt_text, opt_value, opt_order, opt_prompt)
                )
                async with db.execute("SELECT last_insert_rowid()") as cur:
                    received_opt_ids.append((await cur.fetchone())[0])
                    
        # Удаляем опции, которые не пришли
        for old_opt_id in existing_opt_ids:
            if old_opt_id not in received_opt_ids:
                await db.execute("DELETE FROM step_options WHERE id=?", (old_opt_id,))
                
    # Удаляем шаги, которые не пришли
    for old_step_id in existing_step_ids:
        if old_step_id not in received_step_ids:
            await db.execute("DELETE FROM step_options WHERE step_id=?", (old_step_id,))
            await db.execute("DELETE FROM steps WHERE id=?", (old_step_id,))
            
    await db.commit()
    return JSONResponse({"status": "ok"})

@app.post("/constructor/library/step/add")
async def admin_add_library_step(step_key: str = Form(...), question: str = Form(...), input_type: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute(
        "INSERT INTO library_steps (step_key, question_text, input_type) VALUES (?, ?, ?)",
        (step_key, question, input_type)
    )
    await db.commit()
    return RedirectResponse(request.headers.get("referer", "/constructor"), status_code=303)

@app.post("/constructor/library/button/add")
async def admin_add_library_button(text: str = Form(...), value: str = Form(...), category: str = Form("Системные"), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    # Находим или создаем категорию кнопок
    async with db.execute("SELECT id FROM button_categories WHERE name=?", (category,)) as cur:
        row = await cur.fetchone()
        if row:
            cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", (category,))
            async with db.execute("SELECT last_insert_rowid()") as cur_new:
                cat_id = (await cur_new.fetchone())[0]
                
    await db.execute(
        "INSERT INTO library_options (category_id, option_text, option_value) VALUES (?, ?, ?)",
        (cat_id, text, value)
    )
    await db.commit()
    return RedirectResponse(request.headers.get("referer", "/constructor"), status_code=303)
