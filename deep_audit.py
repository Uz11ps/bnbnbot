import sqlite3
import os

def audit_all():
    for root, dirs, files in os.walk("."):
        for file in files:
            full_path = os.path.join(root, file)
            try:
                # Check if it's a sqlite db
                with open(full_path, "rb") as f:
                    header = f.read(16)
                    if not header.startswith(b"SQLite format 3"):
                        continue
                
                print(f"\n--- Database: {full_path} ---")
                conn = sqlite3.connect(full_path)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [t[0] for t in cur.fetchall()]
                for t in tables:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {t}")
                        count = cur.fetchone()[0]
                        print(f"  Table '{t}': {count} rows")
                        if t == 'users' and count > 114:
                            print(f"  !!! FOUND POSSIBLE TARGET: {count} users in {full_path}")
                    except:
                        pass
                conn.close()
            except:
                pass

if __name__ == "__main__":
    audit_all()
