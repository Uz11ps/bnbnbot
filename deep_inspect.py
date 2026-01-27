import sqlite3
import os

def deep_inspect(db_path):
    if not os.path.exists(db_path):
        print(f"File {db_path} not found")
        return
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    print(f"\n=== DEEP INSPECT: {db_path} ===")
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cur.fetchall()]
    
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"\nTable: {table} ({count} rows)")
        
        # Посмотрим колонки
        cur.execute(f"PRAGMA table_info({table})")
        cols = [f"{row[1]}" for row in cur.fetchall()]
        print(f"Columns: {', '.join(cols)}")
        
        if count > 0:
            cur.execute(f"SELECT * FROM {table} LIMIT 1")
            print(f"Sample data: {cur.fetchone()}")
            
    conn.close()

deep_inspect("staraya bd/REAL_OLD.db")
