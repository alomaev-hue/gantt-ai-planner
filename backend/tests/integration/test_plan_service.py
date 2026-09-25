import asyncio
import uuid
from datetime import date

import pytest

from app.db import repo
from app.domain.errors import ConfirmationRequired, OperationError
from app.domain.operations import operations_adapter
from app.domain.seed import build_demo_plan
from app.services.errors import AgentBusy, NothingToUndo
from app.services.events import EventBus
from app.services.locks import SessionLocks
from app.services.plan_service import PlanService

TODAY = date(2026, 9, 25)


@pytest.fixture
def service(sessionmaker):
    return PlanService(
        sessionmaker, EventBus(), SessionLocks(), max_versions=50, today=lambda: TODAY
    )


def ops(*raw):
    return operations_adapter.validate_python(list(raw))


async def test_create_session_seeds_demo_plan(service):
    token, sid = await service.create_session()
    assert await service.resolve_session(token) == sid
    assert await service.resolve_session("nope") is None
    state = await service.get_state(sid)
    assert state.version == 1 and not state.can_undo and not state.can_redo
    assert state.plan == build_demo_plan(TODAY)


async def test_apply_publishes_event_and_versions(service):
    _, sid = await service.create_session()
    queue = service.bus.subscribe(sid)
    out = await service.apply(
        sid, ops({"op": "move_task", "id": 1, "shift_days": 1}), source="user"
    )
    assert out.state.version == 2 and out.state.can_undo
    event = queue.get_nowait()
    assert (
        event["type"] == "plan_changed" and event["version"] == 2 and 1 in event["changed_task_ids"]
    )


async def test_no_change_batch_creates_no_version(service):
    _, sid = await service.create_session()
    out = await service.apply(
        sid,
        ops({"op": "update_task", "id": 1, "name": "Сбор требований и приоритизация"}),
        source="user",
    )
    assert out.state.version == 1 and out.summary == "Без изменений"


async def test_undo_redo_turn_group_and_truncate(service):
    _, sid = await service.create_session()
    turn = uuid.uuid4()
    await service.apply(
        sid, ops({"op": "update_task", "id": 1, "duration": 5}), source="agent", turn_id=turn
    )
    await service.apply(
        sid, ops({"op": "update_task", "id": 2, "duration": 5}), source="agent", turn_id=turn
    )
    state = await service.undo(sid)
    assert state.version == 1 and state.can_redo
    state = await service.redo(sid)
    assert state.version == 3
    await service.undo(sid)
    await service.apply(sid, ops({"op": "update_task", "id": 3, "duration": 9}), source="user")
    state = await service.get_state(sid)
    assert state.version == 2 and not state.can_redo
    await service.undo(sid)
    with pytest.raises(NothingToUndo):
        await service.undo(sid)


async def test_invalid_batch_leaves_state(service):
    _, sid = await service.create_session()
    with pytest.raises(OperationError):
        await service.apply(sid, ops({"op": "delete_task", "id": 999}), source="user")
    assert (await service.get_state(sid)).version == 1


async def test_confirmation_required_for_mass_delete(service):
    _, sid = await service.create_session()
    batch = ops(*({"op": "delete_task", "id": i} for i in range(1, 8)))
    with pytest.raises(ConfirmationRequired):
        await service.apply(sid, batch, source="agent")
    out = await service.apply(sid, batch, source="agent", confirmed=True)
    assert len(out.state.plan.tasks) == 18


async def test_user_edit_rejected_while_agent_busy_and_mcp_waits(service):
    _, sid = await service.create_session()
    async with service.locks.agent_turn(sid):
        with pytest.raises(AgentBusy):
            await service.apply(
                sid, ops({"op": "update_task", "id": 1, "duration": 2}), source="user"
            )
        with pytest.raises(AgentBusy):
            async with service.locks.agent_turn(sid):
                pass

    async def short_turn():
        async with service.locks.agent_turn(sid):
            await asyncio.sleep(0.2)

    task = asyncio.create_task(short_turn())
    await asyncio.sleep(0.05)
    out = await service.apply(sid, ops({"op": "update_task", "id": 1, "duration": 2}), source="mcp")
    await task
    assert out.state.version == 2


async def test_replace_and_reset_are_undoable_and_add_chat_note(service):
    _, sid = await service.create_session()
    plan = build_demo_plan(TODAY)
    plan.tasks = plan.tasks[:3]
    plan.dependencies = [
        d for d in plan.dependencies if d.predecessor_id <= 3 and d.successor_id <= 3
    ]
    state = await service.replace(
        sid, plan, source="import", summary="Импорт", chat_note="Загружен план «x.xlsx», задач: 3"
    )
    assert len(state.plan.tasks) == 3
    async with service.sessionmaker() as db:
        msgs = await repo.recent_chat_messages(db, sid, 5)
    assert msgs[-1].role == "system" and "x.xlsx" in msgs[-1].content
    assert len((await service.reset(sid)).plan.tasks) == 25
    assert len((await service.undo(sid)).plan.tasks) == 3


async def test_versions_are_pruned(sessionmaker):
    service = PlanService(
        sessionmaker, EventBus(), SessionLocks(), max_versions=3, today=lambda: TODAY
    )
    _, sid = await service.create_session()
    for d in range(2, 7):
        await service.apply(sid, ops({"op": "update_task", "id": 1, "duration": d}), source="user")
    assert (await service.get_state(sid)).version == 6
    await service.undo(sid)
    await service.undo(sid)
    with pytest.raises(NothingToUndo):
        await service.undo(sid)


async def test_delete_session_forgets_lock_and_bus_entries(service):
    _, sid = await service.create_session()
    service.bus.subscribe(sid)
    service.locks.lock(sid)
    assert sid in service.locks._locks
    assert sid in service.bus._subs

    await service.delete_session(sid)

    assert sid not in service.locks._locks
    assert sid not in service.bus._subs
    async with service.sessionmaker() as db:
        assert await repo.get_session(db, sid) is None
