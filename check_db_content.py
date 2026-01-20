import asyncio
import aiosqlite

async def check():
    db_path = "data/bot.db"
    async with aiosqlite.connect(db_path) as db:
        print("--- Categories ---")
        async with db.execute("SELECT id, key, name_ru FROM categories") as cur:
            async for row in cur:
                print(row)
        
        print("\n--- Steps for 'random' ---")
        async with db.execute("""
            SELECT s.id, s.step_key, s.question_text 
            FROM steps s 
            JOIN categories c ON s.category_id = c.id 
            WHERE c.key = 'random'
            ORDER BY s.order_index
        """) as cur:
            async for row in cur:
                print(row)
                step_id = row[0]
                print(f"  Options for step {step_id}:")
                async with db.execute("SELECT option_text, option_value FROM step_options WHERE step_id=?", (step_id,)) as opt_cur:
                    async for opt in opt_cur:
                        print(f"    {opt}")

if __name__ == "__main__":
    asyncio.run(check())

