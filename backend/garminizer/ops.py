"""Operations commands: worker, backup, restore (registered on the main CLI)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from garminizer import backup

ops_app = typer.Typer(help="Backups.", no_args_is_help=True)


@ops_app.command("create")
def backup_create(
    keep: int | None = typer.Option(None, help="Backups to keep (default BACKUP_KEEP)."),
) -> None:
    """Write a pg_dump of the whole database to data/backups."""
    try:
        made = backup.create_backup(keep=keep)
    except backup.BackupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"backup: {made.path.name} ({made.size_bytes / 1e6:.1f} MB)")


@ops_app.command("list")
def backup_list() -> None:
    """List existing backups, newest first."""
    for b in backup.list_backups():
        typer.echo(f"{b.created_at:%Y-%m-%d %H:%M}  {b.size_bytes / 1e6:8.1f} MB  {b.path.name}")


@ops_app.command("restore")
def backup_restore(
    file: Annotated[Path, typer.Argument(help="Backup file (see `garminizer backup list`).")],
    yes: bool = typer.Option(False, "--yes", help="Confirm replacing the current database."),
) -> None:
    """Restore a backup into the configured database (replaces its contents)."""
    if not yes:
        typer.echo("Restoring replaces all current data. Re-run with --yes to confirm.", err=True)
        raise typer.Exit(2)
    try:
        backup.restore_backup(file)
    except backup.BackupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo("restore: done")


def worker() -> None:
    """Run the background worker (scheduled sync, backfill, nightly backups)."""
    from garminizer import worker as worker_module  # noqa: PLC0415 - heavy imports

    worker_module.run()
