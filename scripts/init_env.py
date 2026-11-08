"""Create .env from .env.example with freshly generated secrets (stdlib only).

Usage: python scripts/init_env.py [--tz Europe/Berlin]
Refuses to overwrite an existing .env. Never prints the generated values.
"""

from __future__ import annotations

import contextlib
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    target = ROOT / ".env"
    if target.exists():
        print("init_env: .env already exists - left unchanged", file=sys.stderr)
        return 1
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    db_password = secrets.token_urlsafe(24)
    values = {
        "POSTGRES_PASSWORD": db_password,
        "APP_SECRET_KEY": secrets.token_urlsafe(48),
    }
    if "--tz" in argv:
        values["TZ"] = argv[argv.index("--tz") + 1]
    for key, value in values.items():
        text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, count=1, flags=re.M)
    text = re.sub(
        r"^DATABASE_URL=postgresql\+psycopg://garminizer:[^@]*@",
        f"DATABASE_URL=postgresql+psycopg://garminizer:{db_password}@",
        text,
        count=1,
        flags=re.M,
    )
    target.write_text(text, encoding="utf-8", newline="\n")
    with contextlib.suppress(OSError):
        target.chmod(0o600)
    print("init_env: wrote .env with a random database password and secret key")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
