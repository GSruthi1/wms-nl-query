# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# libpq5 is the runtime shared lib psycopg2-binary needs; unlike LDIP this
# project has no OCR/PDF dependencies (no poppler/tesseract).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy just the requirements file first so Docker's layer cache is reused on
# every rebuild that only changes application code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts
COPY benchmark ./benchmark
COPY ui ./ui
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run as a non-root user — no reason for a process that only binds a port
# and talks to Postgres to run as root.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
# $PORT falls back to 8000 locally; Railway injects its own dynamic PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
