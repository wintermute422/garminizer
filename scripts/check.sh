#!/usr/bin/env bash
# The single local gate: lint, format, types, tests, web build, secret scan.
# Exit code is non-zero if any stage fails. Stages for parts that do not exist yet
# print SKIP explicitly (never silently).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
export ROOT
# shellcheck source=scripts/pyenv.sh
. scripts/pyenv.sh

stage() { printf '\n== %s\n' "$1"; }
skip() { printf '\n== %s: SKIP (%s)\n' "$1" "$2"; }

stage "ruff check"
"$PY" -m ruff check backend scripts
stage "ruff format --check"
"$PY" -m ruff format --check backend scripts
stage "mypy --strict"
"$PY" -m mypy
stage "claude hook selftest"
"$PY" scripts/claude_hook.py selftest

if [ -f compose.dev.yml ]; then
  stage "dev database"
  bash scripts/devdb.sh up
fi
stage "pytest"
"$PY" -m pytest

if [ -f web/package.json ]; then
  stage "web: install"
  (cd web && pnpm install --frozen-lockfile --silent)
  stage "web: eslint"
  (cd web && pnpm run -s lint)
  stage "web: prettier --check"
  (cd web && pnpm run -s format:check)
  stage "web: tsc"
  (cd web && pnpm run -s typecheck)
  stage "web: vitest"
  (cd web && pnpm run -s test)
  stage "web: build"
  (cd web && pnpm run -s build)
else
  skip "web" "no web/package.json yet"
fi

if [ -f scripts/gen_api_types.sh ]; then
  stage "API types up to date"
  bash scripts/gen_api_types.sh --check
else
  skip "API types" "no scripts/gen_api_types.sh yet"
fi

stage "UTF-8 / LF"
"$PY" scripts/check_utf8.py
stage "secret scan (working tree)"
bash scripts/secret_scan.sh --tree
stage "gitleaks (history)"
if git rev-parse -q --verify HEAD >/dev/null; then
  bash scripts/gitleaks.sh history
else
  echo "no commits yet"
fi

printf '\ncheck.sh: ALL STAGES PASSED\n'
