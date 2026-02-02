
import asyncio
import aiosqlite
import os
from dotenv import load_dotenv

async def migrate_proxies():
    load_dotenv()
    db_path = os.path.join(os.getcwd(), 'bot.db')
    
    # Извлекаем прокси из GEMINI_HTTP_PROXY
    proxy_str = os.getenv("GEMINI_HTTP_PROXY", "")
    if not proxy_str:
        print("No proxies found in .env")
        return

    proxies = [p.strip() for p in proxy_str.split(",") if p.strip()]
    
    async with aiosqlite.connect(db_path) as db:
        # Проверяем, нет ли уже прокси в базе
        async with db.execute("SELECT COUNT(*) FROM proxies") as cur:
            count = (await cur.fetchone())[0]
            
        if count > 0:
            print(f"Database already has {count} proxies. Skipping migration.")
            return

        for p_url in proxies:
            await db.execute("INSERT INTO proxies (url, is_active, status) VALUES (?, 1, 'unknown')", (p_url,))
            print(f"Migrated: {p_url}")
            
        await db.commit()
        print(f"Successfully migrated {len(proxies)} proxies.")

if __name__ == "__main__":
    asyncio.run(migrate_proxies())
