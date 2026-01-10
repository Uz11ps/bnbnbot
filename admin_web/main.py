from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import aiosqlite
import os
import asyncio
import httpx
from aiogram import Bot
from bot.config import load_settings

app = FastAPI(title="AI-ROOM Admin Panel")
import json

# ...
templates = Jinja2Templates(directory="admin_web/templates")
templates.env.filters["from_json"] = json.loads
security = HTTPBasic()

DB_PATH = "data/bot.db"
LOG_PATH = "data/bot.log"
settings = load_settings()

ADMIN_USER = "123"
ADMIN_PASS = "123"

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
async def check_proxy():
    try:
        proxy_url = settings.proxy.as_url()
        if not proxy_url: return "❌ Не настроен"
        async with httpx.AsyncClient(proxy=proxy_url, timeout=5) as client:
            resp = await client.get("https://google.com")
            return "✅ Работает" if resp.status_code == 200 else "❌ Ошибка прокси"
    except Exception as e:
        return f"❌ Ошибка: {e}"

async def run_broadcast(message_text: str):
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

    async with db.execute("SELECT value FROM app_settings WHERE key='maintenance'") as cur:
        row = await cur.fetchone()
        maintenance = row[0] == '1' if row else False
    proxy_status = await check_proxy()
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
    async with db.execute("SELECT * FROM prompts") as cur:
        db_prompts = await cur.fetchall()
    async with db.execute("SELECT key, value FROM app_settings WHERE key LIKE '%_prompt%'") as cur:
        settings_prompts = await cur.fetchall()
    return templates.TemplateResponse("prompts.html", {"request": request, "prompts": db_prompts, "settings_prompts": settings_prompts})

@app.post("/prompts/edit_db")
async def edit_prompt_db(prompt_id: int = Form(...), text: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("UPDATE prompts SET text=? WHERE id=?", (text, prompt_id))
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

@app.post("/prompts/edit_settings")
async def edit_prompt_settings(key: str = Form(...), value: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("UPDATE app_settings SET value=? WHERE key=?", (value, key))
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

@app.get("/prices", response_class=HTMLResponse)
async def list_prices(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    prices_data = []
    for cat in CATEGORIES:
        key = f"category_price_{cat}"
        async with db.execute("SELECT value FROM app_settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            val = row[0] if row else "10"
            prices_data.append({"key": key, "cat": cat, "value": val})
    return templates.TemplateResponse("prices.html", {"request": request, "prices": prices_data})

@app.post("/prices/edit")
async def edit_price(key: str = Form(...), value: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    await db.commit()
    return RedirectResponse(url="/prices", status_code=303)

@app.get("/categories", response_class=HTMLResponse)
async def list_categories(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    cat_status = []
    for cat in CATEGORIES:
        key = f"cat_enabled_{cat}"
        async with db.execute("SELECT value FROM app_settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            enabled = row[0] == '1' if row else True
            cat_status.append({"key": key, "name": cat, "enabled": enabled})
    return templates.TemplateResponse("categories.html", {"request": request, "categories": cat_status})

@app.post("/categories/toggle/{name}")
async def toggle_category(name: str, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    key = f"cat_enabled_{name}"
    async with db.execute("SELECT value FROM app_settings WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
        current = row[0] == '1' if row else True
    new_val = '0' if current else '1'
    await db.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, new_val))
    await db.commit()
    return RedirectResponse(url="/categories", status_code=303)

@app.get("/models", response_class=HTMLResponse)
async def list_models(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT m.*, p.title as prompt_title FROM models m LEFT JOIN prompts p ON m.prompt_id = p.id ORDER BY m.category, m.cloth") as cur:
        models = await cur.fetchall()
    async with db.execute("SELECT id, title FROM prompts") as cur:
        prompts = await cur.fetchall()
    return templates.TemplateResponse("models.html", {"request": request, "models": models, "prompts": prompts})

@app.post("/models/add")
async def add_model(category: str = Form(...), cloth: str = Form(...), name: str = Form(...), prompt_id: int = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("INSERT INTO models (category, cloth, name, prompt_id) VALUES (?, ?, ?, ?)", (category, cloth, name, prompt_id))
    await db.commit()
    return RedirectResponse(url="/models", status_code=303)

@app.get("/models/delete/{model_id}")
async def delete_model(model_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
    await db.commit()
    return RedirectResponse(url="/models", status_code=303)

@app.get("/api_keys", response_class=HTMLResponse)
async def list_keys(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT * FROM api_keys") as cur:
        gemini_keys = await cur.fetchall()
    async with db.execute("SELECT * FROM own_variant_api_keys") as cur:
        own_keys = await cur.fetchall()
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

@app.get("/templates", response_class=HTMLResponse)
async def list_templates(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT * FROM prompt_templates") as cur:
        templates_data = await cur.fetchall()
    return templates.TemplateResponse("templates.html", {"request": request, "templates": templates_data})

@app.post("/templates/edit")
async def edit_template(key: str = Form(...), template: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("UPDATE prompt_templates SET template=? WHERE key=?", (template, key))
    await db.commit()
    return RedirectResponse(url="/templates", status_code=303)

@app.get("/history", response_class=HTMLResponse)
async def list_history(request: Request, q: str = "", db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    if q:
        query = "SELECT * FROM generation_history WHERE pid LIKE ? OR user_id LIKE ? ORDER BY created_at DESC LIMIT 50"
        async with db.execute(query, (f"%{q}%", f"%{q}%")) as cur:
            history = await cur.fetchall()
    else:
        async with db.execute("SELECT * FROM generation_history ORDER BY created_at DESC LIMIT 50") as cur:
            history = await cur.fetchall()
    return templates.TemplateResponse("history.html", {"request": request, "history": history, "q": q})

@app.post("/users/edit_subscription")
async def edit_subscription(user_id: int = Form(...), days: int = Form(...), limit: int = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    from datetime import datetime, timedelta
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
    async with db.execute("SELECT value FROM app_settings WHERE key='bot_proxy'") as cur:
        row = await cur.fetchone()
        current_proxy = row[0] if row else ""
    status = await check_proxy()
    return templates.TemplateResponse("proxy.html", {"request": request, "current_proxy": current_proxy, "status": status})

@app.post("/proxy/edit")
async def edit_proxy(proxy_url: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('bot_proxy', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (proxy_url,))
    await db.commit()
    return RedirectResponse(url="/proxy", status_code=303)

@app.post("/maintenance/toggle")
async def toggle_maintenance(db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT value FROM app_settings WHERE key='maintenance'") as cur:
        row = await cur.fetchone()
        current = row[0] == '1' if row else False
    
    new_val = '0' if current else '1'
    from datetime import datetime
    now_str = datetime.now().isoformat()

    if new_val == '1':
        # Включаем: записываем время начала
        await db.execute("INSERT INTO app_settings (key, value) VALUES ('maintenance_start', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (now_str,))
    else:
        # Выключаем: продлеваем все активные подписки на время, которое длились техработы
        async with db.execute("SELECT value FROM app_settings WHERE key='maintenance_start'") as cur:
            row = await cur.fetchone()
            if row:
                try:
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
