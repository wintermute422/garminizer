"""Fail if any given (or tracked) text file is not valid UTF-8 or contains CRLF line endings.

Usage: python scripts/check_utf8.py [FILE ...]   (no args: all tracked files)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2", ".fit", ".zip"}


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def main(argv: list[str]) -> int:
    files = argv or _tracked()
    problems: list[str] = []
    for name in files:
        path = Path(name)
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:4096]:
            continue  # binary
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            problems.append(f"{name}: not UTF-8 (byte offset {exc.start})")
            continue
        if b"\r\n" in data:
            problems.append(f"{name}: CRLF line endings")
    if problems:
        print("check_utf8: FAIL\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(f"check_utf8: OK ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
