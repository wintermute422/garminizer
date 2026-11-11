#!/usr/bin/env bash
# Run gitleaks: native binary if on PATH, otherwise the pinned Docker image.
# Usage: scripts/gitleaks.sh history | staged | range A..B | dir PATH
#
# The git modes fail when gitleaks scans 0 commits although there are commits to scan, so a
# misconfigured run (e.g. a git worktree whose .git file points outside the mount) can never
# pass vacuously with "no leaks found".
set -euo pipefail
GITLEAKS_IMAGE="${GITLEAKS_IMAGE:-ghcr.io/gitleaks/gitleaks:v8.30.1}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

mode="${1:-history}"; shift || true
expected=0   # commits gitleaks must report at least one of
case "$mode" in
  history)
    args=(git --redact --no-banner -c /repo/.gitleaks.toml /repo)
    expected="$({ git rev-list --count --all 2>/dev/null || true; } | tail -n1)" ;;
  staged)
    args=(git --pre-commit --staged --redact --no-banner -c /repo/.gitleaks.toml /repo)
    git diff --cached --quiet || expected=1 ;;
  range)
    args=(git --redact --no-banner -c /repo/.gitleaks.toml "--log-opts=$1" /repo)
    # shellcheck disable=SC2086  # log-opts is a git argument string, split like gitleaks does
    expected="$({ git rev-list --count $1 2>/dev/null || true; } | tail -n1)" ;;
  dir)
    args=(dir --redact --no-banner -c /repo/.gitleaks.toml "/repo/$1") ;;
  *) echo "unknown mode: $mode" >&2; exit 64 ;;
esac
expected="${expected:-0}"

run_gitleaks() {
  if command -v gitleaks >/dev/null 2>&1; then
    local native=() a
    for a in "${args[@]}"; do native+=("${a//\/repo/$ROOT}"); done
    gitleaks "${native[@]}"
    return
  fi
  if ! command -v docker >/dev/null 2>&1; then
    echo "gitleaks.sh: neither gitleaks nor docker found. Install one (see CONTRIBUTING.md)." >&2
    return 2
  fi
  local host_root="$ROOT"
  if pwd -W >/dev/null 2>&1; then host_root="$(pwd -W)"; fi   # Git Bash on Windows
  # In a git worktree, .git is a file pointing at <common>/worktrees/<name> on the host, which
  # does not exist in the container. Mount the common git dir and point GIT_DIR at the
  # worktree's own git dir inside it (for a plain checkout GIT_DIR is just the common dir).
  local common git_dir rel
  common="$(git rev-parse --path-format=absolute --git-common-dir)"
  git_dir="$(git rev-parse --path-format=absolute --git-dir)"
  case "$git_dir" in
    "$common") rel="" ;;
    "$common"/*) rel="${git_dir#"$common"}" ;;
    *) echo "gitleaks.sh: git dir $git_dir is not inside $common" >&2; return 2 ;;
  esac
  # safe.directory: the container user differs from the mounted repo's owner.
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "$host_root:/repo" -v "$common:/gitcommon" \
    -e "GIT_DIR=/gitcommon$rel" -e GIT_WORK_TREE=/repo \
    -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' \
    "$GITLEAKS_IMAGE" "${args[@]}"
}

if [ "$mode" = dir ]; then run_gitleaks; exit; fi

# gitleaks logs to stderr; keep a copy to check how many commits it really scanned.
log="$(mktemp)"
trap 'rm -f "$log"' EXIT
status=0
run_gitleaks 2>"$log" || status=$?
cat "$log" >&2
[ "$status" -eq 0 ] || exit "$status"

# --pre-commit always logs "0 commits scanned", so staged mode counts the scanned bytes instead.
if [ "$mode" = staged ]; then unit=bytes; pattern='scanned ~[0-9]+ bytes'; todo="staged changes"
else unit=commits; pattern='[0-9]+ commits scanned'; todo="$expected commit(s)"; fi
scanned="$(grep -oE "$pattern" "$log" | tail -n1 | grep -oE '[0-9]+' || true)"
if [ -z "$scanned" ]; then
  echo "gitleaks.sh: FAIL: gitleaks did not report how many $unit it scanned" >&2
  exit 3
fi
if [ "$expected" -gt 0 ] && [ "$scanned" -eq 0 ]; then
  echo "gitleaks.sh: FAIL: gitleaks scanned 0 $unit but $mode has $todo to scan" \
    "(git repository not visible to gitleaks?)" >&2
  exit 3
fi
echo "gitleaks.sh: $scanned $unit scanned ($mode)" >&2
