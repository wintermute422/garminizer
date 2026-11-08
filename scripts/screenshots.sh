#!/usr/bin/env bash
# README screenshots from the deterministic DEMO database only.
#   1. refuses unless every athlete row in the e2e database is flagged is_demo
#   2. captures viewport screenshots (desktop, dark + light) into docs/screenshots/
#   3. writes docs/screenshots/MANIFEST.sha256 (pre-commit only accepts listed images)
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
export ROOT
# shellcheck source=scripts/pyenv.sh
. scripts/pyenv.sh

DB_URL="${E2E_DATABASE_URL:-postgresql+psycopg://garminizer:garminizer-dev@127.0.0.1:55432/garminizer_e2e}"
bash scripts/devdb.sh up >/dev/null
"$PY" scripts/e2e_db.py "$DB_URL" "${E2E_END:-2026-10-31}"
"$PY" - "$DB_URL" <<'PY'
import sys
from sqlalchemy import create_engine, text
engine = create_engine(sys.argv[1])
with engine.connect() as conn:
    rows = conn.execute(text("SELECT is_demo FROM garmin.athlete")).scalars().all()
if not rows or not all(rows):
    sys.exit("screenshots: refusing - the database is not a demo database")
print("screenshots: demo database confirmed")
PY

mkdir -p docs/screenshots
rm -f docs/screenshots/*.png
README_SHOTS=1 bash scripts/e2e.sh -g "readme " --project=desktop-dark --project=desktop-light

(cd docs/screenshots && sha256sum -- *.png > MANIFEST.sha256)
echo "screenshots: $(ls docs/screenshots/*.png | wc -l) images, manifest written"
