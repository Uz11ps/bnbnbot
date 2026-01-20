import sqlite3
conn = sqlite3.connect('data/bot.db')
cur = conn.cursor()
cur.execute('SELECT s.id, s.step_key, s.question_text, c.key FROM steps s JOIN categories c ON s.category_id = c.id WHERE s.step_key IN ("photo", "aspect")')
rows = cur.fetchall()
for row in rows:
    print(row)
conn.close()

