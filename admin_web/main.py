from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, BackgroundTasks, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
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
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# --- Настройки путей ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# В Docker контейнере база должна быть в /app/data/bot.db
DB_PATH = "/app/data/bot.db"
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(STATIC_DIR, exist_ok=True)
    
    # Запуск миграций при старте
    async with aiosqlite.connect(DB_PATH) as db:
        await run_migrations(db)
        
    yield

app = FastAPI(title="AI-ROOM Admin Panel", lifespan=lifespan)

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

CATEGORIES = ["female", "male", "child", "storefront", "whitebg", "random", "random_other", "own", "own_variant", "infographic_clothing", "infographic_other"]

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
    return templates.TemplateResponse("prompts.html", {
        "request": request, 
        "categorized_models": categorized_models, 
        "categories": CATEGORIES
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
    photo: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
    user: str = Depends(get_current_username)
):
    await db.execute("INSERT INTO prompts (title, text) VALUES (?, ?)", (f"Prompt for {name}", prompt_text))
    async with db.execute("SELECT last_insert_rowid()") as cur:
        prompt_id = (await cur.fetchone())[0]
    await db.execute("INSERT INTO models (category, cloth, name, prompt_id) VALUES (?, 'default', ?, ?)", 
                     (category, name, prompt_id))
    async with db.execute("SELECT last_insert_rowid()") as cur:
        model_id = (await cur.fetchone())[0]
    
    file_path = f"{UPLOAD_DIR}/model_{model_id}.jpg"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(photo.file, buffer)
    
    rel_path = os.path.relpath(file_path, BASE_DIR).replace("\\", "/")
    await db.execute("UPDATE models SET photo_file_id=? WHERE id=?", (rel_path, model_id))
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    try:
        async with db.execute("SELECT key, value FROM app_settings WHERE key IN ('agreement_text', 'howto_text', 'channel_id')") as cur:
            rows = await cur.fetchall()
            settings_dict = {r['key']: r['value'] for r in rows}
    except Exception: settings_dict = {}
    return templates.TemplateResponse("settings.html", {
        "request": request, 
        "agreement": settings_dict.get('agreement_text', ""), 
        "howto": settings_dict.get('howto_text', ""),
        "channel_id": settings_dict.get('channel_id', "-1003224356583")
    })

@app.post("/settings/update")
async def update_app_settings(
    agreement: str = Form(...), 
    howto: str = Form(...), 
    channel_id: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db), 
    user: str = Depends(get_current_username)
):
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('agreement_text', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (agreement,))
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('howto_text', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (howto,))
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('channel_id', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (channel_id,))
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
