#!/usr/bin/env bash
# Development API on 127.0.0.1:8425 against the dev/demo database (never the real one in .env).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
export ROOT
# shellcheck source=scripts/pyenv.sh
. scripts/pyenv.sh
export DATABASE_URL="postgresql+psycopg://garminizer:garminizer-dev@127.0.0.1:55432/garminizer"
export APP_HOST=127.0.0.1 APP_PORT=8425 APP_PASSWORD=""
bash scripts/devdb.sh up >/dev/null
exec "$PY" -m garminizer.cli serve "$@"
