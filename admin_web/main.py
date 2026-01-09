from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import aiosqlite
import os
import json
from datetime import datetime

app = FastAPI(title="AI-ROOM Admin Panel")
templates = Jinja2Templates(directory="admin_web/templates")
security = HTTPBasic()

DB_PATH = "data/bot.db"
LOG_PATH = "data/bot.log" # Путь к логам бота

ADMIN_USER = "admin"
ADMIN_PASS = "jahlYq9pMcT2Ufq6"

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
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

# --- Списки категорий и типов одежды ---
CATEGORIES = ["female", "male", "child", "storefront", "whitebg", "random", "own", "own_variant"]
CLOTH_TYPES = ["coat", "dress", "pants", "shorts", "top", "loungewear", "suit", "overall", "skirt", "shoes", "bg"]

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT COUNT(*) FROM users") as cur:
        total_users = (await cur.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM generation_history") as cur:
        total_gens = (await cur.fetchone())[0]
    async with db.execute("SELECT value FROM app_settings WHERE key='maintenance'") as cur:
        row = await cur.fetchone()
        maintenance = row[0] == '1' if row else False
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_users": total_users,
        "total_gens": total_gens,
        "maintenance": maintenance
    })

@app.post("/maintenance/toggle")
async def toggle_maintenance(db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT value FROM app_settings WHERE key='maintenance'") as cur:
        row = await cur.fetchone()
        current = row[0] == '1' if row else False
    new_val = '0' if current else '1'
    await db.execute("INSERT INTO app_settings (key, value) VALUES ('maintenance', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (new_val,))
    await db.commit()
    return RedirectResponse(url="/", status_code=303)

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

@app.get("/prices", response_class=HTMLResponse)
async def list_prices(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    prices_data = []
    for cat in CATEGORIES:
        key = f"category_price_{cat}"
        async with db.execute("SELECT value FROM app_settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            val = row[0] if row else "10" # Дефолт 10
            prices_data.append({"key": key, "cat": cat, "value": val})
    return templates.TemplateResponse("prices.html", {"request": request, "prices": prices_data})

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
    async with db.execute("SELECT m.*, p.title as prompt_title FROM models m JOIN prompts p ON m.prompt_id = p.id ORDER BY m.category, m.cloth") as cur:
        models = await cur.fetchall()
    return templates.TemplateResponse("models.html", {"request": request, "models": models})

@app.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request, user: str = Depends(get_current_username)):
    logs = "Log file not found."
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            logs = f.readlines()[-200:] # Последние 200 строк
            logs = "".join(logs)
    return templates.TemplateResponse("logs.html", {"request": request, "logs": logs})
