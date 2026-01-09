from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import aiosqlite
import os
import asyncio
from aiogram import Bot
from bot.config import load_settings

app = FastAPI(title="AI-ROOM Admin Panel")
templates = Jinja2Templates(directory="admin_web/templates")
security = HTTPBasic()

DB_PATH = "data/bot.db"
LOG_PATH = "data/bot.log"
settings = load_settings()

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

# --- Рассылка (в фоне) ---
async def run_broadcast(message_text: str):
    bot = Bot(token=settings.bot_token)
    db = await aiosqlite.connect(DB_PATH)
    async with db.execute("SELECT id FROM users") as cur:
        users = await cur.fetchall()
    
    count = 0
    for user in users:
        try:
            await bot.send_message(user[0], message_text)
            count += 1
            await asyncio.sleep(0.05) # Защита от спам-фильтра ТГ
        except Exception:
            continue
    await bot.session.close()
    await db.close()

@app.get("/mailing", response_class=HTMLResponse)
async def mailing_page(request: Request, user: str = Depends(get_current_username)):
    return templates.TemplateResponse("mailing.html", {"request": request})

@app.post("/mailing/send")
async def send_mailing(background_tasks: BackgroundTasks, text: str = Form(...), user: str = Depends(get_current_username)):
    background_tasks.add_task(run_broadcast, text)
    return RedirectResponse(url="/mailing?status=sent", status_code=303)

# --- Управление моделями (кнопками) ---
@app.get("/models", response_class=HTMLResponse)
async def list_models(request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT m.*, p.title as prompt_title FROM models m LEFT JOIN prompts p ON m.prompt_id = p.id ORDER BY m.category, m.cloth") as cur:
        models = await cur.fetchall()
    async with db.execute("SELECT id, title FROM prompts") as cur:
        prompts = await cur.fetchall()
    return templates.TemplateResponse("models.html", {"request": request, "models": models, "prompts": prompts})

@app.post("/models/add")
async def add_model(
    category: str = Form(...), 
    cloth: str = Form(...), 
    name: str = Form(...), 
    prompt_id: int = Form(...), 
    db: aiosqlite.Connection = Depends(get_db), 
    user: str = Depends(get_current_username)
):
    await db.execute("INSERT INTO models (category, cloth, name, prompt_id) VALUES (?, ?, ?, ?)", 
                     (category, cloth, name, prompt_id))
    await db.commit()
    return RedirectResponse(url="/models", status_code=303)

@app.get("/models/delete/{model_id}")
async def delete_model(model_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
    await db.commit()
    return RedirectResponse(url="/models", status_code=303)

# Остальные роуты (dashboard, users, prompts, prices, api_keys, logs) остаются прежними...
# ... (код сокращен для краткости, но он должен быть в файле)
