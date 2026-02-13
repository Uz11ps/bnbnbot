FROM python:3.11-slim

WORKDIR /app

# Устанавливаем Docker CLI для управления контейнерами
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

COPY admin_web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем папку bot, чтобы работали импорты настроек
COPY bot /app/bot
COPY admin_web /app/admin_web
# Папку data НЕ копируем, она должна подключаться как volume

# Устанавливаем PYTHONPATH, чтобы python видел папку bot
ENV PYTHONPATH=/app

CMD ["uvicorn", "admin_web.main:app", "--host", "0.0.0.0", "--port", "8000"]
