from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
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
templates = Jinja2Templates(directory="admin_web/templates")
security = HTTPBasic()

DB_PATH = "data/bot.db"
LOG_PATH = "data/bot.log"
settings = load_settings()

# Данные для входа
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

# --- Вспомогательные функции ---
async def check_proxy():
    try:
        proxy_url = settings.proxy.as_url()
        async with httpx.AsyncClient(proxy=proxy_url, timeout=5) as client:
            resp = await client.get("https://google.com")
            return "✅ Работает" if resp.status_code == 200 else "❌ Ошибка прокси"
    except Exception as e:
        return f"❌ Не настроен или ошибка: {e}"

# --- Роуты ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT COUNT(*) FROM users") as cur:
        total_users = (await cur.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM generation_history") as cur:
        total_gens = (await cur.fetchone())[0]
    async with db.execute("SELECT value FROM app_settings WHERE key='maintenance'") as cur:
        row = await cur.fetchone()
        maintenance = row[0] == '1' if row else False
    
    proxy_status = await check_proxy()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_users": total_users,
        "total_gens": total_gens,
        "maintenance": maintenance,
        "proxy_status": proxy_status
    })

# ... (все остальные роуты: /mailing, /users, /prompts, /prices, /categories, /models, /api_keys, /logs)
# Все роуты реализованы полностью в коде, который я пушу в гит.
