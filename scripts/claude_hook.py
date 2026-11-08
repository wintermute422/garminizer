"""Claude Code hooks for this repo (wired in .claude/settings.json via scripts/claude_hook.sh).

post-edit: after Edit/Write, auto-format the file and feed remaining problems back (exit 2):
           *.py -> ruff check --fix, ruff format, mypy; web/**/*.ts(x) -> prettier, eslint.
pre-bash:  block force pushes, pushes to main, broad/forced `git add`, skipped hooks,
           history rewrites, Docker volume deletion and printing secret/token files.
selftest:  run the pre-bash rules against known good/bad commands (used by check.sh).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_GIT = r"\bgit\b[^;&|\n]*"
_READERS = (
    r"\b(cat|type|head|tail|less|more|bat|sed|awk|grep|rg|findstr|strings"
    r"|Get-Content|gc|Select-String|xxd|od)\b"
)
BLOCKED_BASH: list[tuple[str, str]] = [
    (
        _GIT + r"\bpush\b[^;&|\n]*(\s--force(-with-lease)?\b|\s-[a-zA-Z]*f\b|\s\+\S)",
        "force pushes are not allowed",
    ),
    (
        _GIT + r"\bpush\b[^;&|\n]*\s(origin\s+)?(HEAD:)?(main|master)\b",
        "push to main is not allowed; open a PR from a feature branch",
    ),
    (
        _GIT + r"\badd\b[^;&|\n]*\s(-A|--all|-f|--force)\b",
        "use explicit paths with git add (no -A/--all/-f)",
    ),
    (_GIT + r"\badd\s+\.(\s|$)", "use explicit paths with git add (no `git add .`)"),
    (r"--no-verify\b", "skipping git hooks is not allowed"),
    (
        _GIT + r"\b(rebase|filter-branch|filter-repo)\b",
        "history rewrites are not allowed on pushed branches",
    ),
    (
        r"\bdocker\b[^;&|\n]*\b(volume\s+(rm|prune)|system\s+prune)\b",
        "deleting Docker volumes would destroy the database; do it by hand if you really mean it",
    ),
    (
        r"\bdocker\b[^;&|\n]*\bcompose\b[^;&|\n]*\bdown\b[^;&|\n]*(\s-v\b|--volumes)",
        "`compose down -v` deletes the database volume; not allowed",
    ),
    (
        _READERS + r"[^;&|\n]*(?<![\w.-])\.env(?![\w.-])",
        "reading .env is not allowed (it holds secrets); use .env.example",
    ),
    (
        _READERS + r"[^;&|\n]*\bdata[/\\](tokens|backups|private_values)",
        "reading token/backup/private files is not allowed",
    ),
]

SELFTEST_BLOCKED = [
    "git push --force origin feat/v1",
    "git push -f",
    "git push origin main",
    "git push origin HEAD:main",
    "git add -A",
    "git add .",
    "git commit --no-verify -m x",
    "git rebase -i HEAD~3",
    "docker volume rm garminizer_pgdata",
    "docker compose down -v",
    "cat .env",
    "Get-Content .env",
    "grep PASSWORD .env",
    "cat data/tokens/garmin_tokens.json",
]
SELFTEST_ALLOWED = [
    "git push -u origin feat/v1",
    "git add backend/garminizer/config.py",
    "git commit -m 'feat: x'",
    "cat .env.example",
    "docker compose down",
    "docker compose -f compose.dev.yml up -d",
    "grep -r fastapi backend",
    "git log --oneline -3",
]


def _python() -> str:
    for cand in (ROOT / ".venv" / "bin" / "python", ROOT / ".venv" / "Scripts" / "python.exe"):
        if cand.exists():
            return str(cand)
    return sys.executable


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    return proc.returncode, f"{proc.stdout}{proc.stderr}".strip()


def _post_edit_python(path: Path) -> list[str]:
    py = _python()
    if _run([py, "-m", "ruff", "--version"], ROOT)[0] != 0:
        print(
            "claude_hook: ruff not installed yet, skipping (pip install -e '.[dev]')",
            file=sys.stderr,
        )
        return []
    problems: list[str] = []
    _run([py, "-m", "ruff", "check", "--fix", "--quiet", str(path)], ROOT)
    _run([py, "-m", "ruff", "format", "--quiet", str(path)], ROOT)
    for cmd in ([py, "-m", "ruff", "check", str(path)], [py, "-m", "mypy", str(path)]):
        code, out = _run(cmd, ROOT)
        if code != 0:
            problems.append(f"$ {' '.join(cmd[1:])}\n{out}")
    return problems


def _post_edit_web(path: Path) -> list[str]:
    web = ROOT / "web"
    pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd")
    if pnpm is None or not (web / "node_modules").exists():
        return []
    rel = path.relative_to(web).as_posix()
    problems: list[str] = []
    _run([pnpm, "exec", "prettier", "--write", "--log-level", "warn", rel], web)
    if path.suffix in {".ts", ".tsx"}:
        code, out = _run([pnpm, "exec", "eslint", "--max-warnings=0", rel], web)
        if code != 0:
            problems.append(f"$ eslint {rel}\n{out}")
    return problems


def post_edit(event: dict[str, object]) -> int:
    tool_input = event.get("tool_input")
    raw = tool_input.get("file_path", "") if isinstance(tool_input, dict) else ""
    if not isinstance(raw, str) or not raw:
        return 0
    path = Path(raw).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError:
        return 0
    if not path.exists():
        return 0
    problems: list[str] = []
    if path.suffix == ".py":
        problems = _post_edit_python(path)
    elif (ROOT / "web") in path.parents and path.suffix in {".ts", ".tsx", ".css", ".json"}:
        problems = _post_edit_web(path)
    if problems:
        print("\n\n".join(problems), file=sys.stderr)
        return 2
    return 0


def blocked_reason(command: str) -> str | None:
    for pattern, reason in BLOCKED_BASH:
        if re.search(pattern, command):
            return reason
    return None


def pre_bash(event: dict[str, object]) -> int:
    tool_input = event.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str):
        return 0
    reason = blocked_reason(command)
    if reason:
        print(f"Blocked by repo policy (scripts/claude_hook.py): {reason}", file=sys.stderr)
        return 2
    return 0


def selftest() -> int:
    failures = [c for c in SELFTEST_BLOCKED if blocked_reason(c) is None]
    failures += [f"(false positive) {c}" for c in SELFTEST_ALLOWED if blocked_reason(c)]
    if failures:
        print("claude_hook selftest FAILED:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    n_blocked, n_allowed = len(SELFTEST_BLOCKED), len(SELFTEST_ALLOWED)
    print(f"claude_hook selftest: OK ({n_blocked} blocked, {n_allowed} allowed)")
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "selftest":
        return selftest()
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict):
        return 0
    if mode == "post-edit":
        return post_edit(event)
    if mode == "pre-bash":
        return pre_bash(event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
