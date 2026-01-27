import sqlite3
import os
import sys

def migrate():
    # Путь к текущей базе
    target_db = "data/bot.db"
    
    if not os.path.exists(target_db):
        # Пробуем найти в текущей папке если в data нет
        if os.path.exists("bot.db"):
            target_db = "bot.db"
        else:
            print(f"Ошибка: Целевая база {target_db} не найдена. Убедитесь, что вы в корне проекта.")
            return

    print(f"Целевая база: {target_db}")

    # Ищем все .db файлы по всему проекту, кроме папки data и самого целевого файла
    found_dbs = []
    for root, dirs, files in os.walk("."):
        if "data" in root: continue
        for file in files:
            if file.endswith(".db") and file != "bot.db":
                found_dbs.append(os.path.join(root, file))
            # Специально проверяем файл bot.db в других папках
            elif file == "bot.db" and os.path.abspath(os.path.join(root, file)) != os.path.abspath(target_db):
                found_dbs.append(os.path.join(root, file))

    if not found_dbs:
        print("В проекте не найдено других .db файлов для миграции (кроме основной базы).")
        print("Загрузите старую базу в папку 'staraya bd' и запустите скрипт снова.")
        return

    dst_conn = sqlite3.connect(target_db)
    dst_cur = dst_conn.cursor()

    total_migrated = 0
    for src_path in found_dbs:
        print(f"\n--- Обработка {src_path} ---")
        
        try:
            src_conn = sqlite3.connect(src_path)
            src_cur = src_conn.cursor()
            
            # Проверяем наличие таблицы users
            src_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not src_cur.fetchone():
                print(f"  В файле нет таблицы 'users'. Пропуск.")
                src_conn.close()
                continue
            
            # Получаем колонки старой базы
            src_cur.execute("PRAGMA table_info(users)")
            cols = [row[1] for row in src_cur.fetchall()]
            
            # Формируем запрос в зависимости от наличия колонок
            select_parts = ["id"]
            if "username" in cols: select_parts.append("username")
            else: select_parts.append("NULL")
            
            if "first_name" in cols: select_parts.append("first_name")
            else: select_parts.append("NULL")
            
            if "last_name" in cols: select_parts.append("last_name")
            else: select_parts.append("NULL")
            
            if "balance" in cols: select_parts.append("balance")
            else: select_parts.append("0")

            query = f"SELECT {', '.join(select_parts)} FROM users"
            src_cur.execute(query)
            users = src_cur.fetchall()
            print(f"  Найдено {len(users)} пользователей")
            
            for u in users:
                u_id, username, f_name, l_name, bal = u
                # Добавляем или обновляем
                dst_cur.execute("""
                    INSERT INTO users (id, username, first_name, last_name, balance)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        username = COALESCE(excluded.username, users.username),
                        first_name = COALESCE(excluded.first_name, users.first_name),
                        last_name = COALESCE(excluded.last_name, users.last_name),
                        balance = MAX(users.balance, excluded.balance)
                """, (u_id, username, f_name, l_name, bal))
                total_migrated += 1
            
            src_conn.close()
        except Exception as e:
            print(f"  Ошибка: {e}")

    dst_conn.commit()
    dst_conn.close()
    
    # Проверка итогового количества
    conn = sqlite3.connect(target_db)
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    
    print(f"\n========================================")
    print(f"Готово! Всего импортировано записей: {total_migrated}")
    print(f"Итого уникальных пользователей в базе: {count}")
    print(f"========================================\n")

if __name__ == "__main__":
    migrate()
