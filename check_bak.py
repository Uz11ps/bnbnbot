import sqlite3
import os

db_path = "data/bot.db.bak"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        print(f"Users in {db_path}: {count}")
    except Exception as e:
        print(f"Error reading {db_path}: {e}")
    conn.close()
else:
    print(f"File not found: {db_path}")
