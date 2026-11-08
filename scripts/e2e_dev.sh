#!/usr/bin/env bash
# Page-level e2e against the Vite dev server (no shared build output), for parallel work.
# Starts the API (on the deterministic e2e demo DB, see scripts/e2e.sh) and Vite on the given
# ports, runs Playwright for the matching pages, then stops both servers.
# Usage: scripts/e2e_dev.sh API_PORT WEB_PORT "page training|page records" [playwright args]
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
export ROOT
# shellcheck source=scripts/pyenv.sh
. scripts/pyenv.sh

API_PORT="${1:?api port}"
WEB_PORT="${2:?web port}"
GREP="${3:?grep pattern, e.g. \"page training\"}"
shift 3
DB_URL="postgresql+psycopg://garminizer:garminizer-dev@127.0.0.1:55432/garminizer_e2e"

bash scripts/devdb.sh up >/dev/null
"$PY" scripts/e2e_db.py "$DB_URL" "${E2E_END:-2026-10-31}"

mkdir -p artifacts
DATABASE_URL="$DB_URL" APP_HOST=127.0.0.1 APP_PORT="$API_PORT" APP_PASSWORD="" \
  "$PY" -m garminizer.cli serve >"artifacts/e2e-api-$API_PORT.log" 2>&1 &
API=$!
(cd web && GARMINIZER_API="http://127.0.0.1:$API_PORT" pnpm exec vite --host 127.0.0.1 --port "$WEB_PORT" --strictPort \
  >"../artifacts/e2e-web-$WEB_PORT.log" 2>&1) &
WEB=$!
trap 'kill $API $WEB 2>/dev/null || true; pkill -f "vite --port $WEB_PORT" 2>/dev/null || true' EXIT
for _ in $(seq 1 120); do
  curl -sf "http://127.0.0.1:$API_PORT/api/health" >/dev/null &&
    curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null && break
  sleep 0.5
done

cd web
E2E_BASE_URL="http://127.0.0.1:$WEB_PORT" pnpm exec playwright test -g "$GREP" "$@"
