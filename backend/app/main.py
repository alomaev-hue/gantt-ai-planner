import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.llm import make_llm
from app.agent.loop import Agent
from app.api import routes_chat, routes_events, routes_plan, routes_session
from app.api.errors import install_error_handlers
from app.config import Settings, get_settings
from app.db.engine import make_engine, make_sessionmaker
from app.logging_setup import AccessLogMiddleware
from app.logging_setup import configure as configure_logging
from app.mcp_server.client import PlanToolClient
from app.mcp_server.server import build_mcp
from app.services.cleanup import run_cleanup_cycle
from app.services.events import EventBus
from app.services.locks import SessionLocks
from app.services.plan_service import PlanService

logger = logging.getLogger("app.cleanup")

CLEANUP_INTERVAL_SECONDS = 3600
CLEANUP_FIRST_RUN_DELAY_SECONDS = 30


async def _cleanup_loop(app: FastAPI, cfg: Settings) -> None:
    """Purge expired sessions hourly; first run shortly after startup.

    Failures are logged and swallowed so a transient DB hiccup never crashes
    the loop or the app (no crash loop) — the next hourly tick tries again.
    """
    await asyncio.sleep(CLEANUP_FIRST_RUN_DELAY_SECONDS)
    while True:
        try:
            await run_cleanup_cycle(
                app.state.sessionmaker,
                app.state.service.locks,
                app.state.service.bus,
                ttl_days=cfg.session_ttl_days,
                now=datetime.now(UTC),
            )
        except Exception:
            logger.exception("session cleanup cycle failed")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


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
        cleanup_task = asyncio.create_task(_cleanup_loop(app, cfg))
        try:
            app.state.mcp = build_mcp(app.state.service, today=today_fn)
            async with PlanToolClient(app.state.mcp) as tool_client:
                app.state.tool_client = tool_client
                app.state.agent = Agent(
                    make_llm(cfg), tool_client, app.state.service, today=today_fn
                )
                yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            if engine is not None:
                await engine.dispose()

    configure_logging(cfg.log_level)

    app = FastAPI(
        title="Gantt AI Planner",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(AccessLogMiddleware)
    install_error_handlers(app)
    app.include_router(routes_session.router)
    app.include_router(routes_plan.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_events.router)

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
