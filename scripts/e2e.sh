#!/usr/bin/env bash
# End-to-end tests (A9/A10) against the production build and a deterministic demo database.
#   - database `garminizer_e2e` in the dev Postgres, seeded once (730 days ending E2E_END, seed 42)
#   - FastAPI serves the built SPA on 127.0.0.1:8421
#   - Playwright: every page × desktop/mobile × dark/light, screenshots to artifacts/screenshots
# Usage: scripts/e2e.sh [--reseed] [playwright args...]
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
export ROOT
# shellcheck source=scripts/pyenv.sh
. scripts/pyenv.sh

E2E_END="${E2E_END:-2026-10-31}"
PORT="${E2E_PORT:-8421}"
DB_URL="postgresql+psycopg://garminizer:garminizer-dev@127.0.0.1:55432/garminizer_e2e"
RESEED=0
if [ "${1:-}" = "--reseed" ]; then RESEED=1; shift; fi

bash scripts/devdb.sh up >/dev/null
exists="$(docker compose -f compose.dev.yml -p garminizer-dev exec -T db \
  psql -U garminizer -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='garminizer_e2e'" || true)"
if [ "$exists" != "1" ] || [ "$RESEED" = "1" ]; then
  echo "e2e: seeding demo database (730 days ending $E2E_END)"
  docker compose -f compose.dev.yml -p garminizer-dev exec -T db psql -U garminizer -d postgres -q \
    -c "DROP DATABASE IF EXISTS garminizer_e2e WITH (FORCE)" -c "CREATE DATABASE garminizer_e2e"
  DATABASE_URL="$DB_URL" "$PY" -m garminizer.cli demo seed --days 730 --seed 42 --end "$E2E_END" | head -1
fi

(cd web && pnpm run -s build >/dev/null)

LOG="artifacts/e2e-server.log"
mkdir -p artifacts
DATABASE_URL="$DB_URL" APP_HOST=127.0.0.1 APP_PORT="$PORT" APP_PASSWORD="" \
  "$PY" -m garminizer.cli serve >"$LOG" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null || { cat "$LOG"; echo "e2e: server did not start" >&2; exit 1; }

cd web
E2E_BASE_URL="http://127.0.0.1:$PORT" pnpm exec playwright test "$@"
