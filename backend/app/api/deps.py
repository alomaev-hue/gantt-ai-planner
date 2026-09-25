import uuid

from fastapi import Request

from app.config import Settings
from app.services.errors import BadOrigin, NoSession
from app.services.plan_service import PlanService

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def cookie_name(settings: Settings) -> str:
    return "__Host-sid" if settings.cookie_secure else "sid"


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
    return session_id


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if request.method in UNSAFE and origin and origin != request.app.state.settings.public_origin:
        raise BadOrigin("Запрос с чужого источника отклонён")
