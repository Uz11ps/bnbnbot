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

    # Миграции для переводов (steps)
    try:
        async with db.execute("PRAGMA table_info(steps)") as cur:
            s_cols = [row[1] for row in await cur.fetchall()]
        if s_cols and "question_text_en" not in s_cols:
            await db.execute("ALTER TABLE steps ADD COLUMN question_text_en TEXT")
            await db.commit()
        if s_cols and "question_text_vi" not in s_cols:
            await db.execute("ALTER TABLE steps ADD COLUMN question_text_vi TEXT")
            await db.commit()
    except Exception as e:
        print(f"Migration error (steps translations): {e}")

    # Миграции для переводов (library_options)
    try:
        async with db.execute("PRAGMA table_info(library_options)") as cur:
            l_cols = [row[1] for row in await cur.fetchall()]
        if l_cols and "option_text_en" not in l_cols:
            await db.execute("ALTER TABLE library_options ADD COLUMN option_text_en TEXT")
            await db.commit()
        if l_cols and "option_text_vi" not in l_cols:
            await db.execute("ALTER TABLE library_options ADD COLUMN option_text_vi TEXT")
            await db.commit()
    except Exception as e:
        print(f"Migration error (library_options translations): {e}")

    # Миграции для переводов (step_options)
    try:
        async with db.execute("PRAGMA table_info(step_options)") as cur:
            so_cols = [row[1] for row in await cur.fetchall()]
        if so_cols and "option_text_en" not in so_cols:
            await db.execute("ALTER TABLE step_options ADD COLUMN option_text_en TEXT")
            await db.commit()
        if so_cols and "option_text_vi" not in so_cols:
            await db.execute("ALTER TABLE step_options ADD COLUMN option_text_vi TEXT")
            await db.commit()
    except Exception as e:
        print(f"Migration error (step_options translations): {e}")

    # Таблица опций для библиотечных вопросов
    try:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS library_step_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step_id INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                option_value TEXT NOT NULL,
                order_index INTEGER NOT NULL DEFAULT 0,
                custom_prompt TEXT,
                FOREIGN KEY(step_id) REFERENCES library_steps(id)
            );
            """
        )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library_step_options): {e}")

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
        # Категория праздников и кнопки
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Праздники",)) as cur:
            row = await cur.fetchone()
        if row:
            holiday_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Праздники",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Праздники",)) as cur:
                holiday_cat_id = (await cur.fetchone())[0]

        holiday_buttons = [
            ("Новый год", "new_year", None),
            ("Рождество", "christmas", None),
            ("День рождения", "birthday", None),
            ("8 марта", "mar8", None),
            ("14 февраля", "feb14", None),
            ("23 февраля", "feb23", None),
            ("Свадьба", "wedding", None),
            ("Выпускной", "graduation", None),
            ("Хэллоуин", "halloween", None),
        ]
        for text, value, prompt in holiday_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (holiday_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (holiday_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library holidays): {e}")

    try:
        # Категория размеров и кнопки
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Размеры",)) as cur:
            row = await cur.fetchone()
        if row:
            dim_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Размеры",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Размеры",)) as cur:
                dim_cat_id = (await cur.fetchone())[0]

        dim_buttons = [
            ("Ширина", "width", None),
            ("Высота", "height", None),
            ("Длина", "length", None),
        ]
        for text, value, prompt in dim_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (dim_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (dim_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library dimensions): {e}")

    try:
        # Категория преимуществ и кнопки
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Преимущества",)) as cur:
            row = await cur.fetchone()
        if row:
            adv_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Преимущества",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Преимущества",)) as cur:
                adv_cat_id = (await cur.fetchone())[0]

        adv_buttons = [
            ("Топ 1 преимущества товара", "adv_1", None),
            ("Топ 2 преимущества товара", "adv_2", None),
            ("Топ 3 преимущества товара", "adv_3", None),
        ]
        for text, value, prompt in adv_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (adv_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (adv_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library advantages): {e}")

    try:
        # Категория дополнительно и кнопка
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Дополнительно",)) as cur:
            row = await cur.fetchone()
        if row:
            extra_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Дополнительно",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Дополнительно",)) as cur:
                extra_cat_id = (await cur.fetchone())[0]

        extra_buttons = [
            ("Дополнительная информация о продукте", "extra_info", None),
        ]
        for text, value, prompt in extra_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (extra_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (extra_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library extra): {e}")

    try:
        # Категория человек и кнопки
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Человек",)) as cur:
            row = await cur.fetchone()
        if row:
            person_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Человек",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Человек",)) as cur:
                person_cat_id = (await cur.fetchone())[0]

        person_buttons = [
            ("Человек присутствует", "person_yes", None),
            ("Без человека", "person_no", None),
        ]
        for text, value, prompt in person_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (person_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (person_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library person): {e}")

    try:
        # Категория продукт и кнопка
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Продукт",)) as cur:
            row = await cur.fetchone()
        if row:
            product_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Продукт",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Продукт",)) as cur:
                product_cat_id = (await cur.fetchone())[0]

        product_buttons = [
            ("Название товара/бренда", "product_name", None),
        ]
        for text, value, prompt in product_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (product_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (product_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library product): {e}")

    try:
        # Категория стиль и кнопка
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Стиль",)) as cur:
            row = await cur.fetchone()
        if row:
            style_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Стиль",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Стиль",)) as cur:
                style_cat_id = (await cur.fetchone())[0]

        style_buttons = [
            ("Стиль", "style", None),
        ]
        for text, value, prompt in style_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (style_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (style_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library style): {e}")

    try:
        # Категория язык и кнопки
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Язык",)) as cur:
            row = await cur.fetchone()
        if row:
            lang_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Язык",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Язык",)) as cur:
                lang_cat_id = (await cur.fetchone())[0]

        lang_buttons = [
            ("Русский", "lang_ru", None),
            ("English", "lang_en", None),
            ("Tiếng Việt", "lang_vi", None),
        ]
        for text, value, prompt in lang_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (lang_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (lang_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library language): {e}")

    try:
        # Категория формат и кнопки
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Формат",)) as cur:
            row = await cur.fetchone()
        if row:
            format_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Формат",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Формат",)) as cur:
                format_cat_id = (await cur.fetchone())[0]

        format_buttons = [
            ("1:1", "1:1", None),
            ("9:16", "9:16", None),
            ("16:9", "16:9", None),
            ("3:4", "3:4", None),
            ("4:3", "4:3", None),
            ("3:2", "3:2", None),
            ("2:3", "2:3", None),
            ("5:4", "5:4", None),
            ("4:5", "4:5", None),
            ("21:9", "21:9", None),
        ]
        for text, value, prompt in format_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (format_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (format_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library format): {e}")

    try:
        # Категория Локация (На улице)
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Локация (Улица)",)) as cur:
            row = await cur.fetchone()
        if row:
            out_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Локация (Улица)",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Локация (Улица)",)) as cur:
                out_cat_id = (await cur.fetchone())[0]

        out_buttons = [
            ("У машины", "car", None),
            ("У кофейни", "cafe", None),
            ("У стены", "wall", None),
            ("У здания", "building", None),
            ("Москва сити", "moscow_city", None),
            ("В лесу", "forest", None),
            ("В горах", "mountains", None),
            ("На аллее", "alley", None),
            ("В парке", "park", None),
            ("В городе", "city", None),
            ("Свой вариант", "custom", "Введите ваш вариант локации на улице (до 100 симв):"),
        ]
        for text, value, prompt in out_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (out_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (out_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library street location): {e}")

    try:
        # Категория Локация (Помещение)
        async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Локация (Помещение)",)) as cur:
            row = await cur.fetchone()
        if row:
            in_cat_id = row[0]
        else:
            await db.execute("INSERT INTO button_categories (name) VALUES (?)", ("Локация (Помещение)",))
            await db.commit()
            async with db.execute("SELECT id FROM button_categories WHERE name=?", ("Локация (Помещение)",)) as cur:
                in_cat_id = (await cur.fetchone())[0]

        in_buttons = [
            ("Фотостудия", "photo_studio", None),
            ("В комнате", "room", None),
            ("В ресторане", "restaurant", None),
            ("В гостинице", "hotel", None),
            ("В торговом центре", "mall", None),
            ("Свой вариант", "custom", "Введите ваш вариант помещения (до 100 симв):"),
        ]
        for text, value, prompt in in_buttons:
            async with db.execute(
                "SELECT id FROM library_options WHERE category_id=? AND option_value=?",
                (in_cat_id, value)
            ) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_options (category_id, option_text, option_value, custom_prompt) VALUES (?, ?, ?, ?)",
                        (in_cat_id, text, value, prompt)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library indoor location): {e}")

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
        # Библиотека вопросов: нагруженность инфографики
        async with db.execute("SELECT id FROM library_steps WHERE step_key=?", ("info_load",)) as cur:
            if not await cur.fetchone():
                await db.execute(
                    "INSERT INTO library_steps (step_key, question_text, input_type) VALUES (?, ?, ?)",
                    ("info_load", "📊 Укажите нагруженность инфографики (1-10):", "text")
                )
                await db.commit()
    except Exception as e:
        print(f"Migration error (library_steps.info_load): {e}")

    try:
        # Библиотека вопросов: формат фото
        async with db.execute("SELECT id FROM library_steps WHERE step_key=?", ("aspect",)) as cur:
            if not await cur.fetchone():
                await db.execute(
                    "INSERT INTO library_steps (step_key, question_text, input_type) VALUES (?, ?, ?)",
                    ("aspect", "🖼 Выберите формат фото:", "buttons")
                )
                await db.commit()
    except Exception as e:
        print(f"Migration error (library_steps.aspect): {e}")

    try:
        # Библиотека вопросов: преимущества 1-3 и другие
        ready_steps = [
            ("adv_1", "🏆 Укажите преимущество 1:", "text"),
            ("adv_2", "🏆 Укажите преимущество 2:", "text"),
            ("adv_3", "🏆 Укажите преимущество 3:", "text"),
            ("info_lang", "🌐 Выберите язык инфографики:", "buttons"),
            ("extra_info", "ℹ️ Дополнительная информация о продукте:", "text"),
            ("brand_name", "🏷️ Укажите название бренда/товара:", "text"),
            ("holiday", "🎉 Выберите праздник:", "buttons"),
            ("has_person", "👤 Присутствует ли человек на фото?", "buttons"),
            ("rand_location_indoor", "🏠 Выберите стиль (В помещении):", "buttons"),
            ("rand_location_outdoor", "🌳 Выберите стиль (На улице):", "buttons"),
        ]
        for key, question, i_type in ready_steps:
            async with db.execute("SELECT id FROM library_steps WHERE step_key=?", (key,)) as cur:
                if not await cur.fetchone():
                    await db.execute(
                        "INSERT INTO library_steps (step_key, question_text, input_type) VALUES (?, ?, ?)",
                        (key, question, i_type)
                    )
        await db.commit()
    except Exception as e:
        print(f"Migration error (library_steps additions): {e}")

    try:
        # Дефолтные кнопки для языков в библиотеке вопросов
        async with db.execute("SELECT id FROM library_steps WHERE step_key=?", ("info_lang",)) as cur:
            row = await cur.fetchone()
        if row:
            lang_step_id = row[0]
            async with db.execute("SELECT COUNT(*) FROM library_step_options WHERE step_id=?", (lang_step_id,)) as cur:
                if (await cur.fetchone())[0] == 0:
                    langs = [("Русский", "lang_ru"), ("English", "lang_en"), ("Tiếng Việt", "lang_vi")]
                    for idx, (t, v) in enumerate(langs, 1):
                        await db.execute(
                            "INSERT INTO library_step_options (step_id, option_text, option_value, order_index) VALUES (?, ?, ?, ?)",
                            (lang_step_id, t, v, idx)
                        )
                    await db.commit()

        # Дефолтные кнопки для праздников в библиотеке вопросов
        async with db.execute("SELECT id FROM library_steps WHERE step_key=?", ("holiday",)) as cur:
            row = await cur.fetchone()
        if row:
            h_step_id = row[0]
            async with db.execute("SELECT COUNT(*) FROM library_step_options WHERE step_id=?", (h_step_id,)) as cur:
                if (await cur.fetchone())[0] == 0:
                    hols = [
                        ("Новый год", "newyear"), ("Рождество", "christmas"), 
                        ("День рождения", "birthday"), ("8 марта", "mar8"), 
                        ("Свадьба", "wedding"), ("Пропустить", "skip")
                    ]
                    for idx, (t, v) in enumerate(hols, 1):
                        await db.execute(
                            "INSERT INTO library_step_options (step_id, option_text, option_value, order_index) VALUES (?, ?, ?, ?)",
                            (h_step_id, t, v, idx)
                        )
                    await db.commit()

        # Дефолтные кнопки для присутствия человека
        async with db.execute("SELECT id FROM library_steps WHERE step_key=?", ("has_person",)) as cur:
            row = await cur.fetchone()
        if row:
            p_step_id = row[0]
            async with db.execute("SELECT COUNT(*) FROM library_step_options WHERE step_id=?", (p_step_id,)) as cur:
                if (await cur.fetchone())[0] == 0:
                    btns = [("Да", "person_yes"), ("Нет", "person_no")]
                    for idx, (t, v) in enumerate(btns, 1):
                        await db.execute(
                            "INSERT INTO library_step_options (step_id, option_text, option_value, order_index) VALUES (?, ?, ?, ?)",
                            (p_step_id, t, v, idx)
                        )
                    await db.commit()

        # Дефолтные кнопки для локаций (В помещении)
        async with db.execute("SELECT id FROM library_steps WHERE step_key='rand_location_indoor'") as cur:
            row = await cur.fetchone()
        if row:
            step_id = row[0]
            async with db.execute("SELECT COUNT(*) FROM library_step_options WHERE step_id=?", (step_id,)) as cur:
                if (await cur.fetchone())[0] == 0:
                    btns = [
                        ("Фотостудия", "photo_studio"), 
                        ("В комнате", "room"), 
                        ("В ресторане", "restaurant"), 
                        ("В гостинице", "hotel"), 
                        ("В торговом центре", "mall"), 
                        ("Свой вариант", "custom")
                    ]
                    for idx, (t, v) in enumerate(btns, 1):
                        prompt = "Введите ваш вариант помещения (до 100 симв):" if v == "custom" else None
                        await db.execute(
                            "INSERT INTO library_step_options (step_id, option_text, option_value, order_index, custom_prompt) VALUES (?, ?, ?, ?, ?)",
                            (step_id, t, v, idx, prompt)
                        )
                    await db.commit()

        # Дефолтные кнопки для локаций (На улице)
        async with db.execute("SELECT id FROM library_steps WHERE step_key='rand_location_outdoor'") as cur:
            row = await cur.fetchone()
        if row:
            step_id = row[0]
            async with db.execute("SELECT COUNT(*) FROM library_step_options WHERE step_id=?", (step_id,)) as cur:
                if (await cur.fetchone())[0] == 0:
                    btns = [
                        ("У машины", "car"), 
                        ("У кофейни", "cafe"), 
                        ("У стены", "wall"), 
                        ("У здания", "building"), 
                        ("Москва сити", "moscow_city"), 
                        ("В лесу", "forest"), 
                        ("В горах", "mountains"), 
                        ("На аллее", "alley"), 
                        ("В парке", "park"), 
                        ("В городе", "city"), 
                        ("Свой вариант", "custom")
                    ]
                    for idx, (t, v) in enumerate(btns, 1):
                        prompt = "Введите ваш вариант локации на улице (до 100 симв):" if v == "custom" else None
                        await db.execute(
                            "INSERT INTO library_step_options (step_id, option_text, option_value, order_index, custom_prompt) VALUES (?, ?, ?, ?, ?)",
                            (step_id, t, v, idx, prompt)
                        )
                    await db.commit()
    except Exception as e:
        print(f"Migration error (library_step_options defaults): {e}")

    try:
        # Дефолтные кнопки формата для библиотечного вопроса
        async with db.execute("SELECT id FROM library_steps WHERE step_key=?", ("aspect",)) as cur:
            row = await cur.fetchone()
        if row:
            aspect_step_id = row[0]
            async with db.execute("SELECT COUNT(*) FROM library_step_options WHERE step_id=?", (aspect_step_id,)) as cur:
                count = (await cur.fetchone())[0]
            if count == 0:
                format_buttons = [
                    ("1:1", "1:1", None),
                    ("9:16", "9:16", None),
                    ("16:9", "16:9", None),
                    ("3:4", "3:4", None),
                    ("4:3", "4:3", None),
                    ("3:2", "3:2", None),
                    ("2:3", "2:3", None),
                    ("5:4", "5:4", None),
                    ("4:5", "4:5", None),
                    ("21:9", "21:9", None),
                ]
                for idx, (text, value, prompt) in enumerate(format_buttons, start=1):
                    await db.execute(
                        "INSERT INTO library_step_options (step_id, option_text, option_value, order_index, custom_prompt) VALUES (?, ?, ?, ?, ?)",
                        (aspect_step_id, text, value, idx, prompt)
                    )
                await db.commit()
    except Exception as e:
        print(f"Migration error (library_steps.aspect buttons): {e}")

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

    # Миграция для support_messages
    try:
        async with db.execute("PRAGMA table_info(support_messages)") as cur:
            support_cols = [row[1] for row in await cur.fetchall()]
        
        if not support_cols:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_text TEXT,
                file_id TEXT,
                file_type TEXT DEFAULT 'text',
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """)
        else:
            if "file_id" not in support_cols:
                await db.execute("ALTER TABLE support_messages ADD COLUMN file_id TEXT")
            if "file_type" not in support_cols:
                await db.execute("ALTER TABLE support_messages ADD COLUMN file_type TEXT DEFAULT 'text'")
        
        await db.commit()
    except Exception as e:
        print(f"Migration error (support_messages): {e}")

    # --- МИГРАЦИЯ ПРОМПТОВ (FORCE UPDATE) ---
    try:
        # Функция для проверки, содержит ли текст старые метки
        def has_old_tags(text: str) -> bool:
            if not text: return True
            return any(x in text for x in ["(ТУТ УКАЗЫВАЕМ", "УКАЗЫВАЕМ ПОЛ", "НАГРУЖЕННОСТЬ", "ПРИМУЩЕСТВО", "УКАЗЫВАЕМ  УКАЗЫВАЕМ"])

        # 1. Инфографика (Одежда)
        async with db.execute("SELECT value FROM app_settings WHERE key='infographic_clothing_prompt'") as cur:
            row = await cur.fetchone()
            if not row or has_old_tags(row[0]):
                text = r'''ROLE / TASK
Generate ONE modern high-fashion advertising poster in a magazine cover style,
derived from the uploaded product photo.
for a marketplace using ONLY the uploaded product photo.

Poster must be:
– stylish
– creative
– informative
– commercially strong

PRODUCT FIDELITY ONLY (visual accuracy of the clothing item must be exact)
All design, typography, layout and decorative elements are free, modern,
fashion-forward and may be highly expressive.

COLOR & SHADE LOCK
Reproduce the product color EXACTLY as in the photo:
– same hue, tone, temperature, saturation
– no recolor, no tint, no warming/cooling
– no harmonization with background or model
All small elements (belt, cuffs, quilting zones) must match the exact color.
Lighting changes must not shift product color.

NO PHOTO INSERTION
Do not insert or clip the original photo.
Render a completely new editorial-style image.

ADVANCED TYPOGRAPHY RANDOMIZATION (CRITICAL)

The poster must use a RANDOM modern, stylish, visually expressive font
that matches the product category and aesthetic.

Allowed styles:
– geometric modern sans
– elegant fashion serif
– high-contrast editorial serif
– minimalist grotesk
– soft rounded modern
– stylish condensed typefaces
– expressive display fonts (if still readable)

The font must always look:
– premium
– modern
– aesthetically strong
– visually distinctive
– not similar to default system fonts

Forbidden:
– generic system fonts (Arial, Roboto, Helvetica-like defaults)
– plain or basic typographic styles
– overly neutral, dull or standard typefaces
– repeated typographic look across outputs

The system must randomize typography selection every time, choosing
a visually appealing, fashionable, marketplace-ready typeface.

TYPOGRAPHY FREEDOM MODE

The system must select a unique font style for every output, fully independent
from previous generations.

Allowed:
– expressive display fonts
– fashion editorial serifs
– handwritten-like stylish fonts (if readable)
– geometric, bold or condensed styles
– decorative modern typography

The style may vary freely:
– weight
– contrast
– serif/sans serif
– proportions
– curves
– terminals

No limitation on baseline shape, stroke contrast or typographic geometry,
as long as the text remains readable.

LANGUAGE CONTROL (CRITICAL)
Infographic Language: {Язык инфографики}
ALL text must be written ONLY in this language.
Fix grammar automatically.
Professional marketplace copywriting.

All text must be rendered with ZERO AI artifacts.

The typography must be:
– perfectly smooth and clean
– free from distortions, glitches and warped geometry
– free from broken, duplicated, or melted characters
– free from random symbols or hallucinated glyphs
– free from uneven thickness, inconsistent stroke weight or pixel noise
– free from jagged or stair-stepped edges

Letters must always appear:
– with clean kerning and spacing

Forbidden:
– fragmented or half-rendered glyphs
– “AI handwriting” effect
– any visual signs of neural network generation

VISIBLE = REAL, INVISIBLE = NON-EXISTENT
Only features visible in the product photo may exist in the output.
No invented hardware, seams, textures, structure or lining.

TEXTURE & CONSTRUCTION RULE
Textures and patterns appear only where visible.
Construction, panels and quilting must match exactly.

NO CUT–PASTE
Render the product from scratch while preserving perfect fidelity.

IMAGE QUALITY
– high detail
– sharp
– clean
– realistic texture
– no blur or plastic effects

STYLE MODE BY CATEGORY
Product gender category: {Пол модели}

If WOMEN: modern editorial, elegant, trendy.
If MEN: строгий, геометричный, контрастный.
If KIDS: мягкие формы, дружелюбные элементы.

COLOR SYSTEM
Use 1–3 main colors plus neutrals.

TEXT CONTRAST
Text must remain readable in all cases (light text on dark, dark text on light).

INFOGRAPHIC COMPLEXITY LEVEL: {Нагруженность инфографики}

Level 1–3:
– 1 headline
– 2 advantages
– 1–2 icons
– 0 insets

Level 4–6:
– 1 headline
– 3 advantages
– 3–5 icons
– 1 inset
– 1 micro-copy

Level 7–8:
– 1 headline
– 3 advantages
– 5–7 icons
– 2 insets
– 2–3 micro-copies
– 1 extra block

Level 9–10:
– 1 headline + subheadline
– 3 advantages + 1–2 extra claims
– 7–10 icons
– 3 insets
– 3–5 micro-copies
– rich layout (side columns, badges)

INSET RULE
Inset panels must show only visible real details:
– seams
– texture
– quilting
– cuffs
– collar
– material surface
If insufficient unique zones exist, reuse a visible detail with different zoom.

INSET FIDELITY LOCK (CRITICAL)

Inset panels must reproduce the selected detail EXACTLY as it appears
in the uploaded product photo, with zero modification of:

– shape
– geometry
– fold direction
– curvature
– thickness
– stitching pattern
– quilting rhythm
– collar/hood construction
– material volume and texture
– fabric tension and compression

Inset details must look like a magnified crop of the REAL visible area from the
uploaded photo, NOT a cleaner, smoother, more symmetrical or more standard version.

INSET ANGLE LOCK (ABSOLUTE)

Inset panels must always use the EXACT SAME viewing angle and geometry
as the original product photo.

Forbidden for insets:
– rotating the detail to a different orientation
– showing the detail from a “cleaner” or “more frontal” angle
– changing perspective or projection
– straightening or centering the detail
– reconstructing hidden or obscured sides of the detail
– showing the collar, belt, cuff or quilting from an angle that is NOT visible in the photo

Insets must appear as if they are a magnified crop of the SAME camera angle,
SAME perspective, SAME lighting direction, and SAME geometry as the original image.

If the photo shows the detail partially, cut off, or at a shallow angle → the inset must
repeat that same partial shape without reconstruction or correction.

If the angle of a detail cannot be extracted without guessing → the inset MUST NOT be generated.

STRICT INSET SOURCE RULE (ABSOLUTE)

Inset panels must ALWAYS be a faithful magnified recreation ONLY of the EXACT
visible fragment from the uploaded product photo.

The inset must show:
– the same shape
– the same geometry
– the same folds and curves
– the same stitching and quilting
– the same texture
– the same lighting behavior
– the same viewing angle
– the same partial visibility if the detail is cropped

Forbidden for insets:
– inventing or adding any missing parts
– rotating the detail to another angle
– idealizing or beautifying the construction
– reconstructing hidden areas
– correcting asymmetry
– smoothing folds or straightening lines
– “guessing” how the detail should look
– using category knowledge to complete the design

If the exact detail cannot be reproduced WITHOUT INVENTION,
the inset MUST NOT be generated.

STRICTLY FORBIDDEN IN INSETS:
– improving, beautifying or idealizing the detail
– correcting asymmetry or irregularities
– smoothing or refinishing the geometry
– inventing missing parts
– completing unclear edges
– rounding or sharpening shapes
– using category-typical details when visibility is low

If the visible part of a detail is partially obscured, cropped or cut off in the
photo → the inset MUST show it with the SAME partial visibility.
No reconstruction or completion of the hidden zone.

If the model cannot identify a unique detail clearly → the inset must be skipped
or replaced with a zoom of another clearly visible area.

LAYOUT

VISUAL DESIGN RANDOMIZATION RULE (CRITICAL)

The infographic design must vary each time within a modern editorial style.

The system must randomly choose:
– icon style (outline / filled / geometric / linear / minimalistic / artistic)
– block styling (rounded cards, rectangles, shadows, strokes, layered panels)
– connector lines (straight / curved / dotted / geometric)
– accents (shapes, abstract forms, minimal patterns)
– micro-decor elements (subtle backgrounds, geometric fragments)

Allowed:
– stylish modern icons
– premium line-art
– soft geometric abstract forms
– editorial minimalism
– fashion-style micro accents

Forbidden:
– default generic icons
– basic pack icons
– repeated icon style across outputs
– outdated or overly simplistic visuals

All variations must remain coherent, premium and marketplace-ready.

ADVANCED ART DIRECTION RANDOMIZATION

The visual style of the infographic must vary every time within
the boundaries of modern fashion graphics.

Allowed variations:
– minimalistic, clean layouts
– bold fashion magazine compositions
– collage-style layering
– abstract geometric shapes
– soft pastel backgrounds
– high-contrast editorial blocks
– neon or vibrant accents
– smooth gradients
– artistic brush elements
– cutout-style frames
– modern big-typography compositions

The system must select a coherent but unique combination of:
– layout geometry
– card shapes
– panel layering
– decorative elements
– text placement logic
– accents
– visual hierarchy

Design must always remain:
– modern
– premium
– fashion-oriented
– marketplace-ready

Forbidden:
– template-like repetitive structure
– identical layout patterns across outputs
– standard “neutral” or “corporate” infographic styles

MICRO COPY
Short, relevant, and derived strictly from real visible characteristics.

PRODUCT INFO
Product / Brand Name: {Название товара}
Top 3 advantages: 
1. {Преимущество 1}
2. {Преимущество 2}
3. {Преимущество 3}

Дополнительная информация о продукте:
{Доп информация}
→ use as extra block when complexity >= 6

MODEL LOGIC (ONLY WHEN PRODUCT NEEDS A MODEL)
If product is одежда → model allowed.
If product is обувь / аксессуар / small item → close-up product priority.

MODEL USE GATE (CRITICAL)
Use a model ONLY if the garment can be reproduced on the model with 100% construction fidelity.
If there is any risk of invented elements → render the product without a model.


GARMENT COMPLETION RULE
If the uploaded product is:
– outerwear or tops → model must wear pants
– dress → model must not wear pants
– pants → model must wear a top that does not match product color and does not create a set
– footwear → model must wear neutral pants and neutral top
Non-product clothing must never match product color.

RANDOM MODEL APPEARANCE RULE

The model’s appearance must be generated randomly within the allowed range
for each output, without repeating a fixed look.

Allowed:
– European, Caucasian, Slavic, Mediterranean, Middle Eastern, Latin types
– natural variations of jawline, nose shape, lips, eyes, eyebrows
– natural variation of hairstyle, hair length, color (except unnatural colors)

Forbidden:
– Asian appearance
– African or Afro-American appearance
– unrealistic or stylized facial proportions
– cartoon-like or AI-distorted faces

The appearance must stay natural, realistic and human.
Hair, facial features and styling must vary freely, without pattern repetition.

MODEL ORIENTATION: {Угол камеры}

Если Спереди:
– фронтальный вид
– допускается лёгкий наклон корпуса или головы

Если Сзади:
– вид со спины
– допускается лёгкий поворот головы

MODEL POSE
{Поза}

Обычный:
– нейтральная коммерческая стойка
– спокойное положение тела
– руки в естественном положении

Вульгарный:
– выразительная, динамичная, провокационная поза
– смелая, эффектная, но реалистичная

Нестандартный:
– момент движения
– лёгкий шаг, поворот, наклон
– живая натуральная динамика

Любая поза не должна деформировать изделие или скрывать конструкцию.

CAMERA & FRAMING
Camera angle: {ракурс фотографии}

Дальний:
– модель в полный рост

Средний:
– от головы до середины бёдер
– акцент на пропорции товара

Близкий:
– пояс–голова или крупный план изделия
– максимальный акцент на товар

Без смешения планов и перспективных искажений.

MODEL PARAMETERS
SERVICE DATA VISIBILITY LOCK (ABSOLUTE)

The following parameters are service information ONLY and must NEVER appear
as text or labels on the final poster:

– model height
– model age
– model gender
– model body size
– garment parameters (length, sleeve type, pants cut)
– camera angle
– pose name
– orientation (front/back)
– any numeric or descriptive technical inputs

These parameters are strictly for internal AI logic.
Only the product name, brand name and product advantages may appear on the poster.
No other info may be shown.

Body size: {Размер модели}

BODY SIZE FIDELITY RULE:

Body size defines real physical body volume, mass and softness — NOT styling,
posture, fitness, angle or artistic interpretation.

Each size must show clear, realistic body differences:

42–44 → very slim
46–48 → slim
50–52 → slim-curvy with visible softness, NO athletic appearance
54–56 → curvy with clear belly volume and wide waist
58–60 → heavy with substantial mass
60+ → very large, massive body

Strictly forbidden for sizes 50+:
– flat abdomen
– tight abdomen
– athletic or fit body definition
– visible toned muscles
– narrow waist
– “plus-size but slim” interpretations

Pose, posture, camera angle, lighting and clothing must NOT hide, slim or compress
body volume. Body size ALWAYS overrides pose, styling, age and camera angle.

Height: {Рост модели}
Age: {Возраст модели}
Gender: {Пол модели}

GARMENT PARAMETERS
Product length: {Длина изделия}
Sleeve type: {Тип рукава}
Pants cut: {Тип кроя штанов}
If empty → use only what is visible.

CATEGORY DETECTION
Determine product category only from visible construction, without guessing.

NO SHAPE MODIFICATION
Garment must keep original fullness, silhouette, quilting, collar geometry, sleeve width and belt structure.
Model pose must not distort the garment.

FALLBACK RULE
If a detail cannot be confidently detected → omit it.
Never invent or assume.

FINAL QUALITY CHECK
– perfect text contrast
– correct layout per complexity
– insets only from visible zones
– modern icons and callouts
– 100% product fidelity
– exact color match
– zero invented details
– model neutral and product unobstructed'''
                await db.execute("INSERT INTO app_settings (key, value) VALUES ('infographic_clothing_prompt', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (text.strip(),))
                print("Migration: Updated infographic_clothing_prompt")

        # 2. Рандом прочее
        async with db.execute("SELECT value FROM app_settings WHERE key='random_other_prompt'") as cur:
            row = await cur.fetchone()
            if not row or has_old_tags(row[0]):
                text = r'''You are a professional product stylist and commercial photographer.
Analyze the uploaded image and identify the main product only.
Treat the product as a finished commercial item with a final, approved design.
Product Integrity (STRICT)
The product must remain 100% unchanged.
Do NOT:
rotate, flip, mirror, or invert the product
change orientation (front/back/side)
modify, redraw, rearrange, stylize, or “improve” any graphics, text, logos, or illustrations
alter colors, proportions, or layout of the product
The product must look exactly like the original photo, as if photographed in real life.
Scale & Reality (CRITICAL)
Use the real dimensions below.
The product must appear correctly sized relative to the environment and surrounding objects.
Overscaling or unrealistic proportions are not allowed.
Color & Visual Style (IMPORTANT)
Select a color palette that complements and enhances the product.
Rules:
Base the palette on the product’s colors, materials, and mood
Avoid default neutral-only palettes (plain white, beige, gray) unless clearly justified
Use modern, tasteful, and creative color combinations
Background and props may contrast with the product, but must not overpower it
Colors should feel intentional, contemporary, and visually rich
Safe, boring color choices are discouraged
Controlled creativity is required.
Scene & Complexity Control (VERY IMPORTANT)
Build the scene around the product.
Scene complexity level (1–10) is a hard limit, not a suggestion:
1–2 → almost empty, studio-like, max 1–2 simple props
3–4 → minimal lifestyle, few elements, lots of negative space
5–6 → balanced lifestyle scene
7–8 → rich but controlled environment
9–10 → dense, detailed lifestyle scene
Do NOT exceed the specified complexity level.
Low values must stay visibly simple.
The product must remain the clear focal point.
Product Details
Product type: {Название товара}
Photo angle / shot type: {Угол камеры}
Scene complexity level (1–10): {Нагруженность}
Parameters:
Width: {Ширина}
Height: {Высота}
Length: {Длина}
Season: {Сезон}
Style: {Стиль}


Human Presence (NEW – REQUIRED)
Human presence: {Присутствует ли человек на фото}
If Human presence is Yes:
Add one person interacting naturally with the product shown in the uploaded image
The interaction must be realistic, functional, and relevant to the product
The person must not distract from the product and must support its use or context
Add the following required field:
Gender: {Пол модели}
The model must be well-dressed, stylish, and visually appropriate to:
the product type
the season
the scene complexity
the overall visual mood
Natural Face Rendering (CRITICAL)
If a human is present in the scene, the face must look natural and realistic.
Rules:
No heavy beauty retouching
No “plastic”, “oily”, or overly smooth skin
Skin texture must be visible and realistic
Light natural wrinkles, fine lines, and pores are allowed and encouraged
Natural facial asymmetry is acceptable
Realistic skin imperfections are allowed
Avoid artificial beauty filters or CGI-like skin
The face should look like a real person photographed with professional lighting, not digitally polished.
If Human presence is No:
Do not add any people to the scene
Skip the Gender field entirely
Output Requirements
Ultra-realistic
Professional commercial photography
Correct perspective and lighting
No added text or watermarks'''
                await db.execute("INSERT INTO app_settings (key, value) VALUES ('random_other_prompt', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (text.strip(),))
                print("Migration: Updated random_other_prompt")

        # 3. Рандом
        async with db.execute("SELECT value FROM app_settings WHERE key='random_prompt'") as cur:
            row = await cur.fetchone()
            if not row or has_old_tags(row[0]):
                text = r'''You are a professional commercial fashion imaging AI. Your task is to take the uploaded product photo as the ONLY source of truth and present the product on a realistic human model strictly for sale purposes.

ABSOLUTE PRODUCT FIDELITY (CRITICAL):
The uploaded product photo is the only reference. The product must be reproduced with 100% accuracy including exact shape, silhouette, proportions, cut, construction, seams, stitching, materials, fabric texture, thickness impression, exact color and shade. It is strictly forbidden to redesign, stylize, improve, simplify, reinterpret, add or remove elements or invent details not visible on the photo. If a detail, material or texture is not clearly visible on the photo, it must be treated as non-existent.

FABRIC & TEXTURE DISTRIBUTION LOCK (ABSOLUTE):
Fabric type, knit structure and texture MUST be reproduced exactly as shown on the product photo AND ONLY in the areas where they are visible. If a specific texture (e.g. ribbed, knitted, “lapsha”, structured knit, smooth knit, woven fabric) appears only in certain zones of the product (such as neckline, collar, cuffs, hem or panels), it MUST remain strictly limited to those zones. It is strictly forbidden to extend, repeat, generalize or apply a visible texture or knit pattern to other parts of the product where it is not present on the photo. Any global material unification is a critical failure.

STRUCTURAL CONSTRUCTION LOCK (ABSOLUTE):
Any structural construction elements that exist on the product (including but not limited to neckline, collar, neck opening, cuffs, hems, closures, zippers, tongues, waistlines or openings) MUST be reproduced exactly as shown on the uploaded product photo. The AI is strictly forbidden to modify, reinterpret, stylize, adjust or “improve” the shape, height, width, depth, curvature, openness, fit or construction logic of any existing structural element. If a structural element is not clearly visible on the product photo, it must be treated as non-existent and must not be inferred.

GARMENT SURFACE CONDITION RULE (ABSOLUTE):
If the product on the photo shows wrinkles, creases or folds caused by storage or hanging, the product MUST be presented neatly steamed and smooth on the model. Removing wrinkles is allowed ONLY as surface smoothing. It is strictly forbidden to change fabric behavior, stiffness, thickness, drape, elasticity, knit structure or material appearance while smoothing. No reshaping, tightening or texture alteration is allowed.

PRODUCT COLOR LOCK (ABSOLUTE):
The AI must determine the exact product color exclusively from the uploaded photo. Color must match base color, undertone, saturation and brightness exactly. No recoloring, enhancement, lighting reinterpretation or stylistic shift is allowed. Lighting must not alter perceived color.

IMAGE RESOLUTION, SHARPNESS & OPTICAL QUALITY (CRITICAL)

The generated image must simulate a true high-end commercial fashion photograph captured in studio-grade Ultra High Definition (true 4K).

MANDATORY TECHNICAL REQUIREMENTS:
– ultra-high resolution look with true 4K-equivalent pixel density
– extreme micro-detail clarity on fabric, seams, stitching, edges and construction lines
– tack-sharp focus across the entire visible product area
– no softness, haze, blur, diffusion, glow or cinematic softness
– no motion blur, depth blur, lens blur or artificial bokeh on the product
– no painterly, illustrative or AI-smoothed textures

OPTICAL & SENSOR REALISM RULES:
– simulate professional commercial camera optics and sensor behavior (high-end fashion photography setup)
– realistic depth of field, but the product must remain 100% in sharp focus at all times
– natural micro-contrast and edge acuity without digital oversharpening
– edge definition must be crisp, clean and physically precise
– fabric texture must be clearly readable at close inspection
– stitching, seams and material transitions must be visibly distinct and realistic

ANTI-AI SMOOTHING & ANTI-RENDER LOCK:
– strictly forbid any neural smoothing, beauty smoothing or texture averaging
– strictly forbid plastic, waxy, rubbery or over-processed surfaces
– forbid CGI-like, render-like or synthetic surface appearance
– preserve natural fabric micro-structure and physical irregularities without exaggeration

COMPRESSION & OUTPUT QUALITY:
– image must look uncompressed and lossless
– no JPEG artifacts, noise blobs, aliasing or texture breakup
– clean tonal transitions without banding or posterization

PRIORITY RULE:
Image sharpness, resolution, texture readability and physical realism must NEVER be reduced for style, mood, lighting effects or artistic interpretation.

STRUCTURAL CONSTRUCTION LOCK (ABSOLUTE):
Any structural construction elements that exist on the product (including but not limited to neckline, collar, neck opening, cuffs, hems, closures, zippers, tongues, collars, waistlines or openings) MUST be reproduced exactly as shown on the uploaded product photo. The AI is strictly forbidden to modify, reinterpret, stylize, adjust or “improve” the shape, height, width, depth, curvature, openness, fit or construction logic of any existing structural element. If a structural element is not clearly visible on the product photo, it must be treated as non-existent and must not be inferred. Any deviation from original structural construction is a critical failure.

Location type: {Тип локации}
Rules: If На улице → image must be outdoors. If В помещении → image must be indoors. Mixing is forbidden.

2.LOCATION DESIGN DIVERSITY & STYLE RANDOMIZATION (CRITICAL): {Стиль локации}

If the Location style / subtype is a short generic phrase (length ≤ 18 characters, e.g. у кофейни, на улице, в помещении, у машины), the AI MUST generate a visually strong, contemporary environment aligned with global fashion, architecture and visual design standards of 2025.

The design language MUST be modern, bold and editorial, not cozy or lifestyle-oriented.

FORBIDDEN STYLES & MOODS:
– warm cozy interiors
– beige / cream / soft brown dominant palettes
– “comfortable”, “homey”, “vintage”, “loft lifestyle” aesthetics
– rustic, retro, classic, Scandinavian hygge
– warm ambient lighting as dominant mood

MANDATORY VISUAL CHARACTERISTICS:
– contemporary materials (glass, metal, concrete, stone, technical surfaces)
– clear geometry and spatial contrast
– neutral-to-cool or mixed temperature lighting with directional light
– fashion-editorial or architectural composition
– sense of modernity, clarity and visual tension

The AI MUST vary visual direction across generations using modern design approaches such as contemporary minimalism, architectural modern, urban editorial, experimental space, brutal-modern, high-fashion showroom or cinematic contemporary environments.

Repetition of the same color palette, lighting mood or spatial logic across generations is strictly forbidden.

Environmental lighting and design must never cast color reflections onto the product or alter perceived product color.

If the location refers to a real existing place, the AI MUST follow its real-world architectural identity regardless of text length.

Season: {Сезон}
Applied ONLY if Location type = На улице. Зима → visible snow; Лето → clear weather and sunlight; Осень → dry autumn leaves; Весна → fresh spring atmosphere. If В помещении → ignore completely.

Holiday: {Праздник}
Apply only a light, subtle holiday hint without heavy decorations or product changes. If empty → ignore.

Model’s pose: {Поза модели}
Обычный → natural commercial pose. Вульгарный → openly provocative pose. Нестандартная → unstable or transitional pose. Pose must never distort, hide or deform the product.

Body size of the model: {Размер модели}
BODY SIZE GEOMETRY RULE (ABSOLUTE): Body size defines real physical body volume, mass and softness, not styling, posture or fitness. Each higher size must be visibly larger and heavier than the previous one.
42–44 very slim; 46–48 slim; 50–52 slim-curvy with visible softness and NO athletic appearance; 54–56 curvy with clear belly volume and wide waist; 58–60 heavy with substantial mass; 60+ very large massive body.
FORBIDDEN FOR SIZES 50 AND ABOVE: flat or tight abdomen, athletic or fit body, toned muscles, narrow waist, “plus-size but slim” interpretation.
Pose, posture, camera angle or clothing must not slim or hide body volume. Body size always overrides age, pose, styling and camera angle.

Model height: {Рост модели}
Use exactly as specified.

Model’s age: {Возраст модели}
50+ → visible age signs and natural wrinkles; 65+ → pronounced aging. Any rejuvenation, blur or beauty filters are forbidden.

Pants cut type: {Тип кроя штанов}
If empty → choose a cut that naturally fits the product.

Sleeve type: {Тип рукава}
If empty → replicate sleeves exactly as on the product photo. If footwear → ignore.

Product length: {Длина изделия}
If specified → follow precisely. If empty → determine strictly from the product photo.

Model orientation: {Угол камеры}
Спереди → front view with slight tilt allowed. Сзади → back view with head turn allowed.

Camera angle: {ракурс фотографии}
CAMERA FRAMING LOCK (ABSOLUTE):
Дальний → full body head to feet only.
Средний → head to mid-thigh ONLY; legs below mid-thigh must not be visible.
Близкий → waist to head ONLY; hips and legs must not be visible.
Product category rules must NOT expand framing beyond the specified camera angle.

Gender: {Пол модели}
Specify explicitly.

PRODUCT CATEGORY LOGIC (CRITICAL):
Upper garments require suitable bottoms that do not hide the product. Dresses must never have pants. Long coats or robes must not show pants. Pants as product require a top that does not cover waist or cut. Footwear requires suitable complementary clothing.

MODEL APPEARANCE AND RANDOMIZATION (CRITICAL):

Randomization is mandatory and should vary depending on certain categories of appearance.

FORBIDDEN BY APPEARANCE:
Asian, African, and African-American types are strictly prohibited.

Any kind of hairstyle and hair styling is allowed!

SKIN REALISM LOCK (ABSOLUTE):
Skin must be natural and physically realistic. Glossy, oily, plastic, porcelain or beauty-retouched skin is forbidden. Visible pores and natural texture are required.

MODEL REUSE PREVENTION (FAIL-SAFE):
If face, hairstyle, hair color or overall appearance is visually similar to a previous generation, the result is INVALID and must be regenerated.

FINAL GOAL:
Produce a realistic, professional, sale-ready image where commercial presentation NEVER overrides product construction, proportions, fit, structure or color accuracy.'''
                await db.execute("INSERT INTO app_settings (key, value) VALUES ('random_prompt', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (text.strip(),))
                print("Migration: Updated random_prompt")

        # 4. Белый фон
        async with db.execute("SELECT value FROM app_settings WHERE key='whitebg_prompt'") as cur:
            row = await cur.fetchone()
            if not row or has_old_tags(row[0]):
                text = r'''ROLE / SYSTEM TASK

You are a professional commercial product visualization AI used for marketplaces, brand catalogs, and e-commerce vitrines.

Your task is to analyze the uploaded real product photo and generate a photorealistic 3D-render-style product image on a pure white background, visually indistinguishable from a real studio photograph.

The result must look like a high-end retail vitrine product photo, NOT like obvious CGI or synthetic 3D.

SOURCE OF TRUTH (CRITICAL)

The uploaded product photo is the ONLY and ABSOLUTE SOURCE OF TRUTH.

You must study the product carefully.

You must analyze only the product itself, NOT the background.

Color(s), material, shape, proportions, construction, seams, edges, thickness, texture, and all physical details must be derived strictly from the product visible in the photo.

🚫 DO NOT copy-paste, overlay, or reuse the original photo in any form.
🚫 DO NOT place the original photo on top of a background.
🚫 DO NOT partially reuse pixels, silhouettes, shadows, or cutouts from the source image.

The final image must be a newly generated, reconstructed product, not a manipulation of the original image.

PRODUCT RECONSTRUCTION RULES (HIGHEST PRIORITY)

Recreate the product with 100% structural fidelity:

Exact silhouette and proportions

Exact cut and geometry

Exact number and placement of seams, stitches, panels

Exact edges, folds, thickness, and volume

Exact material appearance (fabric, leather, plastic, metal, etc.)

Exact color(s) of the product itself (ignore background lighting)

🚫 FORBIDDEN ACTIONS

Adding buttons, zippers, pockets, logos, straps, patterns, prints, textures, or any elements not present in the original photo

Removing elements that exist in the original photo

“Improving”, “enhancing”, “stylizing”, or “modernizing” the design

Guessing hidden details that are not visible

Symmetry correction if the product is asymmetrical in the photo

If a detail is not clearly visible, keep it neutral and minimal, never invented.

COLOR & MATERIAL INTELLIGENCE

Analyze only the product’s real color(s), not reflections from background or lighting.

Do not change hue, saturation, brightness, or tone.

Do not “beautify” colors.

Material realism is mandatory: fabric grain, matte/gloss level, softness, rigidity must match reality.

WRINKLES & CONDITION NORMALIZATION

If the product in the photo shows:

Wrinkles

Creases

Folding marks

Signs of being un-ironed or deformed by storage

You must render the product as:

Perfectly straightened

Neatly arranged

Ironed / smoothed

Retail-ready condition

⚠️ This applies ONLY to surface condition.
⚠️ Structural shape, cut, and proportions must remain unchanged.

PHOTOREALISTIC 3D STYLE (CRITICAL)

The output must:

Look like a real studio product photograph

Be indistinguishable from a DSLR or medium-format camera shot

Avoid visible CGI traits (plastic look, fake highlights, unnatural edges)

Lighting:

Soft, neutral studio lighting

Natural shadows under the product

No dramatic, artistic, or cinematic lighting

Background:

Pure white (#FFFFFF)

No gradients

No textures

No reflections

No environment

Camera:

Neutral focal length (no distortion)

Product centered

Clean, commercial framing

ABSOLUTE PROHIBITIONS

🚫 Do NOT:

Copy the original photo

Paste the original product image onto a background

Add branding, text, labels, watermarks

Add props, models, hands, stands (unless visible in original photo)

Change product orientation unless clearly required for vitrine presentation

Add “AI enhancements” or fictional improvements

QUALITY CONTROL CHECK (MANDATORY INTERNAL STEP)

Before finalizing the image, verify internally:

Is this a newly generated product, not a reused photo?

Does every visible detail exist in the original photo?

Are there ZERO invented elements?

Does it look like a real retail product photo, not CGI?

Is the background pure white and clean?

Is the product ironed and neat, without altering structure?

If any answer is “NO” → regenerate.

FINAL OUTPUT REQUIREMENT

Produce ONE single, high-resolution, photorealistic product image suitable for:

Marketplace product card

Online store vitrine

Brand catalog

No explanations.
No captions.
No text overlays.
Image only.'''
                await db.execute("INSERT INTO app_settings (key, value) VALUES ('whitebg_prompt', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (text.strip(),))
                print("Migration: Updated whitebg_prompt")

        # 5. Очистка всех промптов в таблице prompts (для пресетов)
        async with db.execute("SELECT id, text FROM prompts") as cur:
            rows = await cur.fetchall()
            for pid, ptext in rows:
                if ptext and "(ТУТ УКАЗЫВАЕМ" in ptext:
                    new_text = ptext.replace("(ТУТ УКАЗЫВАЕМ Пол модели)", "{Пол модели}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ ШИРИНУ)", "{Ширина}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ ВЫСОТУ)", "{Высота}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ ДЛИНУ)", "{Длина}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ СЕЗОН)", "{Сезон}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ СТИЛЬ)", "{Стиль}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ Присутствует ли человек на фото)", "{Присутствует ли человек на фото}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ Нагруженность инфографики)", "{Нагруженность}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ Угол камеры)", "{Угол камеры}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ Поза модели)", "{Поза}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ Рост модели)", "{Рост модели}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ Возраст модели)", "{Возраст модели}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ РАЗМЕР МОДЕЛИ)", "{Размер модели}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ ЯЗЫК ИНФОГРАФИКИ)", "{Язык инфографики}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ ПРИМУЩЕСТВО 1)", "{Преимущество 1}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ ПРИМУЩЕСТВО 2)", "{Преимущество 2}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ ПРИМУЩЕСТВО 3)", "{Преимущество 3}") \
                                     .replace("(ТУТ УКАЗЫВАЕМ ДОП ЧТО УГОДНО О ТОВАРЕ)", "{Доп информация}")
                    await db.execute("UPDATE prompts SET text=? WHERE id=?", (new_text, pid))
                    print(f"Migration: Cleaned up prompt ID {pid}")

        await db.commit()
    except Exception as e:
        print(f"Migration error (prompts update): {e}")


def _normalize_placeholder_label(text: str, fallback: str) -> str:
    if not text:
        return fallback
    
    # 1. Очистка текста
    clean = re.sub(r"[^0-9A-Za-zА-Яа-яЁё ]+", "", text).strip()
    clean = re.sub(r"\s+", " ", clean).strip()
    
    # 2. Убираем типовые префиксы
    for prefix in ("Выберите ", "Введите ", "Пришлите ", "Загрузите "):
        if clean.lower().startswith(prefix.lower()):
            clean = clean[len(prefix):].strip()
            break
            
    low = clean.lower()
    
    # 3. Интеллектуальный маппинг для объединения дублей (по смыслу)
    mapping = {
        "возраст": "Возраст модели",
        "телосложение": "Телосложение",
        "размер одежды": "Телосложение",
        "рост": "Рост модели",
        "пол": "Пол модели",
        "тип позы": "Поза модели",
        "поза": "Поза модели",
        "угол камеры": "Угол камеры",
        "вид фотографии": "Угол камеры",
        "ракурс": "Ракурс",
        "сезон": "Сезон",
        "праздник": "Праздник",
        "нагруженность": "Нагруженность инфографики",
        "язык": "Язык инфографики",
        "название товара": "Название товара/бренда",
        "преимущество 1": "Топ 1 преимущества товара",
        "преимущество 2": "Топ 2 преимущества товара",
        "преимущество 3": "Топ 3 преимущества товара",
        "преимущества": "Топ 1 преимущества товара",
        "доп текст": "Дополнительная информация о продукте",
        "тип кроя штанов": "Тип кроя штанов",
        "тип рукав": "Тип рукава",
        "длина изделия": "Длина изделия",
        "формат фото": "Формат фото",
        "фото товара": "Фото товара",
        "фото фона": "Фото фона",
        "фотографию модели": "Фото модели",
        "ширину": "Ширина",
        "высоту": "Высота",
        "длину см": "Длина",
        "модель": "Модель"
    }
    
    for key, val in mapping.items():
        if key in low:
            return val

    if len(clean) > 40:
        clean = clean[:40].rstrip()
        
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
        key = p["label"].lower()
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
            if "prompt" not in h_cols:
                try:
                    await db.execute("ALTER TABLE generation_history ADD COLUMN prompt TEXT")
                    await db.commit()
                except Exception as e: print(f"Migration error (history.prompt): {e}")
    
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

CATEGORIES = ["presets", "female", "male", "child", "boy", "girl", "storefront", "whitebg", "random", "random_other", "own", "own_variant", "infographic_clothing", "infographic_other"]

@app.get("/models/toggle/{model_id}")
async def toggle_model_status(model_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    """Включает/выключает модель (пресет)"""
    async with db.execute("SELECT is_active FROM models WHERE id=?", (model_id,)) as cur:
        row = await cur.fetchone()
        if not row:
            return RedirectResponse(url="/prompts", status_code=303)
        current = row[0]
    
    new_val = 0 if current == 1 else 1
    await db.execute("UPDATE models SET is_active=? WHERE id=?", (new_val, model_id))
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

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
    # Промпты категорий (используются в боте)
    cat_prompt_keys = [
        "whitebg_prompt",
        "random_prompt",
        "random_other_prompt",
        "storefront_prompt",
        "infographic_clothing_prompt",
        "infographic_other_prompt",
        "own_prompt",
        "own_variant_prompt",
    ]
    cat_prompts = {}
    async with db.execute(
        f"SELECT key, value FROM app_settings WHERE key IN ({','.join(['?']*len(cat_prompt_keys))})",
        cat_prompt_keys
    ) as cur:
        rows = await cur.fetchall()
        for r in rows:
            cat_prompts[r[0]] = r[1]
    for k in cat_prompt_keys:
        cat_prompts.setdefault(k, "")

    return templates.TemplateResponse("prompts.html", {
        "request": request, 
        "categorized_models": categorized_models, 
        "categories": CATEGORIES,
        "prompt_placeholders": prompt_placeholders,
        "cat_prompts": cat_prompts
    })

@app.post("/prompts/category_prompts")
async def update_category_prompts(
    request: Request,
    whitebg_prompt: str = Form(""),
    random_prompt: str = Form(""),
    random_other_prompt: str = Form(""),
    storefront_prompt: str = Form(""),
    infographic_clothing_prompt: str = Form(""),
    infographic_other_prompt: str = Form(""),
    own_prompt: str = Form(""),
    own_variant_prompt: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db),
    user: str = Depends(get_current_username)
):
    payload = {
        "whitebg_prompt": whitebg_prompt,
        "random_prompt": random_prompt,
        "random_other_prompt": random_other_prompt,
        "storefront_prompt": storefront_prompt,
        "infographic_clothing_prompt": infographic_clothing_prompt,
        "infographic_other_prompt": infographic_other_prompt,
        "own_prompt": own_prompt,
        "own_variant_prompt": own_variant_prompt,
        # совместимость: единый промпт для "Свой вариант (одежда)"
        "own_prompt1": own_prompt,
        "own_prompt2": own_prompt,
        "own_prompt3": own_prompt,
    }
    for key, value in payload.items():
        await db.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, (value or "").strip())
        )
    await db.commit()
    return RedirectResponse(url="/prompts", status_code=303)

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
        async with db.execute("SELECT * FROM api_keys ORDER BY is_active DESC, id") as cur:
            gemini_keys = await cur.fetchall()
    except Exception: gemini_keys = []
    
    return templates.TemplateResponse("api_keys.html", {"request": request, "gemini_keys": gemini_keys})

@app.post("/api_keys/add")
async def add_key(token: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    # Очистка токена от всего лишнего
    token = "".join(token.split())
    
    # Исправляем кириллицу
    cyr_to_lat = {
        'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H', 
        'О': 'O', 'Р': 'P', 'С': 'C', 'Т': 'T', 'У': 'y', 'Х': 'X',
        'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x'
    }
    new_token = ""
    for char in token:
        new_token += cyr_to_lat.get(char, char)
    token = new_token

    import re
    token = re.sub(r'[^A-Za-z0-9_\-]', '', token)
    
    await db.execute("INSERT INTO api_keys (token) VALUES (?)", (token,))
    await db.commit()
    return RedirectResponse(url="/api_keys", status_code=303)

@app.get("/api_keys/delete/{key_id}")
async def delete_key(key_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
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
        "SELECT id, step_key, question_text, question_text_en, question_text_vi, input_type, is_optional, order_index FROM steps WHERE category_id=? ORDER BY order_index, id",
        (cat_id,)
    ) as cur:
        steps = await cur.fetchall()
    
    steps_with_options = []
    for step in steps:
        async with db.execute(
            "SELECT id, option_text, option_text_en, option_text_vi, option_value, order_index, custom_prompt FROM step_options WHERE step_id=? ORDER BY order_index, id",
            (step['id'],)
        ) as cur_opt:
            options_raw = await cur_opt.fetchall()
            options = [
                {
                    "id": r[0],
                    "text": r[1],
                    "text_en": r[2] or "",
                    "text_vi": r[3] or "",
                    "value": r[4],
                    "order": r[5],
                    "prompt": r[6] or ""
                } for r in options_raw
            ]
        
        steps_with_options.append({
            "id": step['id'],
            "key": step['step_key'],
            "question": step['question_text'],
            "question_en": step['question_text_en'] or "",
            "question_vi": step['question_text_vi'] or "",
            "type": step['input_type'],
            "optional": step['is_optional'],
            "order": step['order_index'],
            "options": options
        })

    # Получаем библиотеки для конструктора
    async with db.execute("SELECT id, step_key, question_text, question_text_en, question_text_vi, input_type FROM library_steps ORDER BY id") as cur:
        lib_steps_raw = await cur.fetchall()

    lib_steps = []
    for step in lib_steps_raw:
        step_id, step_key, question_text, question_text_en, question_text_vi, input_type = step
        async with db.execute(
            "SELECT option_text, option_text_en, option_text_vi, option_value, custom_prompt FROM library_step_options WHERE step_id=? ORDER BY order_index, id",
            (step_id,)
        ) as cur:
            opts = await cur.fetchall()
        default_buttons = json.dumps(
            [{"text": o[0], "text_en": o[1] or "", "text_vi": o[2] or "", "value": o[3], "prompt": o[4] or ""} for o in opts],
            ensure_ascii=False
        )
        lib_steps.append({
            "id": step_id,
            "step_key": step_key,
            "question_text": question_text,
            "question_text_en": question_text_en or "",
            "question_text_vi": question_text_vi or "",
            "input_type": input_type,
            "default_buttons": default_buttons
        })

    async with db.execute("SELECT id, name FROM button_categories ORDER BY id") as cur:
        button_cats = await cur.fetchall()

    lib_buttons = {}
    for bcat in button_cats:
        async with db.execute(
            "SELECT id, option_text, option_text_en, option_text_vi, option_value, custom_prompt FROM library_options WHERE category_id=? ORDER BY id", 
            (bcat['id'],)
        ) as cur:
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


@app.get("/constructor/category/{cat_id}/languages", response_class=HTMLResponse)
async def category_languages_page(request: Request, cat_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    async with db.execute("SELECT id, key, name_ru, is_active, order_index FROM categories WHERE id=?", (cat_id,)) as cur:
        category = await cur.fetchone()
    if not category:
        return RedirectResponse("/constructor")

    async with db.execute(
        "SELECT id, step_key, question_text, question_text_en, question_text_vi "
        "FROM steps WHERE category_id=? ORDER BY order_index, id",
        (cat_id,)
    ) as cur:
        steps = await cur.fetchall()

    options_by_step = {}
    async with db.execute(
        "SELECT id, step_id, option_text, option_text_en, option_text_vi, option_value "
        "FROM step_options WHERE step_id IN (SELECT id FROM steps WHERE category_id=?) "
        "ORDER BY step_id, order_index, id",
        (cat_id,)
    ) as cur:
        rows = await cur.fetchall()
        for row in rows:
            options_by_step.setdefault(row["step_id"], []).append(row)

    return templates.TemplateResponse("category_languages.html", {
        "request": request,
        "category": category,
        "steps": steps,
        "options_by_step": options_by_step
    })


@app.post("/constructor/category/{cat_id}/save_translations")
async def save_category_translations(request: Request, cat_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    form = await request.form()
    for key, val in form.items():
        value = (val or "").strip()
        if key.startswith("step_"):
            parts = key.split("_")
            if len(parts) == 3:
                step_id = int(parts[1])
                lang = parts[2]
                if lang in ("en", "vi"):
                    col = f"question_text_{lang}"
                    await db.execute(f"UPDATE steps SET {col}=? WHERE id=?", (value, step_id))
        elif key.startswith("opt_"):
            parts = key.split("_")
            if len(parts) == 3:
                opt_id = int(parts[1])
                lang = parts[2]
                if lang in ("en", "vi"):
                    col = f"option_text_{lang}"
                    await db.execute(f"UPDATE step_options SET {col}=? WHERE id=?", (value, opt_id))
    await db.commit()
    return RedirectResponse(f"/constructor/category/{cat_id}/languages", status_code=303)

@app.post("/constructor/category/update/{cat_id}")
async def admin_update_category(cat_id: int, name: str = Form(...), key: str = Form(...), is_active: int = Form(1), order: int = Form(0), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute(
        "UPDATE categories SET name_ru=?, key=?, is_active=?, order_index=? WHERE id=?",
        (name, key, is_active, order, cat_id)
    )
    await db.commit()
    return RedirectResponse(f"/constructor/category/{cat_id}", status_code=303)

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
    try:
        data = await request.json()
        print(f"Starting save_all for category {cat_id}. Data: {len(data.get('steps', []))} steps.")
        steps_data = data.get("steps", [])
        
        # Получаем текущие ID шагов этой категории
        async with db.execute("SELECT id FROM steps WHERE category_id=?", (cat_id,)) as cur:
            existing_step_ids = [row[0] for row in await cur.fetchall()]
        
        received_step_ids = []
        
        for s_data in steps_data:
            step_id = s_data.get("id")
            step_key = s_data.get("key")
            question = s_data.get("question")
            question_en = s_data.get("question_en") or ""
            question_vi = s_data.get("question_vi") or ""
            input_type = s_data.get("type")
            is_optional = s_data.get("optional")
            order_index = int(s_data.get("order") or 0)
            buttons = s_data.get("buttons", [])
            
            # Конвертация step_id
            if step_id == 'null' or step_id is None:
                step_id = None
            else:
                try:
                    step_id = int(step_id)
                except (ValueError, TypeError):
                    step_id = None
            
            if step_id and step_id in existing_step_ids:
                # Обновляем существующий шаг
                await db.execute(
                    "UPDATE steps SET question_text=?, question_text_en=?, question_text_vi=?, input_type=?, is_optional=?, order_index=?, step_key=? WHERE id=?",
                    (question, question_en, question_vi, input_type, is_optional, order_index, step_key, step_id)
                )
                received_step_ids.append(step_id)
            else:
                # Создаем новый шаг
                await db.execute(
                    "INSERT INTO steps (category_id, step_key, question_text, question_text_en, question_text_vi, input_type, is_optional, order_index) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (cat_id, step_key, question, question_en, question_vi, input_type, is_optional, order_index)
                )
                async with db.execute("SELECT last_insert_rowid()") as cur_last_step:
                    step_id = (await cur_last_step.fetchone())[0]
                received_step_ids.append(step_id)
                
            # Работа с кнопками (опциями) этого шага
            async with db.execute("SELECT id FROM step_options WHERE step_id=?", (int(step_id),)) as cur_opts:
                existing_opt_ids = [row[0] for row in await cur_opts.fetchall()]
                
            received_opt_ids = []
            for b_data in buttons:
                opt_id = b_data.get("id")
                opt_text = b_data.get("text")
                opt_text_en = b_data.get("text_en")
                opt_text_vi = b_data.get("text_vi")
                opt_value = b_data.get("value")
                opt_prompt = b_data.get("prompt")
                opt_order = int(b_data.get("order") or 0)
                
                # Если opt_id - строка 'null', приводим к None
                if opt_id == 'null' or opt_id is None:
                    opt_id = None
                else:
                    try:
                        opt_id = int(opt_id)
                    except (ValueError, TypeError):
                        opt_id = None
                
                if opt_id and opt_id in existing_opt_ids:
                    await db.execute(
                        "UPDATE step_options SET option_text=?, option_text_en=?, option_text_vi=?, option_value=?, order_index=?, custom_prompt=? WHERE id=?",
                        (opt_text, opt_text_en, opt_text_vi, opt_value, opt_order, opt_prompt, opt_id)
                    )
                    received_opt_ids.append(opt_id)
                else:
                    await db.execute(
                        "INSERT INTO step_options (step_id, option_text, option_text_en, option_text_vi, option_value, order_index, custom_prompt) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (int(step_id), opt_text, opt_text_en, opt_text_vi, opt_value, opt_order, opt_prompt)
                    )
                    async with db.execute("SELECT last_insert_rowid()") as cur_last_opt:
                        received_opt_ids.append((await cur_last_opt.fetchone())[0])
                        
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
    except Exception as e:
        print(f"Error in save_all_steps: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/constructor/library/step/add")
async def admin_add_library_step(step_key: str = Form(...), question: str = Form(...), input_type: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute(
        "INSERT INTO library_steps (step_key, question_text, input_type) VALUES (?, ?, ?)",
        (step_key, question, input_type)
    )
    await db.commit()
    return RedirectResponse(request.headers.get("referer", "/constructor"), status_code=303)

@app.post("/constructor/library/step/update/{step_id}")
async def admin_update_library_step(step_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    data = await request.json()
    step_data = data.get("step", {})
    options = data.get("options", [])
    await db.execute(
        "UPDATE library_steps SET step_key=?, question_text=?, input_type=? WHERE id=?",
        (step_data.get("key"), step_data.get("question"), step_data.get("type"), step_id)
    )

    # Синхронизация опций
    async with db.execute("SELECT id FROM library_step_options WHERE step_id=?", (step_id,)) as cur:
        existing_ids = [row[0] for row in await cur.fetchall()]
    received_ids = []
    for b_data in options:
        opt_id = b_data.get("id")
        opt_text = b_data.get("text")
        opt_text_en = b_data.get("text_en") or ""
        opt_text_vi = b_data.get("text_vi") or ""
        opt_value = b_data.get("value")
        opt_prompt = b_data.get("prompt")
        opt_order = b_data.get("order")

        if opt_id == 'null' or opt_id is None:
            opt_id = None
        else:
            try:
                opt_id = int(opt_id)
            except (ValueError, TypeError):
                opt_id = None

        if opt_id and opt_id in existing_ids:
            await db.execute(
                "UPDATE library_step_options SET option_text=?, option_text_en=?, option_text_vi=?, option_value=?, order_index=?, custom_prompt=? WHERE id=?",
                (opt_text, opt_text_en, opt_text_vi, opt_value, opt_order, opt_prompt, opt_id)
            )
            received_ids.append(opt_id)
        else:
            await db.execute(
                "INSERT INTO library_step_options (step_id, option_text, option_text_en, option_text_vi, option_value, order_index, custom_prompt) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (step_id, opt_text, opt_text_en, opt_text_vi, opt_value, opt_order, opt_prompt)
            )
            async with db.execute("SELECT last_insert_rowid()") as cur_last_opt:
                received_ids.append((await cur_last_opt.fetchone())[0])

    for old_id in existing_ids:
        if old_id not in received_ids:
            await db.execute("DELETE FROM library_step_options WHERE id=?", (old_id,))

    await db.commit()
    return JSONResponse({"status": "ok"})

@app.post("/constructor/library/step/delete/{step_id}")
async def admin_delete_library_step(step_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("DELETE FROM library_step_options WHERE step_id=?", (step_id,))
    await db.execute("DELETE FROM library_steps WHERE id=?", (step_id,))
    await db.commit()
    return RedirectResponse(request.headers.get("referer", "/constructor"), status_code=303)

@app.post("/constructor/library/button/add")
async def admin_add_library_button(request: Request, text: str = Form(...), text_en: str = Form(""), text_vi: str = Form(""), value: str = Form(...), category: str = Form("Системные"), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
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
        "INSERT INTO library_options (category_id, option_text, option_text_en, option_text_vi, option_value) VALUES (?, ?, ?, ?, ?)",
        (cat_id, text, text_en, text_vi, value)
    )
    await db.commit()
    return RedirectResponse(request.headers.get("referer", "/constructor"), status_code=303)

@app.post("/constructor/library/button/delete/{btn_id}")
async def admin_delete_library_button(request: Request, btn_id: int, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("DELETE FROM library_options WHERE id=?", (btn_id,))
    await db.commit()
    return RedirectResponse(request.headers.get("referer", "/constructor"), status_code=303)

@app.post("/constructor/library/category/add")
async def admin_add_library_category(request: Request, name: str = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("INSERT OR IGNORE INTO button_categories (name) VALUES (?)", (name,))
    await db.commit()
    return RedirectResponse(request.headers.get("referer", "/constructor"), status_code=303)

# --- Техподдержка ---

@app.get("/support", response_class=HTMLResponse)
async def get_support(request: Request, user_id: int = None, db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    # Список пользователей, писавших в поддержку
    async with db.execute("""
        SELECT u.id, u.username, u.first_name, 
               (SELECT COUNT(*) FROM support_messages WHERE user_id = u.id AND is_admin = 0 AND is_read = 0) as unread_count,
               (SELECT MAX(created_at) FROM support_messages WHERE user_id = u.id) as last_msg_at
        FROM users u
        WHERE EXISTS (SELECT 1 FROM support_messages WHERE user_id = u.id)
        ORDER BY last_msg_at DESC
    """) as cur:
        support_users = await cur.fetchall()

    messages = []
    current_user = None
    if user_id:
        # Помечаем как прочитанные
        await db.execute("UPDATE support_messages SET is_read = 1 WHERE user_id = ? AND is_admin = 0", (user_id,))
        await db.commit()
        
        async with db.execute("SELECT message_text, is_admin, created_at, file_id, file_type FROM support_messages WHERE user_id = ? ORDER BY created_at ASC", (user_id,)) as cur:
            messages = await cur.fetchall()
        
        async with db.execute("SELECT id, username, first_name FROM users WHERE id = ?", (user_id,)) as cur:
            current_user = await cur.fetchone()

    return templates.TemplateResponse("support.html", {
        "request": request, 
        "support_users": support_users, 
        "messages": messages, 
        "current_user": current_user
    })

@app.get("/support/file/{file_id}")
async def proxy_telegram_file(file_id: str, user: str = Depends(get_current_username)):
    """Проксирует файл из Telegram для отображения в админке"""
    try:
        settings = load_settings()
        async with httpx.AsyncClient() as client:
            # 1. Получаем путь к файлу
            get_file_url = f"https://api.telegram.org/bot{settings.bot_token}/getFile?file_id={file_id}"
            resp = await client.get(get_file_url)
            file_data = resp.json()
            if not file_data.get("ok"):
                return Response(status_code=404)
            
            file_path = file_data["result"]["file_path"]
            # 2. Скачиваем сам файл
            download_url = f"https://api.telegram.org/file/bot{settings.bot_token}/{file_path}"
            file_resp = await client.get(download_url)
            
            return Response(content=file_resp.content, media_type=file_resp.headers.get("content-type"))
    except Exception as e:
        print(f"Error proxying file {file_id}: {e}")
        return Response(status_code=500)

@app.post("/support/send")
async def send_support_reply(
    user_id: int = Form(...),
    message_text: str = Form(None),
    file: UploadFile = File(None),
    db: aiosqlite.Connection = Depends(get_db),
    user: str = Depends(get_current_username)
):
    try:
        settings = load_settings()
        file_id = None
        file_type = 'text'
        
        async with httpx.AsyncClient() as client:
            if file and file.filename:
                # Читаем контент файла
                file_content = await file.read()
                files = {"photo" if "image" in file.content_type else "video": (file.filename, file_content, file.content_type)}
                
                method = "sendPhoto" if "image" in file.content_type else "sendVideo"
                url = f"https://api.telegram.org/bot{settings.bot_token}/{method}"
                
                payload = {"chat_id": user_id}
                if message_text:
                    payload["caption"] = f"👨‍💻 <b>Ответ поддержки:</b>\n\n{message_text}"
                    payload["parse_mode"] = "HTML"
                else:
                    payload["caption"] = "👨‍💻 <b>Ответ поддержки</b>"
                    payload["parse_mode"] = "HTML"

                resp = await client.post(url, data=payload, files=files)
                result = resp.json()
                
                if result.get("ok"):
                    msg = result["result"]
                    if "photo" in msg:
                        file_id = msg["photo"][-1]["file_id"]
                        file_type = 'photo'
                    elif "video" in msg:
                        file_id = msg["video"]["file_id"]
                        file_type = 'video'
            
            elif message_text:
                url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
                payload = {
                    "chat_id": user_id,
                    "text": f"👨‍💻 <b>Ответ поддержки:</b>\n\n{message_text}",
                    "parse_mode": "HTML"
                }
                resp = await client.post(url, json=payload)
                result = resp.json()

            # Сохраняем в БД
            await db.execute(
                "INSERT INTO support_messages (user_id, message_text, file_id, file_type, is_admin, is_read) VALUES (?, ?, ?, ?, 1, 1)",
                (user_id, message_text, file_id, file_type)
            )
            await db.commit()

        return RedirectResponse(url=f"/support?user_id={user_id}", status_code=303)
    except Exception as e:
        print(f"Error sending support reply: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/support/mark_read")
async def mark_read(user_id: int = Form(...), db: aiosqlite.Connection = Depends(get_db), user: str = Depends(get_current_username)):
    await db.execute("UPDATE support_messages SET is_read = 1 WHERE user_id = ? AND is_admin = 0", (user_id,))
    await db.commit()
    return {"status": "ok"}
