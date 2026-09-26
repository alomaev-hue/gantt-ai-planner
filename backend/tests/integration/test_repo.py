import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.db import repo
from app.db.models import SessionRow


async def test_session_lifecycle_and_cascade(sessionmaker):
    async with sessionmaker() as db, db.begin():
        s = await repo.create_session(db, b"h" * 32)
        await repo.add_version(
            db,
            session_id=s.id,
            version_no=1,
            snapshot={"a": 1},
            source="seed",
            turn_id=None,
            summary="Демо",
            diff=[],
        )
        await repo.add_chat_message(db, session_id=s.id, role="user", content="привет")
    async with sessionmaker() as db, db.begin():
        found = await repo.get_session_by_token_hash(db, b"h" * 32)
        assert found is not None and found.id == s.id
        await repo.delete_session(db, s.id)
    async with sessionmaker() as db:
        assert await repo.get_version(db, s.id, 1) is None
        assert await repo.recent_chat_messages(db, s.id, 10) == []


async def test_versions_meta_delete_after_and_prune(sessionmaker):
    turn = uuid.uuid4()
    async with sessionmaker() as db, db.begin():
        s = await repo.create_session(db, b"v" * 32)
        for n in range(1, 6):
            await repo.add_version(
                db,
                session_id=s.id,
                version_no=n,
                snapshot={"n": n},
                source="agent",
                turn_id=turn if n in (3, 4) else None,
                summary="",
                diff=[],
            )
    async with sessionmaker() as db, db.begin():
        meta = await repo.list_version_meta(db, s.id)
        assert [m.version_no for m in meta] == [1, 2, 3, 4, 5]
        assert meta[2].turn_id == turn and meta[0].turn_id is None
        await repo.delete_versions_after(db, s.id, 3)
        await repo.prune_versions(db, s.id, keep=2)
    async with sessionmaker() as db:
        assert [m.version_no for m in await repo.list_version_meta(db, s.id)] == [2, 3]


async def test_chat_order_and_rate_counts(sessionmaker):
    async with sessionmaker() as db, db.begin():
        a = await repo.create_session(db, b"a" * 32)
        b = await repo.create_session(db, b"b" * 32)
        for i in range(3):
            await repo.add_chat_message(db, session_id=a.id, role="user", content=f"m{i}")
        await repo.add_chat_message(db, session_id=a.id, role="assistant", content="ответ")
        await repo.add_chat_message(db, session_id=b.id, role="user", content="x")
    since = datetime.now(UTC) - timedelta(hours=1)
    async with sessionmaker() as db:
        assert [m.content for m in await repo.recent_chat_messages(db, a.id, 3)] == [
            "m1",
            "m2",
            "ответ",
        ]
        assert await repo.count_user_messages_since(db, since, a.id) == 3
        assert await repo.count_user_messages_since(db, since) == 4


async def test_delete_expired_session_ids(sessionmaker):
    async with sessionmaker() as db, db.begin():
        old = await repo.create_session(db, b"o" * 32)
        fresh = await repo.create_session(db, b"f" * 32)
        await db.execute(
            update(SessionRow)
            .where(SessionRow.id == old.id)
            .values(last_seen_at=datetime.now(UTC) - timedelta(days=30))
        )
    async with sessionmaker() as db, db.begin():
        ids = await repo.delete_expired_session_ids(db, datetime.now(UTC) - timedelta(days=14))
        assert ids == [old.id]
        assert await repo.get_session(db, fresh.id) is not None
