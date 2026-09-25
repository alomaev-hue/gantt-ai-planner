import uuid

from app.services.locks import SessionLocks


async def test_forget_unknown_session_is_noop():
    locks = SessionLocks()
    locks.forget(uuid.uuid4())  # must not raise


async def test_forget_drops_idle_entries_when_not_busy():
    locks = SessionLocks()
    sid = uuid.uuid4()
    async with locks.agent_turn(sid):
        pass  # busy then idle again
    assert sid in locks._idle

    locks.forget(sid)

    assert sid not in locks._idle
    assert sid not in locks._locks


async def test_forget_keeps_entries_while_busy():
    locks = SessionLocks()
    sid = uuid.uuid4()
    async with locks.agent_turn(sid):
        locks.forget(sid)
        assert sid in locks._idle  # still busy: must not be dropped

    locks.forget(sid)
    assert sid not in locks._idle


async def test_forget_keeps_entries_while_lock_held():
    locks = SessionLocks()
    sid = uuid.uuid4()
    lock = locks.lock(sid)
    await lock.acquire()
    try:
        locks.forget(sid)
        assert sid in locks._locks  # still locked: must not be dropped
    finally:
        lock.release()

    locks.forget(sid)
    assert sid not in locks._locks
