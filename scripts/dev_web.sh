#!/usr/bin/env bash
# Vite dev server on 127.0.0.1:5180 proxying /api to the development API (scripts/dev_api.sh).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT/web"
export GARMINIZER_API="http://127.0.0.1:8425"
exec pnpm exec vite --host 127.0.0.1 --port 5180 --strictPort
