# Production image for the Breakpoint Web API.
#
# Deliberately does NOT install the analysis engine's heavy dependencies
# (numpy/opencv/librosa/etc). This image only serves the FastAPI SaaS
# backend (auth, projects, uploads, quota, admin) — analysis/export
# execution happens in separate worker processes that are not part of
# Layer 1.
FROM python:3.12.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps needed to build psycopg2-binary/argon2-cffi wheels are not
# required since both ship manylinux wheels for slim's glibc; libpq is
# still needed at runtime for psycopg2-binary's bundled libpq to link.
RUN groupadd --system app && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

# Install dependencies before copying source so dependency layers cache
# independently of application code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY docker-entrypoint.sh ./docker-entrypoint.sh
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
