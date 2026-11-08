#!/usr/bin/env bash
# Secret / personal-data scan. Never prints matched values, only file:line and the rule name.
#
# Exact values are read at runtime from the untracked .env and data/private_values.txt
# (written by the app after you connect Garmin: display name, profile id, email, home area),
# plus the local user name, so the real values are never stored in a tracked file.
#
# Usage:
#   scripts/secret_scan.sh --staged          # added lines of the staged diff
#   scripts/secret_scan.sh --range A..B      # added lines of a commit range
#   scripts/secret_scan.sh --history         # every commit's diff + commit messages (all refs)
#   scripts/secret_scan.sh --tree [PATH...]  # tracked + untracked non-ignored files + extra paths
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
VALUES="$TMP/values"
: >"$VALUES"
chmod 600 "$VALUES"

env_value() {  # env_value FILE KEY -> prints the value (quotes and CR stripped)
  [ -f "$1" ] || return 0
  local line val
  line="$(grep -E "^[[:space:]]*$2=" "$1" | tail -n1 || true)"
  val="${line#*=}"
  val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
  printf '%s' "$val" | tr -d '\r' | sed 's/[[:space:]]*$//'
}
add_value() {  # skip empty/placeholder/too-short values (noise, not protection)
  case "$1" in ""|*example*|change-me|demo-password|your-*|"~"*) return 0 ;; esac
  [ "${#1}" -ge 6 ] || return 0
  printf '%s\n' "$1" >>"$VALUES"
}
for key in GARMIN_EMAIL GARMIN_PASSWORD APP_PASSWORD APP_SECRET_KEY POSTGRES_PASSWORD DATABASE_URL; do
  add_value "$(env_value .env "$key")"
done
if [ -f data/private_values.txt ]; then
  while IFS= read -r v || [ -n "$v" ]; do add_value "$(printf '%s' "$v" | tr -d '\r')"; done <data/private_values.txt
fi

# Local identity: user name inside home paths and as an e-mail local part.
for u in "${USER:-}" "${USERNAME:-}"; do
  if [ -n "$u" ] && [ "${#u}" -ge 3 ]; then
    printf '/home/%s\n' "$u" >>"$VALUES"
    printf 'Users\\%s\n' "$u" >>"$VALUES"
    printf 'Users/%s\n' "$u" >>"$VALUES"
  fi
done
sort -u "$VALUES" -o "$VALUES"

# Generic patterns (extended regex). Name|regex
GENERIC="$TMP/generic"
cat >"$GENERIC" <<'EOF'
private-ipv4|(^|[^0-9.])(10\.[0-9]{1,3}|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]{1,3}\.[0-9]{1,3}([^0-9]|$)
home-path|/home/[a-z_][a-z0-9_-]*/
windows-user-path|[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z]
private-key|-----BEGIN [A-Z ]*PRIVATE KEY-----
jwt|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.
email|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}
EOF
# Allowed placeholders that look like generic hits.
ALLOW='/home/(user|you|runner|<user>|USER|\$USER)/|noreply|@example\.(com|org|net)|@users\.noreply\.github\.com|anthropic\.com|@localhost'

FINDINGS="$TMP/findings"
: >"$FINDINGS"

# Files that legitimately contain the generic regexes themselves.
SELF_EXCLUDE='^([0-9a-f]{8}:)?(scripts/secret_scan\.sh|\.gitleaks\.toml)$'

# Scan a stream of "path<TAB>lineno<TAB>text" records.
scan_records() {
  local records="$1"
  [ -s "$records" ] || return 0
  if [ -s "$VALUES" ]; then
    # -F fixed strings, values come from a file (never on the command line).
    cut -f3- "$records" | grep -n -i -F -f "$VALUES" | cut -d: -f1 | while read -r n; do
      sed -n "${n}p" "$records" | awk -F'\t' '{print $1":"$2": exact value from .env/private_values/local user"}'
    done >>"$FINDINGS" || true
  fi
  awk -F'\t' -v OFS='\t' '{print $1, $2}' "$records" >"$TMP/meta"
  while IFS='|' read -r name rx; do
    cut -f3- "$records" | grep -n -E -e "$rx" | grep -v -E -e "$ALLOW" | cut -d: -f1 | while read -r n; do
      path="$(sed -n "${n}p" "$TMP/meta" | cut -f1)"
      if ! printf '%s' "$path" | grep -q -E "$SELF_EXCLUDE"; then
        printf '%s: %s\n' "$(sed -n "${n}p" "$TMP/meta" | tr '\t' ':')" "$name"
      fi
    done >>"$FINDINGS" || true
  done <"$GENERIC"
}

# Convert a unified diff (on stdin) into records of added lines.
diff_to_records() {
  awk -v OFS='\t' '
    /^\+\+\+ / { f=$2; sub(/^b\//, "", f); next }
    /^@@/ { match($0, /\+[0-9]+/); n=substr($0, RSTART+1, RLENGTH-1)-1; next }
    /^\+/ { n++; print f, n, substr($0, 2); next }
    /^ / { n++ }
  '
}

MODE="${1:---tree}"; shift || true
REC="$TMP/records"
case "$MODE" in
  --staged)
    git diff --cached --no-color -U0 --diff-filter=ACMR | diff_to_records >"$REC" ;;
  --range)
    git diff --no-color -U0 --diff-filter=ACMR "$1" | diff_to_records >"$REC" ;;
  --history)
    : >"$REC"
    for c in $(git rev-list --all); do
      git show --no-color -U0 --format= --diff-filter=ACMR "$c" | diff_to_records | \
        awk -v c="${c:0:8}" -F'\t' -v OFS='\t' '{print c":"$1, $2, $3}' >>"$REC"
    done
    # commit messages too
    git log --all --format='%h%x09%B' | awk -F'\t' -v OFS='\t' 'NF>1{h=$1; print "msg:"h, 1, $2; next} {print "msg:"h, 0, $0}' >>"$REC"
    ;;
  --tree)
    : >"$REC"
    { git ls-files --cached --others --exclude-standard; for p in "$@"; do printf '%s\n' "$p"; done; } | while read -r f; do
      [ -f "$f" ] || continue
      grep -Iq . "$f" 2>/dev/null || continue   # skip binary files
      awk -v f="$f" -v OFS='\t' '{print f, NR, $0}' "$f"
    done >"$REC"
    ;;
  *) echo "unknown mode: $MODE" >&2; exit 64 ;;
esac

scan_records "$REC"

if [ -s "$FINDINGS" ]; then
  echo "secret_scan: FAIL ($(sort -u "$FINDINGS" | wc -l | tr -d ' ') finding(s), values redacted):" >&2
  sort -u "$FINDINGS" >&2
  exit 1
fi
echo "secret_scan: OK ($MODE, $(wc -l <"$VALUES" | tr -d ' ') exact values + $(wc -l <"$GENERIC" | tr -d ' ') generic rules)"
