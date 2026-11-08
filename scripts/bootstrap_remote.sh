#!/usr/bin/env bash
# One-time bootstrap: create the GitHub repo (private) and push the initial `main`.
# Refuses when the remote already has a main branch - afterwards main changes only via PRs.
# Usage: scripts/bootstrap_remote.sh OWNER/NAME "description"
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
fail() { echo "bootstrap_remote: $*" >&2; exit 1; }

repo="${1:?usage: bootstrap_remote.sh OWNER/NAME \"description\"}"
desc="${2:-}"
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || fail "run this on the local main branch"

if ! git remote get-url origin >/dev/null 2>&1; then
  if gh repo view "$repo" >/dev/null 2>&1; then
    git remote add origin "https://github.com/$repo.git"
  else
    gh repo create "$repo" --private --description "$desc" --source . --remote origin
  fi
fi
if git ls-remote --exit-code --heads origin main >/dev/null 2>&1; then
  fail "origin already has main; use a feature branch and a PR"
fi
git push -u origin main
