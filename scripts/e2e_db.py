"""Ensure the deterministic e2e demo database exists (portable: local Docker or CI service).

Usage: python scripts/e2e_db.py URL END_DAY [--reseed]
Creates the database if missing (or recreates it with --reseed) and seeds 730 demo days.
Refuses database names that do not end in "_e2e".
"""

from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer.db import migrate
from garminizer.demo.seed import seed_demo


def main(argv: list[str]) -> int:
    url, end = argv[0], date.fromisoformat(argv[1])
    reseed = "--reseed" in argv[2:]
    parsed = make_url(url)
    name = parsed.database or ""
    if not name.endswith("_e2e"):
        print(f"e2e_db: refusing to touch database {name!r}", file=sys.stderr)
        return 2
    admin = create_engine(
        parsed.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
        ).first()
        if exists and not reseed:
            print("e2e_db: database exists")
            return 0
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    migrate.upgrade(url)
    engine = create_engine(url, poolclass=NullPool)
    with Session(engine) as session:
        report = seed_demo(session, end=end, days=730, seed=42)
        session.commit()
    engine.dispose()
    print(f"e2e_db: seeded {report.activities} activities in {report.seconds}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
