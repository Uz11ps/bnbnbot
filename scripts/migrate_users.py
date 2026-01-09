import argparse
import os
import sqlite3
from typing import List, Tuple


def get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate users and balances from old SQLite DB to bot.db")
    parser.add_argument("--from-db", required=True, help="Path to old SQLite DB file")
    parser.add_argument("--from-table", default="users", help="Source table name (default: users)")
    parser.add_argument("--id-col", default="id", help="Source user id column (default: id)")
    parser.add_argument("--balance-col", default="balance", help="Source balance column (default: balance)")
    parser.add_argument("--username-col", default="username", help="Source username column (optional)")
    parser.add_argument("--first-name-col", default="first_name", help="Source first_name column (optional)")
    parser.add_argument("--last-name-col", default="last_name", help="Source last_name column (optional)")
    parser.add_argument("--full-name-col", default=None, help="Source full_name column (split to first/last, optional)")
    parser.add_argument("--created-at-col", default=None, help="Source created_at column (optional)")
    parser.add_argument("--target-db", default="bot.db", help="Target DB path (default: bot.db in project root)")
    args = parser.parse_args()

    if not os.path.exists(args.from_db):
        raise SystemExit(f"Source DB not found: {args.from_db}")
    if not os.path.exists(args.target_db):
        raise SystemExit(f"Target DB not found: {args.target_db}. Run the bot once to create it.")

    src = sqlite3.connect(args.from_db)
    dst = sqlite3.connect(args.target_db)

    try:
        src_cols = set(get_columns(src, args.from_table))

        required = {args.id_col, args.balance_col}
        if not required.issubset(src_cols):
            missing = required - src_cols
            raise SystemExit(f"Source table {args.from_table} missing required columns: {', '.join(missing)}")

        sel_cols: List[Tuple[str, str]] = [(args.id_col, "id"), (args.balance_col, "balance")]
        if args.username_col in src_cols:
            sel_cols.append((args.username_col, "username"))
        if args.first_name_col in src_cols and not args.full_name_col:
            sel_cols.append((args.first_name_col, "first_name"))
        if args.last_name_col in src_cols and not args.full_name_col:
            sel_cols.append((args.last_name_col, "last_name"))
        if args.full_name_col and args.full_name_col in src_cols:
            sel_cols.append((args.full_name_col, "full_name"))
        if args.created_at_col and args.created_at_col in src_cols:
            sel_cols.append((args.created_at_col, "created_at"))

        src_select = ", ".join([f"{src_name} AS {alias}" for src_name, alias in sel_cols])
        rows = src.execute(f"SELECT {src_select} FROM {args.from_table}").fetchall()

        migrated = 0
        updated = 0
        for row in rows:
            row_dict = {alias: row[idx] for idx, (_, alias) in enumerate(sel_cols)}
            user_id = int(row_dict["id"])
            balance = int(row_dict["balance"] or 0)
            username = row_dict.get("username")
            first_name = row_dict.get("first_name")
            last_name = row_dict.get("last_name")
            created_at = row_dict.get("created_at")
            # Разбить full_name если задан
            if row_dict.get("full_name") and (not first_name and not last_name):
                fn = str(row_dict["full_name"]).strip()
                if " " in fn:
                    first_name, last_name = fn.split(" ", 1)
                else:
                    first_name, last_name = fn, None

            # Upsert base fields
            dst.execute(
                """
                INSERT INTO users (id, username, first_name, last_name, balance)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  username=COALESCE(excluded.username, users.username),
                  first_name=COALESCE(excluded.first_name, users.first_name),
                  last_name=COALESCE(excluded.last_name, users.last_name)
                """,
                (user_id, username, first_name, last_name, balance),
            )

            # Ensure balance is set to source value (not additive)
            cur = dst.execute("SELECT balance FROM users WHERE id=?", (user_id,))
            cur_bal = int(cur.fetchone()[0] or 0)
            if cur_bal != balance:
                dst.execute("UPDATE users SET balance=? WHERE id=?", (balance, user_id))
                updated += 1
            # Установить created_at при наличии
            if created_at is not None:
                try:
                    dst.execute("UPDATE users SET created_at=? WHERE id=?", (created_at, user_id))
                except Exception:
                    pass
            migrated += 1

        dst.commit()
        print(f"Migrated users: {migrated}; balances set: {updated}")
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()


