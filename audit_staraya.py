import sqlite3
import os

db_path = r"staraya bd/bot.db"
if not os.path.exists(db_path):
    print("File not found")
    exit()

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cur.fetchall()]
print(f"Tables: {tables}")

for table in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"Table '{table}' has {count} rows")
        
        # Check first 5 rows of users to see IDs
        if table == 'users':
            cur.execute("SELECT id, username FROM users LIMIT 10")
            print(f"Users sample: {cur.fetchall()}")
    except Exception as e:
        print(f"Error reading {table}: {e}")

conn.close()
