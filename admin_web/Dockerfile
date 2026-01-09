FROM python:3.11-slim

WORKDIR /app

COPY admin_web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY admin_web /app/admin_web
COPY data /app/data

CMD ["uvicorn", "admin_web.main:app", "--host", "0.0.0.0", "--port", "8000"]

