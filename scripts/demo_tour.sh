#!/usr/bin/env bash
# Demo tour video for announcements, recorded from the deterministic DEMO database only.
#   1. refuses unless every athlete row in the e2e database is flagged is_demo
#   2. records web/e2e/tour.spec.ts (desktop, dark, 1280x720, about one minute)
#   3. writes artifacts/demo-tour.webm (git-ignored), plus demo-tour.mp4 when ffmpeg is installed
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
    sys.exit("demo_tour: refusing - the database is not a demo database")
print("demo_tour: demo database confirmed")
PY

rm -rf web/test-results-tour
DEMO_TOUR=1 bash scripts/e2e.sh -g "demo tour" --project=desktop-dark --output=test-results-tour

video="$(find web/test-results-tour -name '*.webm' | head -n1)"
[ -n "$video" ] || { echo "demo_tour: no recording found" >&2; exit 1; }
mkdir -p artifacts
cp "$video" artifacts/demo-tour.webm
echo "demo_tour: artifacts/demo-tour.webm"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -y -loglevel error -i artifacts/demo-tour.webm \
    -c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart -an artifacts/demo-tour.mp4
  echo "demo_tour: artifacts/demo-tour.mp4"
fi
