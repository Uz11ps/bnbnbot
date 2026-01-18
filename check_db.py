import sqlite3
import os

db_path = 'data/bot.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print("Tables:", cur.fetchall())
    
    cur.execute("SELECT DISTINCT category FROM models")
    print("Categories:", cur.fetchall())
    
    cur.execute("SELECT COUNT(*) FROM models")
    print("Total models:", cur.fetchone()[0])
    
    conn.close()
else:
    print(f"File {db_path} not found")


