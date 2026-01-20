
import asyncio
import aiosqlite
from bot.db import Database

async def check():
    db = Database("data/bot.db")
    await db.init()
    
    async with aiosqlite.connect("data/bot.db") as conn:
        print("--- CATEGORIES ---")
        async with conn.execute("SELECT id, key, name FROM categories") as cur:
            categories = await cur.fetchall()
            for c_id, c_key, c_name in categories:
                print(f"Category {c_key} (id={c_id}, name={c_name})")
                async with conn.execute("SELECT id, key, question, input_type FROM steps WHERE category_id=?", (c_id,)) as cur2:
                    steps = await cur2.fetchall()
                    for s_id, s_key, s_q, s_type in steps:
                        print(f"  Step {s_key} (id={s_id}, type={s_type}) Q: {s_q}")
                        async with conn.execute("SELECT text, value FROM step_options WHERE step_id=?", (s_id,)) as cur3:
                            options = await cur3.fetchall()
                            if options:
                                print(f"    Options: {options}")

if __name__ == "__main__":
    asyncio.run(check())

