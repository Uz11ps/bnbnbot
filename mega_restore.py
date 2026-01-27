import sqlite3
import os

def mega_restore():
    target_db = "data/bot.db"
    source_db = "staraya bd/REAL_OLD.db"
    
    if not os.path.exists(target_db) or not os.path.exists(source_db):
        print("Ошибка: Файлы баз не найдены.")
        return

    dst_conn = sqlite3.connect(target_db)
    dst_cur = dst_conn.cursor()
    
    src_conn = sqlite3.connect(source_db)
    src_cur = src_conn.cursor()
    
    print("--- Начинаю мега-восстановление ---")

    # 1. Восстанавливаем настройки и ПЕРЕВОДЫ (app_settings)
    print("Восстанавливаю настройки и переводы...")
    src_cur.execute("SELECT key, value FROM app_settings")
    settings = src_cur.fetchall()
    for k, v in settings:
        dst_cur.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    print(f"  Перенесено {len(settings)} настроек.")

    # 2. Восстанавливаем Промты (prompts)
    print("Восстанавливаю промты...")
    # Очистим текущие промты, чтобы не было дублей
    dst_cur.execute("DELETE FROM prompts")
    src_cur.execute("SELECT id, title, text FROM prompts")
    prompts = src_cur.fetchall()
    for p in prompts:
        dst_cur.execute("INSERT INTO prompts (id, title, text) VALUES (?, ?, ?)", p)
    print(f"  Перенесено {len(prompts)} промтов.")

    # 3. Восстанавливаем Модели (models)
    print("Восстанавливаю модели...")
    dst_cur.execute("DELETE FROM models")
    src_cur.execute("SELECT id, category, cloth, name, prompt_id, position, is_active, photo_file_id FROM models")
    models = src_cur.fetchall()
    for m in models:
        dst_cur.execute("INSERT INTO models (id, category, cloth, name, prompt_id, position, is_active, photo_file_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", m)
    print(f"  Перенесено {len(models)} моделей.")

    # 4. Восстанавливаем Историю (transactions -> transactions)
    # В новой базе может не быть таблицы transactions, создадим если надо
    dst_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
    if not dst_cur.fetchone():
        dst_cur.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, user_id INTEGER, amount INTEGER, type TEXT, reason TEXT, created_at TIMESTAMP)")
    
    print("Восстанавливаю историю транзакций...")
    src_cur.execute("SELECT id, user_id, amount, type, reason, created_at FROM transactions")
    txs = src_cur.fetchall()
    for tx in txs:
        dst_cur.execute("INSERT OR IGNORE INTO transactions (id, user_id, amount, type, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)", tx)
    print(f"  Перенесено {len(txs)} транзакций.")

    dst_conn.commit()
    dst_conn.close()
    src_conn.close()
    print("\n--- Восстановление завершено! Все данные в data/bot.db ---")

if __name__ == "__main__":
    mega_restore()
