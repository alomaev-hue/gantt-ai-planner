import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.services.errors import AgentBusy


class SessionLocks:
    def __init__(self) -> None:
        self._locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._idle: dict[uuid.UUID, asyncio.Event] = {}

    def lock(self, session_id: uuid.UUID) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    def _event(self, session_id: uuid.UUID) -> asyncio.Event:
        if session_id not in self._idle:
            ev = asyncio.Event()
            ev.set()
            self._idle[session_id] = ev
        return self._idle[session_id]

    def is_busy(self, session_id: uuid.UUID) -> bool:
        return not self._event(session_id).is_set()

    @asynccontextmanager
    async def agent_turn(self, session_id: uuid.UUID) -> AsyncIterator[None]:
        ev = self._event(session_id)
        if not ev.is_set():
            raise AgentBusy()
        ev.clear()
        try:
            yield
        finally:
            ev.set()

    async def wait_not_busy(self, session_id: uuid.UUID, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._event(session_id).wait(), timeout)
            return True
        except TimeoutError:
            return False

    def forget(self, session_id: uuid.UUID) -> None:
        """Drop the lock/idle entries for a deleted session, unless still in use.

        Safe no-op when the session was never seen, is currently locked
        (``lock()``'s asyncio.Lock held), or busy (an ``agent_turn`` in
        progress) — dropping entries out from under an in-flight operation
        would let a concurrent caller create a fresh, unsynchronized lock.
        """
        lock = self._locks.get(session_id)
        if lock is not None and lock.locked():
            return
        idle = self._idle.get(session_id)
        if idle is not None and not idle.is_set():
            return
        self._locks.pop(session_id, None)
        self._idle.pop(session_id, None)
