FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000

WORKDIR /app

# System dependencies: Tesseract OCR with English and Bengali language packs, and Poppler
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-ben \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir psycopg2-binary asyncpg

COPY . .

# Ensure storage and data directories exist
RUN mkdir -p /app/storage/originals /app/storage/evidence /app/data

EXPOSE 8000

CMD sh -c "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
