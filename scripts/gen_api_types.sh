#!/usr/bin/env bash
# Regenerate web/src/api/schema.d.ts from the FastAPI OpenAPI schema (no database needed).
# Usage: scripts/gen_api_types.sh          # write the file
#        scripts/gen_api_types.sh --check  # fail if the committed file is out of date
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
export ROOT
# shellcheck source=scripts/pyenv.sh
. scripts/pyenv.sh

OUT="web/src/api/schema.d.ts"
TMP="web/node_modules/.tmp/apigen"
mkdir -p "$TMP"
"$PY" - "$TMP/openapi.json" <<'PY'
import json
import sys

from garminizer.api.app import create_app
from garminizer.config import Settings

app = create_app(Settings(_env_file=None), web_dist=None)
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as fh:
    json.dump(app.openapi(), fh, indent=2, sort_keys=True)
PY
(cd web && pnpm exec openapi-typescript "node_modules/.tmp/apigen/openapi.json" \
  -o "node_modules/.tmp/apigen/schema.d.ts" --alphabetize >/dev/null)
sed -i 's/\r$//' "$TMP/schema.d.ts"

if [ "${1:-}" = "--check" ]; then
  if ! cmp -s "$TMP/schema.d.ts" "$OUT"; then
    echo "gen_api_types: $OUT is out of date - run scripts/gen_api_types.sh" >&2
    exit 1
  fi
  echo "gen_api_types: up to date"
else
  cp "$TMP/schema.d.ts" "$OUT"
  echo "gen_api_types: wrote $OUT ($(wc -l <"$OUT") lines)"
fi
