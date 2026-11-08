"""Generate docs/data-model.md from the SQLAlchemy models (table + column comments).

Usage: python scripts/gen_data_model_doc.py [--check]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from sqlalchemy import Table

import garminizer.models  # noqa: F401 - registers every table
from garminizer.db.base import SCHEMA, Base

OUT = Path(__file__).resolve().parent.parent / "docs" / "data-model.md"

GROUPS: list[tuple[str, list[str]]] = [
    ("Athlete, devices & gear", ["athlete", "device", "gear", "activity_gear"]),
    (
        "Activities",
        [
            "activity",
            "activity_lap",
            "activity_split",
            "activity_sample",
            "activity_zone",
            "activity_weather",
            "activity_file",
        ],
    ),
    (
        "Daily wellness & sleep",
        ["daily_summary", "sleep", "sleep_stage", "hrv_daily"],
    ),
    (
        "All-day (intraday) series",
        [
            "hr_sample",
            "stress_sample",
            "body_battery_sample",
            "respiration_sample",
            "spo2_sample",
            "steps_interval",
        ],
    ),
    (
        "Training & performance",
        [
            "training_readiness",
            "training_status",
            "max_metric",
            "race_prediction",
            "endurance_score",
            "hill_score",
        ],
    ),
    (
        "Body, records & goals",
        ["body_composition", "blood_pressure", "personal_record", "badge", "goal"],
    ),
    (
        "Computed by Garminizer",
        [
            "daily_load",
            "activity_best_effort",
            "activity_best_distance",
            "activity_track",
            "activity_tile",
        ],
    ),
    (
        "Sync bookkeeping & raw data",
        ["raw_payload", "sync_run", "sync_cursor", "sync_error", "app_setting"],
    ),
]

VIEWS = [
    ("weekly_volume", "Training volume per ISO week and sport group."),
    ("monthly_volume", "Training volume per calendar month and sport group."),
    ("explorer_tile", "Every visited map tile with visit count and first/last visit."),
    ("v_daily", "One row per day with every daily metric side by side (for correlations)."),
]


def _anchor(title: str) -> str:
    """GitHub heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")


def _table_md(t: Table) -> str:
    lines = [f"### `{t.name}`", "", (t.comment or "").strip(), ""]
    pk = {c.name for c in t.primary_key.columns}
    lines += ["| Column | Type | Null | Description |", "|---|---|---|---|"]
    for c in t.columns:
        name = f"**{c.name}**" if c.name in pk else c.name
        ctype = (
            str(c.type)
            .lower()
            .replace("double precision", "double")
            .replace("timestamp with time zone", "timestamptz")
        )
        lines.append(f"| {name} | {ctype} | {'yes' if c.nullable else 'no'} | {c.comment or ''} |")
    return "\n".join(lines) + "\n"


def render() -> str:
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    listed = {n for _, names in GROUPS for n in names}
    missing = sorted(set(tables) - listed)
    if missing:
        raise SystemExit(f"gen_data_model_doc: tables not assigned to a group: {missing}")
    out = [
        "# Data model",
        "",
        f"Everything lives in the PostgreSQL schema `{SCHEMA}`. This file is generated from the",
        "models by `scripts/gen_data_model_doc.py` — edit the column comments, not this file.",
        "Units are SI (m, s, m/s, kg, W, bpm, °C); `day` columns are the athlete's local calendar",
        "date; timestamps are UTC (`timestamptz`). **Bold** columns form the primary key.",
        "",
        "Three layers: `raw_payload` keeps every Garmin response verbatim (re-parse at any time",
        "without re-downloading), typed tables hold the parsed values, and the *computed* tables",
        "and views are rebuilt by `garminizer analytics refresh`.",
        "",
        "## Contents",
        "",
    ]
    out += [f"- [{g}](#{_anchor(g)})" for g, _ in GROUPS]
    out += ["- [Views](#views)", ""]
    for group, names in GROUPS:
        out += [f"## {group}", ""]
        out += [_table_md(tables[n]) for n in names]
    out += ["## Views", "", "| View | Description |", "|---|---|"]
    out += [f"| `{SCHEMA}.{n}` | {d} |" for n, d in VIEWS]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            print("gen_data_model_doc: docs/data-model.md is out of date", file=sys.stderr)
            return 1
        print("gen_data_model_doc: up to date")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"gen_data_model_doc: wrote {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
