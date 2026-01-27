import sqlite3
import os

db1 = r"data/bot.db"
db2 = r"staraya bd/bot.db"

def get_ids(path):
    if not os.path.exists(path): return set()
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users")
    ids = {row[0] for row in cur.fetchall()}
    conn.close()
    return ids

ids1 = get_ids(db1)
ids2 = get_ids(db2)

print(f"Current DB users: {len(ids1)}")
print(f"Old DB users: {len(ids2)}")
print(f"Combined unique users: {len(ids1 | ids2)}")
print(f"New users to add: {len(ids2 - ids1)}")
