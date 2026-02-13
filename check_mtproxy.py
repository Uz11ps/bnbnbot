import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('130.49.148.147', 22, 'root', 'ixm7e6yx6zthgbw0')

_, stdout, stderr = ssh.exec_command('cd /root/bnbai && docker ps -a --filter name=mtproxy')
print("=== MTProxy контейнеры ===")
print(stdout.read().decode(errors="replace"))
print(stderr.read().decode(errors="replace"))

_, stdout, _ = ssh.exec_command('cd /root/bnbai && docker compose ps mtproxy')
print("\n=== Docker Compose статус ===")
print(stdout.read().decode(errors="replace"))

_, stdout, _ = ssh.exec_command('cd /root/bnbai && docker compose logs --tail=20 mtproxy')
print("\n=== Последние логи MTProxy ===")
print(stdout.read().decode(errors="replace"))

ssh.close()
