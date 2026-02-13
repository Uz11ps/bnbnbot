import paramiko
import sqlite3
import io

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('130.49.148.147', 22, 'root', 'ixm7e6yx6zthgbw0')

# Скачиваем БД
sftp = ssh.open_sftp()
sftp.get('/root/bnbai/data/bot.db', 'bot.db')
sftp.close()

# Проверяем настройки MTProxy
conn = sqlite3.connect('bot.db')
cursor = conn.cursor()

cursor.execute("SELECT key, value FROM app_settings WHERE key LIKE 'mtproxy%'")
rows = cursor.fetchall()
print("=== Настройки MTProxy в БД ===")
for row in rows:
    print(f"{row[0]}: {row[1]}")

conn.close()

ssh.close()
