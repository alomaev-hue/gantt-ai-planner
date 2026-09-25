from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import routes_plan, routes_session
from app.api.errors import install_error_handlers
from app.config import Settings, get_settings
from app.db.engine import make_engine, make_sessionmaker
from app.services.events import EventBus
from app.services.locks import SessionLocks
from app.services.plan_service import PlanService


def create_app(
    settings: Settings | None = None,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    today: Callable[[], date] | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    today_fn = today or date.today

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        sm = sessionmaker
        if sm is None:
            engine = make_engine(cfg)
            sm = make_sessionmaker(engine)
        app.state.settings = cfg
        app.state.sessionmaker = sm
        app.state.service = PlanService(
            sm, EventBus(), SessionLocks(), max_versions=cfg.max_versions, today=today_fn
        )
        try:
            yield
        finally:
            if engine is not None:
                await engine.dispose()

    app = FastAPI(
        title="Gantt AI Planner",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    install_error_handlers(app)
    app.include_router(routes_session.router)
    app.include_router(routes_plan.router)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        async with app.state.sessionmaker() as db:
            await db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok"})

    _mount_spa(app, cfg)  # must stay the LAST registration: catch-all route
    return app


def _mount_spa(app: FastAPI, settings: Settings) -> None:
    if not settings.static_dir or not Path(settings.static_dir).is_dir():
        return
    root = Path(settings.static_dir).resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / "index.html")
