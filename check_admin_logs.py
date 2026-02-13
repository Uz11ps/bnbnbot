import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('130.49.148.147', 22, 'root', 'ixm7e6yx6zthgbw0')

_, stdout, _ = ssh.exec_command('cd /root/bnbai && docker compose logs --tail=50 admin_web | grep -i mtproxy')
print("=== Логи admin_web с упоминанием MTProxy ===")
print(stdout.read().decode(errors="replace"))

_, stdout, _ = ssh.exec_command('cd /root/bnbai && docker compose logs --tail=100 admin_web | tail -30')
print("\n=== Последние логи admin_web ===")
print(stdout.read().decode(errors="replace"))

ssh.close()
