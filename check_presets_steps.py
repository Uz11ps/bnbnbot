import sqlite3
conn = sqlite3.connect('data/bot.db')
cur = conn.cursor()
cur.execute('SELECT id, key FROM categories WHERE key="presets"')
cat = cur.fetchone()
if cat:
    print(f"Category: {cat}")
    cur.execute('SELECT step_key, input_type FROM steps WHERE category_id=?', (cat[0],))
    for step in cur.fetchall():
        print(f"  Step: {step}")
else:
    print("Category presets not found")
conn.close()

