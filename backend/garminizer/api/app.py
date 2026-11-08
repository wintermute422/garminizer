"""FastAPI application factory: JSON API under /api, the built SPA everywhere else."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from garminizer import __version__
from garminizer.api import security
from garminizer.api.routers import (
    activities,
    body,
    calendar,
    gear,
    insights,
    maps,
    meta,
    overview,
    performance,
    records,
    sleep,
    sync,
    training,
    wellness,
    year,
)
from garminizer.config import Settings, get_settings

ROUTERS = (
    meta,
    activities,
    overview,
    training,
    performance,
    records,
    wellness,
    sleep,
    body,
    calendar,
    maps,
    insights,
    gear,
    year,
    sync,
)
DEFAULT_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app(
    settings: Settings | None = None,
    *,
    database_url: str | None = None,
    web_dist: Path | None = DEFAULT_WEB_DIST,
) -> FastAPI:
    settings = settings or get_settings()
    settings.check_web_safety()
    engine = create_engine(database_url or settings.database_url, pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with factory() as session:
            app.state.secret_key = security.secret_key(settings, session)
        yield
        engine.dispose()

    app = FastAPI(
        title="Garminizer",
        version=__version__,
        description="Your Garmin Connect data in your own database. All values in SI units.",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = factory
    app.middleware("http")(security.guard)
    app.include_router(security.router)
    for module in ROUTERS:
        app.include_router(module.router)
    if web_dist is not None and (web_dist / "index.html").is_file():
        _mount_spa(app, web_dist)
    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    def spa(path: str) -> FileResponse | JSONResponse:
        if path.startswith("api/"):
            return JSONResponse({"detail": "not found"}, status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
