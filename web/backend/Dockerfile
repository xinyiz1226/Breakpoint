# Shared production image for the API, Celery worker, and Celery Beat.
FROM python:3.12.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps needed to build psycopg2-binary/argon2-cffi wheels are not
# required since both ship manylinux wheels for slim's glibc; libpq is
# still needed at runtime for psycopg2-binary's bundled libpq to link.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg libgl1 libglib2.0-0 libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

# Install dependencies before copying source so dependency layers cache
# independently of application code changes.
COPY requirements.txt ./requirements-engine.txt
COPY web/backend/requirements.txt ./requirements-backend.txt
RUN pip install --no-cache-dir -r requirements-engine.txt -r requirements-backend.txt

COPY engine ./engine
COPY TennisHighlightAnalysis.py ./TennisHighlightAnalysis.py
COPY web/backend/app ./app
COPY web/backend/alembic.ini ./alembic.ini
COPY web/backend/alembic ./alembic
COPY web/backend/docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

RUN chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status == 200 else sys.exit(1)"

ENTRYPOINT ["./docker-entrypoint.sh"]

# gunicorn manages a small pool of uvicorn workers for production; a single
# worker is fine here since the API is I/O-bound and any real scale-out
# happens via horizontal replicas, not per-process worker fan-out.
CMD ["gunicorn", "app.main:app", "--worker-class", "uvicorn.workers.UvicornWorker", "--workers", "2", "--bind", "0.0.0.0:8000", "--access-logfile", "-"]
