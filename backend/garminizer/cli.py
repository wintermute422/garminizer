"""Command line interface: `garminizer --help`."""

from __future__ import annotations

import typer

from garminizer import __version__
from garminizer.db import migrate

app = typer.Typer(help="Garminizer: your Garmin data, in your own database.", no_args_is_help=True)
db_app = typer.Typer(help="Database schema management.", no_args_is_help=True)
demo_app = typer.Typer(help="Synthetic demo data.", no_args_is_help=True)
analytics_app = typer.Typer(
    help="Derived tables (best efforts, load, tracks).", no_args_is_help=True
)
app.add_typer(db_app, name="db")
app.add_typer(demo_app, name="demo")
app.add_typer(analytics_app, name="analytics")


@analytics_app.command("refresh")
def analytics_refresh(
    force: bool = typer.Option(False, help="Reprocess every activity, not only pending ones."),
) -> None:
    """Compute best efforts, zones, splits, tracks, tiles and the daily load series."""
    from garminizer.analytics import pipeline  # noqa: PLC0415 - keep CLI start-up light
    from garminizer.db import session_scope  # noqa: PLC0415

    with session_scope() as session:
        report = pipeline.run(session, force=force)
    typer.echo(f"analytics: {report.activities} activities, {report.daily_rows} days of load")


@demo_app.command("seed")
def demo_seed(
    days: int = typer.Option(730, help="Number of days to simulate (ending today)."),
    seed: int = typer.Option(42, help="Random seed (same seed = same data)."),
    end: str | None = typer.Option(None, help="Last simulated day, YYYY-MM-DD (default: today)."),
) -> None:
    """Fill the database with a synthetic demo athlete (refuses if real data is present)."""
    from datetime import date  # noqa: PLC0415 - keep CLI start-up light

    from garminizer.db import session_scope  # noqa: PLC0415
    from garminizer.demo.seed import RealDataError, seed_demo  # noqa: PLC0415

    migrate.upgrade()
    try:
        with session_scope() as session:
            report = seed_demo(
                session, days=days, seed=seed, end=date.fromisoformat(end) if end else None
            )
    except RealDataError as exc:
        typer.echo(f"refused: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"demo: {report.activities} activities over {report.days} days in {report.seconds}s")
    for table, n in sorted(report.rows.items()):
        typer.echo(f"  {table:<22} {n:>10,}")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Override APP_HOST (default 127.0.0.1)."),
    port: int | None = typer.Option(None, help="Override APP_PORT (default 8420)."),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (development)."),
) -> None:
    """Run the web app (API + dashboards)."""
    import os  # noqa: PLC0415 - keep CLI start-up light

    import uvicorn  # noqa: PLC0415

    from garminizer.config import get_settings  # noqa: PLC0415

    if host:
        os.environ["APP_HOST"] = host
    if port:
        os.environ["APP_PORT"] = str(port)
    get_settings.cache_clear()
    settings = get_settings()
    settings.check_web_safety()
    migrate.upgrade()
    uvicorn.run(
        "garminizer.api.app:create_app",
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
        reload=reload,
        proxy_headers=True,
    )


@app.command()
def version() -> None:
    """Print the Garminizer version."""
    typer.echo(__version__)


@db_app.command("upgrade")
def db_upgrade(revision: str = typer.Argument("head")) -> None:
    """Apply migrations (default: to the latest revision)."""
    migrate.upgrade(revision=revision)
    typer.echo(f"database at revision {migrate.current_revision()}")


@db_app.command("current")
def db_current() -> None:
    """Show the applied migration revision."""
    typer.echo(migrate.current_revision() or "empty (no migrations applied)")


if __name__ == "__main__":
    app()
