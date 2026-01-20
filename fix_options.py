import asyncio
import os
import sys
import aiosqlite

# Добавляем корневую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.db import Database

async def fix():
    # Пробуем найти базу данных в разных местах
    possible_paths = ["data/bot.db", "bot.db", "/app/data/bot.db"]
    db_path = None
    for p in possible_paths:
        if os.path.exists(p):
            db_path = p
            break
    
    if not db_path:
        db_path = "data/bot.db"
        print(f"Database not found, creating new at {db_path}")
    else:
        print(f"Found database at {db_path}")

    db = Database(db_path)
    await db.init() # Это создаст таблицы и запустит seed если пусто
    
    print(f"Clearing and re-seeding all categories, steps and options in {db_path}...")
    
    async with aiosqlite.connect(db_path) as conn:
        try:
            await conn.execute("DELETE FROM step_options")
            await conn.execute("DELETE FROM steps")
            await conn.execute("DELETE FROM categories")
            await conn.commit()
            print("Successfully cleared tables.")
        except Exception as e:
            print(f"Error during clear: {e}")
    
    # Теперь вызываем _seed_categories напрямую
    # Мы обновили ее в db.py, теперь она содержит ВСЕ опции для ВСЕХ категорий
    await db._seed_categories()
    
    # Проверка
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("SELECT COUNT(*) FROM categories") as cur:
            cat_count = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM steps") as cur:
            step_count = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM step_options") as cur:
            opt_count = (await cur.fetchone())[0]
            
    print(f"Re-seed complete: {cat_count} categories, {step_count} steps, {opt_count} options created.")

if __name__ == "__main__":
    asyncio.run(fix())
