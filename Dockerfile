# syntax=docker/dockerfile:1.7
# Garminizer: one image for the web app (API + dashboards) and the background worker.

# ---- web: build the SPA ---------------------------------------------------------------
FROM node:24-slim AS web
WORKDIR /src/web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm run build

# ---- app: Python runtime + PostgreSQL 17 client (pg_dump/pg_restore for backups) -------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates postgresql-common curl \
 && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
 && apt-get install -y --no-install-recommends postgresql-client-17 \
 && apt-get purge -y curl && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY backend/ backend/
RUN pip install .
COPY --from=web /src/web/dist /app/web/dist

RUN useradd --create-home --uid 1000 garminizer && mkdir -p /data && chown garminizer /data
USER garminizer
ENV DATA_DIR=/data \
    WEB_DIST=/app/web/dist \
    LISTEN_HOST=0.0.0.0 \
    APP_PORT=8420
VOLUME ["/data"]
EXPOSE 8420
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8420/api/health', timeout=4)"
CMD ["garminizer", "serve"]
