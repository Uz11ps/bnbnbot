FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY bot ./bot
COPY scripts ./scripts
# Копируем изображение-гайд для выбора длины изделия (переименовываем для удобства)
COPY ["WhatsApp Image 2025-11-25 at 00.40.21.jpeg", "./garment_length_guide.jpeg"]
RUN mkdir -p /app/data

# Default envs
ENV DATABASE_URL=sqlite+aiosqlite:///./data/bot.db

# Run
CMD ["python", "-m", "bot.main"]
