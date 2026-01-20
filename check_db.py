import asyncio
from bot.db import Database

async def check():
    db = Database('data/bot.db')
    
    # Actually, let's look at all categories in the table
    import aiosqlite
    async with aiosqlite.connect('data/bot.db') as conn:
        async with conn.execute("SELECT id, key FROM categories") as cur:
            cats = await cur.fetchall()
            print(f"Total categories in table: {len(cats)}")
            for cid, ckey in cats:
                async with conn.execute("SELECT id, step_key FROM steps WHERE category_id=?", (cid,)) as scur:
                    steps = await scur.fetchall()
                    print(f"Category {ckey} (id={cid}): {len(steps)} steps")
                    for sid, skey in steps:
                        async with conn.execute("SELECT id, option_text FROM step_options WHERE step_id=?", (sid,)) as ocur:
                            opts = await ocur.fetchall()
                            print(f"  Step {skey} (id={sid}): {len(opts)} options")

if __name__ == "__main__":
    asyncio.run(check())
