import uuid

from fastapi import Request, Response

from app.config import Settings
from app.services.errors import BadOrigin, NoSession
from app.services.plan_service import PlanService

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def cookie_name(settings: Settings) -> str:
    return "__Host-sid" if settings.cookie_secure else "sid"


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        cookie_name(settings),
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    # Same attributes as when set: browsers ignore a __Host- cookie (deletion included)
    # that comes without Secure.
    response.delete_cookie(
        cookie_name(settings),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def get_service(request: Request) -> PlanService:
    service: PlanService = request.app.state.service
    return service


async def require_session(request: Request) -> uuid.UUID:
    token = request.cookies.get(cookie_name(request.app.state.settings))
    if not token:
        raise NoSession()
    session_id = await get_service(request).resolve_session(token)
    if session_id is None:
        raise NoSession()
    request.state.session_id = session_id  # read by AccessLogMiddleware for sid=... logging
    return session_id


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if request.method in UNSAFE and origin and origin != request.app.state.settings.public_origin:
        raise BadOrigin("Запрос с чужого источника отклонён")
