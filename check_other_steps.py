import sqlite3
import os

db_path = "data/bot.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Check random category
    cur.execute("SELECT id, step_key, input_type FROM steps WHERE category_id = (SELECT id FROM categories WHERE key = 'random') ORDER BY order_index")
    print("Random steps:", cur.fetchall())
    
    # Check infographic_clothing
    cur.execute("SELECT id, step_key, input_type FROM steps WHERE category_id = (SELECT id FROM categories WHERE key = 'infographic_clothing') ORDER BY order_index")
    print("Infographic Clothing steps:", cur.fetchall())
    
    conn.close()

