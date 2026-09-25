import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse

from app.api.deps import check_origin, get_service, require_session
from app.db import repo
from app.services.errors import AgentBusy
from app.services.ratelimit import check_chat_limits

router = APIRouter(prefix="/api/chat")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.post("", dependencies=[Depends(check_origin)])
async def chat(
    body: ChatRequest, request: Request, session_id: uuid.UUID = Depends(require_session)
) -> EventSourceResponse:
    service = get_service(request)
    settings = request.app.state.settings
    if service.locks.is_busy(session_id):
        raise AgentBusy()
    async with service.sessionmaker() as db:
        await check_chat_limits(
            db,
            session_id,
            per_hour=settings.chat_limit_per_hour,
            per_day=settings.chat_limit_per_day,
        )
    agent = request.app.state.agent

    async def gen() -> AsyncIterator[dict[str, str]]:
        async for event in agent.run_turn(session_id, body.message.strip()):
            yield {"event": event["type"], "data": json.dumps(event, ensure_ascii=False)}

    return EventSourceResponse(gen(), ping=15, sep="\n")


@router.get("/history")
async def history(
    request: Request, session_id: uuid.UUID = Depends(require_session)
) -> list[dict[str, Any]]:
    async with get_service(request).sessionmaker() as db:
        rows = await repo.recent_chat_messages(db, session_id, 200)
    return [
        {
            "id": r.id,
            "role": r.role,
            "content": r.content,
            "created_at": r.created_at.isoformat(),
            "meta": r.meta,
        }
        for r in rows
    ]
