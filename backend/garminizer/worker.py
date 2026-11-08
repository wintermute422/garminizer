"""Background worker (the `worker` service): scheduled sync, backfill and nightly backups.

- incremental sync every SYNC_INTERVAL_HOURS, plus once shortly after start (catch-up after the
  PC was off)
- backfill in budgeted chunks every 15 minutes until the whole history is in
- nightly database backup at 03:30 local time (keeps BACKUP_KEEP files)
All sync jobs are no-ops until Garmin is connected, and on demo databases.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from garminizer import backup
from garminizer.config import Settings, get_settings
from garminizer.db import migrate

log = logging.getLogger("garminizer.worker")
BACKFILL_EVERY_MIN = 15
BACKFILL_BUDGET_S = 10 * 60


def _engine() -> Any:
    from garminizer.sync import engine  # noqa: PLC0415 - optional until sync is configured

    return engine


def job_incremental(settings: Settings) -> None:
    try:
        summary = _engine().run_incremental(settings)
        log.info("incremental sync: %s", summary)
    except Exception:
        log.exception("incremental sync failed")


def job_backfill(settings: Settings, scheduler: BlockingScheduler) -> None:
    try:
        done = bool(_engine().run_backfill_chunk(settings, BACKFILL_BUDGET_S))
    except Exception:
        log.exception("backfill chunk failed")
        return
    if done:
        log.info("backfill complete; stopping the backfill job")
        scheduler.remove_job("backfill")


def job_backup(settings: Settings) -> None:
    try:
        made = backup.create_backup(settings)
        log.info("backup written: %s (%d bytes)", made.path.name, made.size_bytes)
    except Exception:
        log.exception("backup failed")


def build_scheduler(settings: Settings) -> BlockingScheduler:
    tz = ZoneInfo(settings.tz)
    scheduler = BlockingScheduler(timezone=tz)
    now = datetime.now(tz)
    scheduler.add_job(
        job_incremental,
        "interval",
        hours=settings.sync_interval_hours,
        next_run_time=now + timedelta(seconds=30),
        args=[settings],
        id="incremental",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_backfill,
        "interval",
        minutes=BACKFILL_EVERY_MIN,
        next_run_time=now + timedelta(minutes=3),
        args=[settings, scheduler],
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
    settings = get_settings()
    migrate.upgrade()
    scheduler = build_scheduler(settings)
    log.info(
        "worker started: sync every %.1f h, backups at 03:30 %s",
        settings.sync_interval_hours,
        settings.tz,
    )
    scheduler.start()
