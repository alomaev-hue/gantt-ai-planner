import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse

from app.api.deps import get_service, require_session
from app.services.events import EventBus

router = APIRouter(prefix="/api/events")


async def event_stream(
    bus: EventBus, session_id: uuid.UUID, *, busy: bool
) -> AsyncIterator[dict[str, str]]:
    queue = bus.subscribe(session_id)
    try:
        yield {"event": "agent_status", "data": json.dumps({"type": "agent_status", "busy": busy})}
        while True:
            event = await queue.get()
            yield {"event": event["type"], "data": json.dumps(event, ensure_ascii=False)}
    finally:
        bus.unsubscribe(session_id, queue)


@router.get("")
async def events(
    request: Request, session_id: uuid.UUID = Depends(require_session)
) -> EventSourceResponse:
    service = get_service(request)
    stream = event_stream(service.bus, session_id, busy=service.locks.is_busy(session_id))
    return EventSourceResponse(stream, ping=20, sep="\n")
