#!/usr/bin/env bash
# Sourced by other scripts: sets $PY to the project venv's python, else the first PATH
# interpreter that actually runs (skips the Windows Store "python3" stub, which exits 49).
ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"
PY=""
for cand in "$ROOT/.venv/bin/python" "$ROOT/.venv/Scripts/python.exe"; do
  if [ -x "$cand" ]; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys' >/dev/null 2>&1; then
      PY="$cand"; break
    fi
  done
fi
[ -n "$PY" ] || { echo "pyenv.sh: no working python found" >&2; exit 2; }
export PY
