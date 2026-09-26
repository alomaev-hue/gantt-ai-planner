import asyncio
import uuid
from collections import defaultdict
from contextlib import suppress
from typing import Any


class EventBus:
    """In-process per-session pub/sub. Valid for a single uvicorn worker only (see README)."""

    def __init__(self) -> None:
        self._subs: dict[uuid.UUID, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def subscribe(self, session_id: uuid.UUID) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subs[session_id].add(queue)
        return queue

    def unsubscribe(self, session_id: uuid.UUID, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subs.get(session_id)
        if subs is None:
            return
        subs.discard(queue)
        if not subs:
            del self._subs[session_id]

    def publish(self, session_id: uuid.UUID, event: dict[str, Any]) -> None:
        for queue in list(self._subs.get(session_id, ())):
            with suppress(asyncio.QueueFull):  # slow client; it refetches the plan on reconnect
                queue.put_nowait(event)

    def forget(self, session_id: uuid.UUID) -> None:
        """Drop the subscriber set for a deleted session so it doesn't linger forever."""
        self._subs.pop(session_id, None)
