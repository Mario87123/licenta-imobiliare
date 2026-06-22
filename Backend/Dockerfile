FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DATABASE_PATH=/data/app.db
ENV ML_MODEL_DIR=/data/ml_models

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY App ./App

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "App.main:app", "--host", "0.0.0.0", "--port", "8000"]
