"""
Скрипт деплоя bnbai на сервер.
Требования: pip install paramiko scp
Переменные: DEPLOY_HOST, DEPLOY_USER, DEPLOY_PASSWORD (или задать ниже)
"""
import os
import sys

try:
    import paramiko
    from scp import SCPClient
except ImportError:
    print("Установите: pip install paramiko scp")
    sys.exit(1)

SERVER = os.getenv("DEPLOY_HOST", "130.49.148.147")
PORT = int(os.getenv("DEPLOY_PORT", "22"))
USER = os.getenv("DEPLOY_USER", "root")
PASSWORD = os.getenv("DEPLOY_PASSWORD", "ixm7e6yx6zthgbw0")
REMOTE_DIR = "/root/bnbai"
REPO_URL = "https://github.com/Uz11ps/bnbnbot.git"


def deploy():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Подключение к {SERVER}...")
    ssh.connect(SERVER, PORT, USER, PASSWORD)

    def run(cmd: str, check: bool = True) -> tuple[int, str, str]:
        _, stdout, stderr = ssh.exec_command(cmd)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        if check and code != 0:
            print(f"Ошибка [{code}]: {cmd}\n{err or out}")
        return code, out, err

    # Проверка Docker
    code, _, _ = run("docker --version", check=False)
    if code != 0:
        print("Docker не установлен. Установите Docker на сервере.")
        ssh.close()
        sys.exit(1)

    # Создание директории и git clone/pull
    run("mkdir -p " + REMOTE_DIR)
    code, _, _ = run(f"test -d {REMOTE_DIR}/.git", check=False)
    if code != 0:
        print("Клонирование репозитория...")
        run(f"cd /root && rm -rf bnbai && git clone {REPO_URL} bnbai")
    else:
        print("Обновление репозитория...")
        run(f"cd {REMOTE_DIR} && git pull origin main")

    # Загрузка .env
    base = os.path.dirname(os.path.abspath(__file__))
    local_env = os.path.join(base, ".env")
    local_env_bak = os.path.join(base, ".env.bak")
    if os.path.isfile(local_env):
        print("Загрузка .env...")
        with SCPClient(ssh.get_transport()) as scp:
            scp.put(local_env, f"{REMOTE_DIR}/.env")
    elif os.path.isfile(local_env_bak):
        code, _, _ = run(f"test -f {REMOTE_DIR}/.env", check=False)
        if code != 0:
            print("Загрузка .env.bak как .env...")
            with SCPClient(ssh.get_transport()) as scp:
                scp.put(local_env_bak, f"{REMOTE_DIR}/.env")

    # Директории для volumes
    run(f"mkdir -p {REMOTE_DIR}/data {REMOTE_DIR}/scripts")
    run(f"mkdir -p \"{REMOTE_DIR}/staraya bd\"")

    # Сборка и запуск
    print("Сборка образов...")
    run(f"cd {REMOTE_DIR} && docker compose build --no-cache")
    print("Запуск контейнеров...")
    run(f"cd {REMOTE_DIR} && docker compose up -d")

    print("Проверка статуса...")
    run(f"cd {REMOTE_DIR} && docker compose ps")
    
    # Перезапускаем admin_web для надежности
    print("Перезапуск admin_web...")
    run(f"cd {REMOTE_DIR} && docker compose restart admin_web")
    
    # Ждем запуска admin_web
    print("Ожидание запуска admin_web...")
    import time
    time.sleep(10)
    
    # Проверяем логи на ошибки
    print("Проверка логов admin_web...")
    code, out, err = run(f"cd {REMOTE_DIR} && docker compose logs --tail=20 admin_web", check=False)
    if "error" in out.lower() or "exception" in out.lower():
        print("WARNING: Обнаружены ошибки в логах admin_web")
        print(out[-500:])  # Последние 500 символов
    
    # Проверяем, что admin_web отвечает
    code, out, err = run(f"curl -f -s http://localhost:8000/health 2>&1 || echo 'FAIL'", check=False)
    if "FAIL" in out or code != 0:
        print("WARNING: admin_web не отвечает на /health")
        print("Проверьте логи: docker compose logs admin_web")
        print("Проверьте статус: docker compose ps")
    else:
        print("OK: admin_web работает")

    # Настройка nginx для g-box.space
    nginx_config = """server {
    listen 80;
    server_name g-box.space www.g-box.space;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
"""
    print("Настройка nginx для g-box.space...")
    code, _, _ = run("which nginx", check=False)
    if code == 0:
        tmp_path = "/tmp/g-box.space.conf"
        sftp = ssh.open_sftp()
        try:
            with sftp.open(tmp_path, "w") as f:
                f.write(nginx_config)
        finally:
            sftp.close()
        run(f"sudo cp {tmp_path} /etc/nginx/conf.d/g-box.space.conf && rm -f {tmp_path}")
        run("sudo nginx -t")
        run("sudo systemctl reload nginx 2>/dev/null || sudo service nginx reload")
        print("Nginx настроен.")
    else:
        print("Nginx не найден. Настройте прокси вручную.")

    ssh.close()
    print("\nДеплой завершён.")
    print("Сайт: https://g-box.space")
    print("Админка: https://g-box.space/")


if __name__ == "__main__":
    deploy()
