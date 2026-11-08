#!/usr/bin/env bash
# Entry point for the Claude Code hooks in .claude/settings.json.
# Picks a working interpreter via pyenv.sh and execs it, so the hook's exit code
# (2 = block / feed back) reaches Claude Code unchanged.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT
# shellcheck source=scripts/pyenv.sh
. "$ROOT/scripts/pyenv.sh"
exec "$PY" "$ROOT/scripts/claude_hook.py" "$@"
