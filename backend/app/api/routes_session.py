import uuid

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import (
    check_origin,
    clear_session_cookie,
    cookie_name,
    get_service,
    require_session,
    set_session_cookie,
)

router = APIRouter(prefix="/api", tags=["session"])


@router.post("/session")
async def create_session(
    request: Request, response: Response, _: None = Depends(check_origin)
) -> dict[str, bool]:
    settings = request.app.state.settings
    token = request.cookies.get(cookie_name(settings))
    service = get_service(request)
    if token is not None and await service.resolve_session(token) is not None:
        return {"ok": True}
    new_token, _session_id = await service.create_session()
    set_session_cookie(response, settings, new_token)
    return {"ok": True}


@router.delete("/session", status_code=204)
async def delete_session(
    request: Request,
    response: Response,
    session_id: uuid.UUID = Depends(require_session),
    _: None = Depends(check_origin),
) -> None:
    settings = request.app.state.settings
    service = get_service(request)
    await service.delete_session(session_id)
    clear_session_cookie(response, settings)
