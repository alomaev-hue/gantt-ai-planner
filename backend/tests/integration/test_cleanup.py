import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.db import repo
from app.db.models import SessionRow
from app.services.cleanup import purge_expired, run_cleanup_cycle
from app.services.events import EventBus
from app.services.locks import SessionLocks

NOW = datetime(2026, 9, 25, tzinfo=UTC)


async def _make_session(sessionmaker, *, age_days: int) -> uuid.UUID:
    async with sessionmaker() as db, db.begin():
        row = await repo.create_session(db, uuid.uuid4().bytes + uuid.uuid4().bytes)
        await repo.add_version(
            db,
            session_id=row.id,
            version_no=1,
            snapshot={"a": 1},
            source="seed",
            turn_id=None,
            summary="",
            diff=[],
        )
        await repo.add_chat_message(db, session_id=row.id, role="user", content="hi")
        await db.execute(
            update(SessionRow)
            .where(SessionRow.id == row.id)
            .values(last_seen_at=NOW - timedelta(days=age_days))
        )
    return row.id


async def test_purge_expired_deletes_old_session_and_cascades(sessionmaker):
    old_id = await _make_session(sessionmaker, age_days=30)
    fresh_id = await _make_session(sessionmaker, age_days=1)

    purged = await purge_expired(sessionmaker, ttl_days=14, now=NOW)

    assert purged == [old_id]
    async with sessionmaker() as db:
        assert await repo.get_session(db, old_id) is None
        assert await repo.get_version(db, old_id, 1) is None
        assert await repo.recent_chat_messages(db, old_id, 10) == []
        assert await repo.get_session(db, fresh_id) is not None


async def test_purge_expired_keeps_fresh_sessions(sessionmaker):
    fresh_id = await _make_session(sessionmaker, age_days=1)

    purged = await purge_expired(sessionmaker, ttl_days=14, now=NOW)

    assert purged == []
    async with sessionmaker() as db:
        assert await repo.get_session(db, fresh_id) is not None


async def test_run_cleanup_cycle_forgets_purged_sessions(sessionmaker):
    old_id = await _make_session(sessionmaker, age_days=30)
    locks = SessionLocks()
    bus = EventBus()
    locks.lock(old_id)  # register entries as if the session had been active
    bus.subscribe(old_id)
    assert old_id in locks._locks
    assert old_id in bus._subs

    purged = await run_cleanup_cycle(sessionmaker, locks, bus, ttl_days=14, now=NOW)

    assert purged == [old_id]
    assert old_id not in locks._locks
    assert old_id not in bus._subs
