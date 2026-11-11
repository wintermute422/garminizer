"""data/private_values.txt: the account's identifying values, for scripts/secret_scan.sh.

The scan blocks commits containing any of these exact values (display name, full name, profile
id, e-mail, and the rounded coordinates of the most frequent activity start = "home area").
The file lives under data/ (git-ignored), is created with mode 0600 and is never printed.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.db import SCHEMA
from garminizer.sync.parsers.profile import identifying_values

FILE_NAME = "private_values.txt"


def _raw(session: Session, dataset: str) -> Any:
    return session.scalar(
        select(m.RawPayload.payload).where(m.RawPayload.dataset == dataset).limit(1)
    )


def _str(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    s = str(value).strip()
    return s or None


def collect(session: Session) -> list[str]:
    """Identifying values from the stored profile and activities (order kept, no duplicates)."""
    raw = identifying_values(_raw(session, "identity"), _raw(session, "personal_information"))
    values: list[str | None] = [_str(v) for v in raw]
    athlete = session.scalar(select(m.Athlete))
    if athlete is not None:
        values += [_str(athlete.display_name), _str(athlete.full_name), _str(athlete.profile_id)]
    home = session.execute(
        text(
            f"""
            SELECT round(start_lat::numeric, 3) AS lat, round(start_lon::numeric, 3) AS lon
            FROM {SCHEMA}.activity
            WHERE start_lat IS NOT NULL AND start_lon IS NOT NULL
            GROUP BY 1, 2 ORDER BY count(*) DESC, 1, 2 LIMIT 1
            """  # noqa: S608 - schema constant
        )
    ).first()
    if home is not None:
        values += [f"{float(home.lat):.3f}", f"{float(home.lon):.3f}"]
    return list(dict.fromkeys(v for v in values if v))


def write(data_dir: Path, values: list[str]) -> Path:
    """Merge values into data_dir/private_values.txt (existing lines are kept)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / FILE_NAME
    existing: list[str] = []
    if path.is_file():
        existing = [
            line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    merged = list(dict.fromkeys([*existing, *values]))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(f"{v}\n" for v in merged))
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return path


def update(session: Session, data_dir: Path) -> Path | None:
    values = collect(session)
    return write(data_dir, values) if values else None
