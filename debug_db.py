import sqlite3
conn = sqlite3.connect('data/bot.db')
cur = conn.cursor()
cur.execute('SELECT categories.key, steps.step_key, steps.input_type FROM steps JOIN categories ON steps.category_id = categories.id WHERE steps.step_key IN ("photo", "aspect")')
for row in cur.fetchall():
    print(row)
conn.close()

