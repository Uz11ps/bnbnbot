import sqlite3
import os

def check_target(db_path):
    if not os.path.exists(db_path):
        print(f"File {db_path} not found")
        return
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    print(f"\n=== CHECKING TARGET BACKUP: {db_path} ===")
    
    tables = ['users', 'categories', 'steps', 'models', 'app_settings', 'prompts']
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"Table {table}: {count} rows")
        except sqlite3.OperationalError:
            print(f"Table {table}: Not found")
            
    conn.close()

check_target("staraya bd/bot.db")
