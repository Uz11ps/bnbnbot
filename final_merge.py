import sqlite3
import os

def final_merge():
    # Целевая база (та самая из бэкапа с конструктором)
    target_db = "staraya bd/bot.db"
    # Источник пользователей
    source_db = "staraya bd/REAL_OLD.db"
    
    if not os.path.exists(target_db) or not os.path.exists(source_db):
        print("Ошибка: Базы не найдены.")
        return

    dst_conn = sqlite3.connect(target_db)
    dst_cur = dst_conn.cursor()
    
    src_conn = sqlite3.connect(source_db)
    src_cur = src_conn.cursor()
    
    print(f"Слияние пользователей из {source_db} в {target_db}...")

    # Получаем колонки из источника (REAL_OLD.db)
    src_cur.execute("PRAGMA table_info(users)")
    src_cols = [row[1] for row in src_cur.fetchall()]
    
    # Базовые поля, которые точно есть
    fields = ["id", "username", "first_name", "last_name", "balance"]
    
    # Формируем SELECT запрос
    query = f"SELECT {', '.join(fields)} FROM users"
    src_cur.execute(query)
    users = src_cur.fetchall()
    
    print(f"Найдено в источнике: {len(users)} пользователей.")

    for u in users:
        u_id, username, f_name, l_name, bal = u
        # Обновляем/вставляем в целевую базу
        dst_cur.execute("""
            INSERT INTO users (id, username, first_name, last_name, balance)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username),
                first_name = COALESCE(excluded.first_name, users.first_name),
                last_name = COALESCE(excluded.last_name, users.last_name),
                balance = MAX(users.balance, excluded.balance)
        """, (u_id, username, f_name, l_name, bal))
    
    dst_conn.commit()
    
    # Итоговая проверка
    dst_cur.execute("SELECT COUNT(*) FROM users")
    final_count = dst_cur.fetchone()[0]
    dst_cur.execute("SELECT COUNT(*) FROM categories")
    cat_count = dst_cur.fetchone()[0]
    
    print(f"Итого в целевой базе: {final_count} пользователей.")
    print(f"Проверка: Категорий конструктора сохранено: {cat_count}")
    
    dst_conn.close()
    src_conn.close()
    
    # Копируем результат в папку data, чтобы пользователю было удобно скачивать
    import shutil
    if not os.path.exists("data"):
        os.makedirs("data")
    shutil.copy2(target_db, "data/bot.db")
    print("\nФайл скопирован в data/bot.db")

if __name__ == "__main__":
    final_merge()
