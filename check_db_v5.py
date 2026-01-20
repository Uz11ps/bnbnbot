
import asyncio
import aiosqlite
import sys

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

async def check():
    async with aiosqlite.connect("data/bot.db") as conn:
        print("--- CATEGORIES ---")
        async with conn.execute("SELECT id, key, name_ru FROM categories") as cur:
            categories = await cur.fetchall()
            for c_id, c_key, c_name in categories:
                print(f"Category {c_key} (id={c_id})")
                async with conn.execute("SELECT id, step_key, question_text, input_type FROM steps WHERE category_id=?", (c_id,)) as cur2:
                    steps = await cur2.fetchall()
                    for s_id, s_key, s_q, s_type in steps:
                        print(f"  Step {s_key} (id={s_id}) Q: {repr(s_q)}")
                        async with conn.execute("SELECT option_text, option_value FROM step_options WHERE step_id=?", (s_id,)) as cur3:
                            options = await cur3.fetchall()
                            if options:
                                print(f"    Options: {len(options)}")
                                for opt_text, opt_val in options:
                                    print(f"      - Text: {repr(opt_text)}, Value: {repr(opt_val)}")

if __name__ == "__main__":
    asyncio.run(check())

