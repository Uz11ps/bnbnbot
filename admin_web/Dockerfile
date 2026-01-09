FROM python:3.11-slim

WORKDIR /app

COPY admin_web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем папку bot, чтобы работали импорты настроек
COPY bot /app/bot
COPY admin_web /app/admin_web
COPY data /app/data

# Устанавливаем PYTHONPATH, чтобы python видел папку bot
ENV PYTHONPATH=/app

CMD ["uvicorn", "admin_web.main:app", "--host", "0.0.0.0", "--port", "8000"]
