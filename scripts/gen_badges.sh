#!/usr/bin/env bash
# Regenerate the README badges in docs/badges/ from shields.io (needs network, run by hand).
# They are committed so the README loads them from GitHub itself: shields.io badges go through
# GitHub's image proxy (camo), which privacy filters and ad blockers often block.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
OUT="docs/badges"
mkdir -p "$OUT"

badge() {  # badge FILE SHIELDS-PATH
  curl -fsS --max-time 20 -o "$OUT/$1.tmp" "https://img.shields.io/badge/$2"
  grep -q '<svg' "$OUT/$1.tmp" || { echo "gen_badges: $1 is not an SVG" >&2; exit 1; }
  mv "$OUT/$1.tmp" "$OUT/$1"
}

badge license.svg "license-MIT-blue"
badge docker.svg "self--hosted-Docker%20Compose-2496ED?logo=docker&logoColor=white"
badge postgresql.svg "PostgreSQL-17-4169E1?logo=postgresql&logoColor=white"
badge python.svg "Python-3.12%2B-3776AB?logo=python&logoColor=white"
badge react.svg "React-19-087EA4?logo=react&logoColor=61DAFB"
echo "gen_badges: wrote $(ls "$OUT"/*.svg | wc -l | tr -d ' ') badges to $OUT"
