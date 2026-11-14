"""Background worker (the `worker` service): scheduled sync, backfill and nightly backups.

- incremental sync every SYNC_INTERVAL_HOURS, plus once shortly after start (catch-up after the
  PC was off)
- quick sync (new activities and weigh-ins only) every QUICK_SYNC_MINUTES (default 60; 0 = off)
  for the weight goal and the energy balance
- backfill in budgeted chunks every 15 minutes until the whole history is in
- nightly database backup at 03:30 local time (keeps BACKUP_KEEP files)
All sync jobs are no-ops until Garmin is connected, and on demo databases.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from garminizer import backup
from garminizer.config import Settings, get_settings
from garminizer.db import migrate

if TYPE_CHECKING:
    from garminizer.sync.service import SyncDeps

log = logging.getLogger("garminizer.worker")
BACKFILL_EVERY_MIN = 15
BACKFILL_BUDGET_S = 10 * 60


def job_incremental(deps: SyncDeps) -> None:
    from garminizer.sync import service  # noqa: PLC0415 - heavy imports, worker only

    try:
        log.info(service.describe_outcome("incremental", service.start("incremental", deps)))
    except Exception:
        log.exception("incremental sync failed")


def job_quick(deps: SyncDeps) -> None:
    from garminizer.sync import service  # noqa: PLC0415

    try:
        log.info(service.describe_outcome("quick", service.start("quick", deps)))
    except Exception:
        log.exception("quick sync failed")


def job_backfill(deps: SyncDeps, scheduler: BlockingScheduler) -> None:
    from garminizer.sync import service  # noqa: PLC0415

    try:
        outcome = service.start("backfill", deps, budget_s=BACKFILL_BUDGET_S, skip_if_complete=True)
    except Exception:
        log.exception("backfill chunk failed")
        return
    log.info(service.describe_outcome("backfill", outcome))
    done = (isinstance(outcome, service.Ran) and outcome.summary.done) or (
        isinstance(outcome, service.Skipped) and outcome.reason == "complete"
    )
    if done:
        log.info("backfill complete; stopping the backfill job")
        scheduler.remove_job("backfill")


def job_backup(settings: Settings) -> None:
    try:
        made = backup.create_backup(settings)
        log.info("backup written: %s (%d bytes)", made.path.name, made.size_bytes)
    except Exception:
        log.exception("backup failed")


def build_scheduler(settings: Settings, deps: SyncDeps) -> BlockingScheduler:
    tz = ZoneInfo(settings.tz)
    scheduler = BlockingScheduler(timezone=tz)
    now = datetime.now(tz)
    scheduler.add_job(
        job_incremental,
        "interval",
        hours=settings.sync_interval_hours,
        next_run_time=now + timedelta(seconds=30),
        args=[deps],
        id="incremental",
        max_instances=1,
        coalesce=True,
    )
    if settings.quick_sync_minutes > 0:
        scheduler.add_job(
            job_quick,
            "interval",
            minutes=settings.quick_sync_minutes,
            next_run_time=now + timedelta(minutes=settings.quick_sync_minutes),
            args=[deps],
            id="quick",
            max_instances=1,
            coalesce=True,
        )
    scheduler.add_job(
        job_backfill,
        "interval",
        minutes=BACKFILL_EVERY_MIN,
        next_run_time=now + timedelta(minutes=3),
        args=[deps, scheduler],
        id="backfill",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_backup,
        "cron",
        hour=3,
        minute=30,
        args=[settings],
        id="backup",
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def run() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    from garminizer.db.session import session_factory  # noqa: PLC0415
    from garminizer.sync.service import SyncDeps  # noqa: PLC0415

    settings = get_settings()
    migrate.upgrade()
    deps = SyncDeps(session_factory(settings.database_url), settings)
    scheduler = build_scheduler(settings, deps)
    log.info(
        "worker started: sync every %.1f h, activities + weigh-ins every %s, backups at 03:30 %s",
        settings.sync_interval_hours,
        f"{settings.quick_sync_minutes:g} min" if settings.quick_sync_minutes > 0 else "(off)",
        settings.tz,
    )
    scheduler.start()
