"""
Скрипт деплоя bnbai на сервер.
Требования: pip install paramiko scp
"""
import os
import sys

try:
    import paramiko
    from scp import SCPClient
except ImportError:
    print("Установите: pip install paramiko scp")
    sys.exit(1)

SERVER = "130.49.148.147"
PORT = 22
USER = "root"
PASSWORD = "ixm7e6yx6zthgbw0"
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

    ssh.close()
    print("\nДеплой завершён. Админка: http://130.49.148.147:8000")


if __name__ == "__main__":
    deploy()
