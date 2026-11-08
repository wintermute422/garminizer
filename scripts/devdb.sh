#!/usr/bin/env bash
# Dev/test PostgreSQL (compose project `garminizer-dev`, 127.0.0.1:55432). Never touches the
# real `garminizer` stack.
# Usage: scripts/devdb.sh up | down | status | reset | psql
#   reset  drops and recreates the `garminizer` database inside the dev container only.
# Set GARMINIZER_DB_EXTERNAL=1 (CI service container) to make `up` a no-op.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
DC=(docker compose -f compose.dev.yml -p garminizer-dev)
cmd="${1:-up}"

case "$cmd" in
  up)
    if [ "${GARMINIZER_DB_EXTERNAL:-0}" = "1" ]; then echo "devdb: external database, skipping"; exit 0; fi
    "${DC[@]}" up -d --wait >/dev/null
    echo "devdb: up (127.0.0.1:55432)"
    ;;
  down) "${DC[@]}" stop ;;
  status) "${DC[@]}" ps ;;
  reset)
    "${DC[@]}" exec -T db psql -U garminizer -d postgres -v ON_ERROR_STOP=1 \
      -c "DROP DATABASE IF EXISTS garminizer WITH (FORCE)" -c "CREATE DATABASE garminizer OWNER garminizer"
    echo "devdb: database garminizer recreated (dev container only)"
    ;;
  psql) "${DC[@]}" exec db psql -U garminizer -d garminizer ;;
  *) echo "usage: $0 up|down|status|reset|psql" >&2; exit 64 ;;
esac
