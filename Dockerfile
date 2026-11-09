# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build all Python packages as wheels.
# mysqlclient needs a C compiler and MySQL headers, which we do NOT want in
# the final image (smaller and fewer tools for an attacker).
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: the small runtime image.
# ---------------------------------------------------------------------------
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Only the MySQL client library (no compiler), and a normal user to run the app.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmariadb3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY --chown=app:app . .

# Collect static files into the image. Dummy values: settings need them to load,
# but collectstatic never connects to the database. Real values come at runtime.
RUN DJANGO_SECRET_KEY=build-only DB_NAME=build DB_USER=build DB_PASSWORD=build \
    python manage.py collectstatic --noinput \
    && mkdir -p /app/media \
    && chown -R app:app /app/media /app/staticfiles

USER app
EXPOSE 8000

# Gunicorn: a production web server (runserver is for development only).
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]