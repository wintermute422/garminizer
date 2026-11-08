"""Command line interface: `garminizer --help`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

import typer

from garminizer import __version__
from garminizer.db import migrate
from garminizer.ops import ops_app

if TYPE_CHECKING:
    from garminizer.garmin.client import GarminClient
    from garminizer.sync.engine import RunSummary

app = typer.Typer(help="Garminizer: your Garmin data, in your own database.", no_args_is_help=True)
db_app = typer.Typer(help="Database schema management.", no_args_is_help=True)
demo_app = typer.Typer(help="Synthetic demo data.", no_args_is_help=True)
analytics_app = typer.Typer(
    help="Derived tables (best efforts, load, tracks).", no_args_is_help=True
)
app.add_typer(db_app, name="db")
app.add_typer(demo_app, name="demo")
app.add_typer(analytics_app, name="analytics")
app.add_typer(ops_app, name="backup")


@app.command()
def worker() -> None:
    """Run the background worker: scheduled sync, history backfill, nightly backups."""
    from garminizer import worker as worker_module  # noqa: PLC0415 - heavy imports

    worker_module.run()


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
    if_empty: bool = typer.Option(False, help="Do nothing when the database already has data."),
) -> None:
    """Fill the database with a synthetic demo athlete (refuses if real data is present)."""
    from datetime import date  # noqa: PLC0415 - keep CLI start-up light

    from sqlalchemy import select  # noqa: PLC0415

    from garminizer.config import get_settings  # noqa: PLC0415
    from garminizer.db import session_scope  # noqa: PLC0415
    from garminizer.demo.seed import RealDataError, seed_demo  # noqa: PLC0415
    from garminizer.models import Athlete  # noqa: PLC0415

    if any(get_settings().token_dir.glob("*")):
        typer.echo(
            "refused: Garmin tokens exist here, so this is your real-data installation. Run the "
            "demo with DATABASE_URL pointing at a separate database, or use compose.demo.yml.",
            err=True,
        )
        raise typer.Exit(2)
    migrate.upgrade()
    if if_empty:
        with session_scope() as session:
            if session.scalar(select(Athlete)) is not None:
                typer.echo("demo: database already has data, nothing to do")
                return
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
        host=settings.bind_host,
        port=settings.app_port,
        reload=reload,
        proxy_headers=True,
    )


@app.command("mcp")
def mcp_command(
    env_file: str | None = typer.Option(
        None,
        help="Read DATABASE_URL and TZ from this .env file (for Claude Desktop, which starts "
        "the server outside the Garminizer folder).",
    ),
) -> None:
    """MCP server for Claude Desktop (stdio): log meals, calories and macros.

    Claude Desktop starts this command itself; see docs/claude-desktop.md. It prints nothing
    on stdout except the MCP protocol (logs go to stderr).
    """
    from pathlib import Path  # noqa: PLC0415 - keep CLI start-up light

    from garminizer import mcp_server  # noqa: PLC0415

    path = Path(env_file) if env_file else None
    if path is not None and not path.is_file():
        _fail(f"--env-file {env_file}: no such file", 2)
    mcp_server.main(env_file=path)


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


# --- Garmin connection and sync ---------------------------------------------------------------


def _fail(message: str, code: int = 1) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code)


def _garmin_client() -> GarminClient:
    from garminizer.garmin import auth  # noqa: PLC0415 - keep CLI start-up light
    from garminizer.garmin.client import GarminError  # noqa: PLC0415

    try:
        return auth.resume()
    except GarminError as exc:
        _fail(f"Garmin: {exc}", 2)


def _print_summary(summary: RunSummary) -> None:
    typer.echo(
        f"{summary.kind}: {summary.status}, {summary.requests} requests, "
        f"{summary.items_written} rows written, {summary.errors} errors"
        + (f" - {summary.message}" if summary.message else "")
    )
    if summary.status != "ok":
        raise typer.Exit(1)


def _run_sync(kind: str, **kwargs: Any) -> None:
    from garminizer.db import session_factory  # noqa: PLC0415
    from garminizer.sync import engine  # noqa: PLC0415

    migrate.upgrade()
    client = _garmin_client()
    try:
        if kind == "incremental":
            summary = engine.incremental(session_factory(), client, **kwargs)
        else:
            summary = engine.backfill(session_factory(), client, **kwargs)
    except engine.DemoDatabaseError as exc:
        _fail(f"refused: {exc}", 2)
    except engine.SyncBusyError as exc:
        _fail(f"busy: {exc}", 3)
    _print_summary(summary)


@app.command()
def login() -> None:
    """Connect your Garmin account (password and MFA code are prompted, never echoed)."""
    import getpass  # noqa: PLC0415 - keep CLI start-up light

    from garminizer.config import get_settings  # noqa: PLC0415
    from garminizer.garmin import auth  # noqa: PLC0415
    from garminizer.garmin.client import GarminError  # noqa: PLC0415

    settings = get_settings()
    email: str = typer.prompt("Garmin e-mail", default=settings.garmin_email)
    password = getpass.getpass("Garmin password (not shown): ")
    try:
        result = auth.login(email.strip(), password, settings=settings)
        password = ""
        if result.status == "needs_mfa":
            assert result.state is not None
            code: str = typer.prompt("MFA code Garmin sent you")
            auth.complete_mfa(result.state, code, settings=settings)
    except GarminError as exc:
        _fail(f"login failed: {exc}", 2)
    typer.echo(
        "Connected to Garmin (tokens saved). Next: `garminizer sync` / `garminizer backfill`."
    )


@app.command()
def logout() -> None:
    """Delete the local Garmin tokens (the Garmin account itself is not touched)."""
    from garminizer.garmin import auth  # noqa: PLC0415

    typer.echo("Garmin tokens deleted." if auth.disconnect() else "No Garmin tokens found.")


@app.command()
def sync() -> None:
    """Incremental sync: profile, new/changed activities and the last days of wellness data."""
    _run_sync("incremental")


@app.command()
def backfill(
    until: str | None = typer.Option(
        None, help="Oldest day to go back to, YYYY-MM-DD (default: your first Garmin day)."
    ),
    budget_minutes: float | None = typer.Option(
        None, help="Stop after this many minutes (resume later with the same command)."
    ),
) -> None:
    """Fetch your history backwards to the first Garmin day (resumable)."""
    from datetime import date  # noqa: PLC0415

    _run_sync(
        "backfill",
        until=date.fromisoformat(until) if until else None,
        budget_s=budget_minutes * 60 if budget_minutes is not None else None,
    )


@app.command()
def reparse() -> None:
    """Rebuild the typed tables from the stored raw Garmin responses (no Garmin requests)."""
    from garminizer.db import session_scope  # noqa: PLC0415
    from garminizer.sync import engine  # noqa: PLC0415

    migrate.upgrade()
    try:
        with session_scope() as session:
            summary = engine.reparse(session)
    except engine.DemoDatabaseError as exc:
        _fail(f"refused: {exc}", 2)
    except engine.SyncBusyError as exc:
        _fail(f"busy: {exc}", 3)
    _print_summary(summary)


@app.command()
def verify() -> None:
    """Compare the database with Garmin (activity count, 3 activities, one day's steps)."""
    from garminizer.db import session_scope  # noqa: PLC0415
    from garminizer.sync import engine  # noqa: PLC0415
    from garminizer.sync import verify as verify_mod  # noqa: PLC0415

    client = _garmin_client()
    with session_scope() as session:
        report = verify_mod.verify(session, client, today=engine.local_today(session))
    typer.echo(verify_mod.format_report(report))
    if not report.ok:
        raise typer.Exit(1)


@app.command()
def probe() -> None:
    """Call every daily Garmin dataset once for yesterday; prints only ok / empty / error."""
    from datetime import timedelta  # noqa: PLC0415

    from garminizer.db import session_scope  # noqa: PLC0415
    from garminizer.sync import engine  # noqa: PLC0415
    from garminizer.sync import verify as verify_mod  # noqa: PLC0415

    client = _garmin_client()
    with session_scope() as session:
        day = engine.local_today(session) - timedelta(days=1)
    for name, result in verify_mod.probe(client, day):
        typer.echo(f"{name:<22} {result}")


if __name__ == "__main__":
    app()
