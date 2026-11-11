"""The worker maps sync outcomes to its schedule: the backfill job stops once history is in."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from garminizer import worker
from garminizer.config import Settings
from garminizer.sync import service
from garminizer.sync.engine import RunSummary


class _Scheduler:
    def __init__(self) -> None:
        self.removed: list[str] = []

    def remove_job(self, job_id: str) -> None:
        self.removed.append(job_id)


def _summary(done: bool) -> RunSummary:
    return RunSummary(
        run_id=1, kind="backfill", status="ok", requests=3, items_written=9, errors=0,
        message=None, done=done,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("outcome", "stops"),
    [
        (service.Ran(_summary(done=True)), True),
        (service.Ran(_summary(done=False)), False),
        (service.Skipped("complete", "backfill complete"), True),
        (service.Skipped("not_connected", service.NOT_CONNECTED), False),
        (service.Busy("a Garmin sync is already running"), False),
        (service.Failed("the saved Garmin tokens were rejected or expired"), False),
    ],
)
def test_backfill_job_stops_only_when_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: service.Outcome, stops: bool
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_start(kind: str, deps: service.SyncDeps, **kwargs: Any) -> service.Outcome:
        calls.append({"kind": kind, **kwargs})
        return outcome

    monkeypatch.setattr(service, "start", fake_start)
    deps = service.SyncDeps(lambda: None, Settings(data_dir=tmp_path, _env_file=None))  # type: ignore[arg-type, return-value]
    scheduler = _Scheduler()
    worker.job_backfill(deps, scheduler)
    assert calls == [
        {"kind": "backfill", "budget_s": worker.BACKFILL_BUDGET_S, "skip_if_complete": True}
    ]
    assert scheduler.removed == (["backfill"] if stops else [])


def test_jobs_survive_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> service.Outcome:
        raise RuntimeError("database gone")

    monkeypatch.setattr(service, "start", boom)
    deps = service.SyncDeps(lambda: None, Settings(data_dir=tmp_path, _env_file=None))  # type: ignore[arg-type, return-value]
    scheduler = _Scheduler()
    worker.job_incremental(deps)
    worker.job_backfill(deps, scheduler)
    assert scheduler.removed == []
