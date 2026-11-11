"""Original activity files: store the downloaded zip, decode its FIT `record` messages.

Garmin's "original" download is a zip with one `<id>_ACTIVITY.fit` (activities imported from
other services may contain GPX/TCX instead; those are stored but not decoded).
"""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import fitdecode
from sqlalchemy import select
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.sports import FOOT_GROUPS
from garminizer.sync import store
from garminizer.sync.parsers.common import Patch, Replace, Upsert, num

log = logging.getLogger(__name__)

MAX_FIT_BYTES = 64 * 1024 * 1024
FIT_EPOCH = datetime(1989, 12, 31, tzinfo=UTC)
SEMICIRCLE_DEG = 180.0 / 2**31
MAX_START_SKEW = timedelta(hours=1)


def is_fit(data: bytes) -> bool:
    return len(data) >= 12 and data[8:12] == b".FIT"


def extract_fit(content: bytes) -> bytes | None:
    """The FIT file inside a Garmin "original" zip (or the content itself if it is FIT)."""
    if is_fit(content):
        return content
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return None
    with archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".fit"):
                continue
            if info.file_size > MAX_FIT_BYTES:
                log.warning("FIT member too large (%d bytes), skipped", info.file_size)
                return None
            with archive.open(info) as fh:
                data = fh.read(MAX_FIT_BYTES + 1)
            if len(data) > MAX_FIT_BYTES:
                return None
            return data
    return None


def read_records(fit_bytes: bytes) -> list[dict[str, Any]]:
    """Decoded `record` messages as {field name: value} (truncated files: what was readable)."""
    records: list[dict[str, Any]] = []
    try:
        with fitdecode.FitReader(
            io.BytesIO(fit_bytes),
            check_crc=fitdecode.CrcCheck.DISABLED,
            error_handling=fitdecode.ErrorHandling.IGNORE,
        ) as reader:
            for frame in reader:
                if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "record":
                    records.append({f.name: f.value for f in frame.fields})
    except fitdecode.FitError as exc:
        log.warning("FIT decoding stopped early (%s)", type(exc).__name__)
    return records


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return FIT_EPOCH + timedelta(seconds=value)
    return None


def _semicircles(value: Any) -> float | None:
    f = num(value)
    if f is None:
        return None
    deg = f * SEMICIRCLE_DEG
    return round(deg, 7) if -180.0 <= deg <= 180.0 else None


def _first(r: Mapping[str, Any], *keys: str) -> float | None:
    for k in keys:
        v = num(r.get(k))
        if v is not None:
            return v
    return None


def _small(v: float | None, lo: int = 0, hi: int = 32767) -> int | None:
    if v is None:
        return None
    i = round(v)
    return i if lo <= i <= hi else None


def _scaled(v: float | None, factor: float, ndigits: int) -> float | None:
    return None if v is None else round(v * factor, ndigits)


def record_rows(
    records: Sequence[Mapping[str, Any]],
    *,
    activity_id: int,
    sport_group: str,
    start: datetime | None = None,
) -> list[dict[str, Any]]:
    """FIT record messages → activity_sample rows (t_s = whole seconds since the start).

    Positions are converted from semicircles; enhanced speed/altitude are preferred; running
    cadence (FIT stores strides/min + fractional part) becomes steps/min; vertical oscillation
    mm → cm, step length mm → m. Several records in the same second merge (later values win).
    """
    stamped = [(t, r) for r in records if (t := _timestamp(r.get("timestamp"))) is not None]
    if not stamped:
        return []
    first_ts = min(t for t, _ in stamped)
    t0 = start if start is not None and abs(first_ts - start) <= MAX_START_SKEW else first_ts
    t0 = min(t0, first_ts)
    foot = sport_group in FOOT_GROUPS
    out: dict[int, dict[str, Any]] = {}
    for ts, r in sorted(stamped, key=lambda p: p[0]):
        t_s = int((ts - t0).total_seconds())  # whole seconds (floor; t0 <= ts)
        lat, lon = _semicircles(r.get("position_lat")), _semicircles(r.get("position_long"))
        if lat is None or lon is None or abs(lat) > 90:
            lat = lon = None
        cadence = _first(r, "cadence")
        if cadence is not None and foot:
            cadence = (cadence + (_first(r, "fractional_cadence") or 0.0)) * 2.0
        row = {
            "activity_id": activity_id,
            "t_s": t_s,
            "ts": ts,
            "lat": lat,
            "lon": lon,
            "altitude_m": _scaled(_first(r, "enhanced_altitude", "altitude"), 1.0, 2),
            "distance_m": _scaled(_first(r, "distance"), 1.0, 2),
            "speed_mps": _scaled(_first(r, "enhanced_speed", "speed"), 1.0, 3),
            "hr": _small(_first(r, "heart_rate"), 1, 300),
            "cadence": _small(cadence),
            "power_w": _small(_first(r, "power")),
            "temperature_c": _scaled(_first(r, "temperature"), 1.0, 1),
            "vertical_oscillation_cm": _scaled(_first(r, "vertical_oscillation"), 0.1, 2),
            "ground_contact_ms": _scaled(_first(r, "stance_time"), 1.0, 1),
            "stride_length_m": _scaled(_first(r, "step_length"), 0.001, 3),
            "respiration_rate": _scaled(
                _first(r, "enhanced_respiration_rate", "respiration_rate"), 1.0, 1
            ),
        }
        previous = out.get(t_s)
        if previous is not None:
            row = {k: (v if v is not None else previous.get(k)) for k, v in row.items()}
        out[t_s] = row
    return [out[k] for k in sorted(out)]


def store_file(session: Session, activity_id: int, content: bytes) -> str:
    """Keep the downloaded original (zip) in activity_file; returns its sha256."""
    digest = hashlib.sha256(content).hexdigest()
    store.apply(
        session,
        [
            Upsert(
                m.ActivityFile,
                [
                    {
                        "activity_id": activity_id,
                        "file_format": "fit_zip" if not is_fit(content) else "fit",
                        "content": content,
                        "size_bytes": len(content),
                        "sha256": digest,
                        "fetched_at": datetime.now(UTC),
                    }
                ],
                ("activity_id",),
            )
        ],
    )
    return digest


def ingest_samples(session: Session, activity_id: int) -> int:
    """(Re)build activity_sample from the stored file; sets activity.has_samples."""
    row = session.execute(
        select(m.ActivityFile.content, m.Activity.sport_group, m.Activity.start_time_utc)
        .join(m.Activity, m.Activity.activity_id == m.ActivityFile.activity_id)
        .where(m.ActivityFile.activity_id == activity_id)
    ).first()
    if row is None:
        return 0
    content, group, start = row
    fit_bytes = extract_fit(bytes(content))
    rows = (
        record_rows(
            read_records(fit_bytes), activity_id=activity_id, sport_group=group, start=start
        )
        if fit_bytes
        else []
    )
    written = store.apply(
        session,
        [
            Replace(m.ActivitySample, {"activity_id": activity_id}, rows),
            Patch(
                m.Activity,
                {"activity_id": activity_id},
                {"has_samples": bool(rows)},
                overwrite=True,
            ),
        ],
    )
    return written
