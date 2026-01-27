import sqlite3
import os

db_path = "data/bot.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    print(f"Users in {db_path}: {count}")
    
    cur.execute("SELECT id, username FROM users LIMIT 5")
    print(f"First 5 users: {cur.fetchall()}")
    conn.close()
else:
    print(f"DB not found: {db_path}")

old_db = "bot.db"
if os.path.exists(old_db):
    conn = sqlite3.connect(old_db)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    print(f"Users in {old_db}: {count}")
    conn.close()
else:
    print(f"Old DB not found: {old_db}")
