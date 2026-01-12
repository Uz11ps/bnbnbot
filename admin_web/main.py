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
# Пытаемся найти БД в data/ или в корне
DB_PATH = os.path.join(BASE_DIR, "data", "bot.db")
if not os.path.exists(DB_PATH):
    DB_PATH = os.path.join(BASE_DIR, "bot.db")

UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads", "models")
STATIC_DIR = os.path.join(BASE_DIR, "admin_web", "static")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаем папки при запуске
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(STATIC_DIR, exist_ok=True)
    yield

app = FastAPI(title="AI-ROOM Admin Panel", lifespan=lifespan)

# --- Шаблоны ---
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "admin_web", "templates"))
templates.env.filters["from_json"] = json.loads
security = HTTPBasic()

# Загружаем настройки (может упасть если нет .env)
try:
    settings = load_settings()
except Exception as e:
    print(f"Error loading settings: {e}")
    # Создаем пустые заглушки чтобы не падало при импорте
    class MockSettings:
        bot_token = "MOCK"
        class MockProxy:
            def as_url(self): return None
        proxy = MockProxy()
    settings = MockSettings()

ADMIN_USER = "123"
ADMIN_PASS = "123"

# Монтируем статику только если папки существуют
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

CATEGORIES = ["female", "male", "child", "storefront", "whitebg", "random", "own", "own_variant"]

# --- Вспомогательные функции ---
async def get_proxy_url(db: aiosqlite.Connection = None):
    # 1. Проверяем в БД
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
    
    # 2. Проверяем в settings (.env)
    return settings.proxy.as_url()

async def check_proxy(db: aiosqlite.Connection = None):
    try:
        proxy_url = await get_proxy_url(db)
        if not proxy_url: return "❌ Не настроен"
        
        # Список URL для проверки (пробуем сначала легкие HTTP без SSL)
        test_urls = [
            "http://api.ipify.org",
            "https://api.ipify.org",
            "http://google.com"
        ]
        
        # Используем таймаут побольше и разрешаем любые статус-коды
        async with httpx.AsyncClient(proxy=proxy_url, timeout=15, follow_redirects=True, verify=False) as client:
            for url in test_urls:
                try:
                    resp = await client.get(url)
                    # Если получили любой ответ (даже 301), значит прокси пропустил запрос
                    if resp.status_code < 500:
                        return f"✅ Работает (код {resp.status_code})"
                except Exception:
                    continue
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
        except Exception:
            continue
    await bot.session.close()
    await db.close()

# --- Роуты ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    try:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')") as cur:
            today_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM generation_history") as cur:
            total_gens = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM generation_history WHERE date(created_at) = date('now')") as cur:
            today_gens = (await cur.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(balance),0) FROM users") as cur:
            total_balance = (await cur.fetchone())[0]
    except Exception:
        total_users = today_users = total_gens = today_gens = total_balance = 0

    maintenance = False
    try:
        async with db.execute("SELECT value FROM app_settings WHERE key='maintenance'") as cur:
            row = await cur.fetchone()
            maintenance = row[0] == '1' if row else False
    except Exception: pass

    proxy_status = await check_proxy(db)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "total_users": total_users, "today_users": today_users,
        "total_gens": total_gens, "today_gens": today_gens,
        "total_balance": total_balance,
        "maintenance": maintenance, "proxy_status": proxy_status
    })

@app.get("/users", response_class=HTMLResponse)
async def list_users(request: Request, q: str = "", db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    if q:
        query = "SELECT * FROM users WHERE id LIKE ? OR username LIKE ? ORDER BY created_at DESC LIMIT 100"
        async with db.execute(query, (f"%{q}%", f"%{q}%")) as cur:
            users = await cur.fetchall()
    else:
        async with db.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 50") as cur:
            users = await cur.fetchall()
    return templates.TemplateResponse("users.html", {"request": request, "users": users, "q": q})

@app.post("/users/edit_balance")
async def edit_balance(user_id: int = Form(...), amount: int = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
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
    
    try:
        async with db.execute("SELECT * FROM prompt_templates") as cur:
            templates_data = await cur.fetchall()
    except Exception: templates_data = []

    categorized_models = {}
    for m in models:
        cat = m['category']
        if cat not in categorized_models:
            categorized_models[cat] = []
        categorized_models[cat].append(m)
    return templates.TemplateResponse("prompts.html", {
        "request": request, 
        "categorized_models": categorized_models, 
        "templates": templates_data,
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
        # Сохраняем относительный путь от корня проекта
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
        async with db.execute("SELECT key, value FROM app_settings WHERE key IN ('agreement_text', 'howto_text')") as cur:
            rows = await cur.fetchall()
            settings_dict = {r['key']: r['value'] for r in rows}
    except Exception: settings_dict = {}
    return templates.TemplateResponse("settings.html", {
        "request": request, 
        "agreement": settings_dict.get('agreement_text', ""), 
        "howto": settings_dict.get('howto_text', "")
    })

@app.post("/settings/update")
async def update_app_settings(
    agreement: str = Form(...), 
    howto: str = Form(...), 
    db: aiosqlite.Connection = Depends(get_db), 
    user: str = Depends(get_current_username)
):
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('agreement_text', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (agreement,))
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('howto_text', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (howto,))
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

@app.post("/templates/edit")
async def edit_template(key: str = Form(...), template: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("UPDATE prompt_templates SET template=? WHERE key=?", (template, key))
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

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

@app.post("/users/edit_subscription")
async def edit_subscription(user_id: int = Form(...), days: int = Form(...), limit: int = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    expires_at = datetime.now() + timedelta(days=days)
    await db.execute(
        "INSERT INTO subscriptions (user_id, plan_type, expires_at, daily_limit) VALUES (?, 'custom', ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at, daily_limit=excluded.daily_limit",
        (user_id, expires_at.isoformat(), limit)
    )
    await db.commit()
    return RedirectResponse(url=f"/users?q={user_id}", status_code=303)

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
