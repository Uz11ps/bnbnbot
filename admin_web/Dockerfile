FROM python:3.11-slim

WORKDIR /app

# Устанавливаем Docker CLI для управления контейнерами
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-24.0.7.tgz | tar -xzC /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && chmod +x /usr/local/bin/docker \
    && rm -rf /tmp/docker \
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
