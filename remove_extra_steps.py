import sqlite3
import os

db_path = "data/bot.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Находим ID шагов photo и aspect
    cur.execute("SELECT id FROM steps WHERE step_key IN ('photo', 'aspect')")
    step_ids = [row[0] for row in cur.fetchall()]
    
    if step_ids:
        print(f"Removing step options for steps: {step_ids}")
        cur.execute(f"DELETE FROM step_options WHERE step_id IN ({','.join(map(str, step_ids))})")
        
        print(f"Removing steps: {step_ids}")
        cur.execute(f"DELETE FROM steps WHERE id IN ({','.join(map(str, step_ids))})")
        
        conn.commit()
        print("Done.")
    else:
        print("No photo/aspect steps found.")
    
    conn.close()
else:
    print("DB not found")

