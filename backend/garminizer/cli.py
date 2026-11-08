"""Command line interface: `garminizer --help`."""

from __future__ import annotations

import typer

from garminizer import __version__
from garminizer.db import migrate

app = typer.Typer(help="Garminizer: your Garmin data, in your own database.", no_args_is_help=True)
db_app = typer.Typer(help="Database schema management.", no_args_is_help=True)
app.add_typer(db_app, name="db")


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
