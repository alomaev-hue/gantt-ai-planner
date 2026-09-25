import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import repo
from app.db.repo import VersionMeta
from app.domain.diff import Change, diff_plans, summarize_changes
from app.domain.errors import ConfirmationRequired, DomainError
from app.domain.models import Plan
from app.domain.operations import Operation, apply_operations, requires_confirmation
from app.domain.scheduler import ScheduledPlan, schedule
from app.domain.seed import build_demo_plan
from app.services.errors import AgentBusy, NoSession, NothingToRedo, NothingToUndo
from app.services.events import EventBus
from app.services.locks import SessionLocks
from app.services.sessions import hash_token, new_token

Source = Literal["seed", "import", "user", "agent", "mcp", "reset"]
MCP_WAIT_SECONDS = 10.0


@dataclass(frozen=True)
class PlanState:
    version: int
    plan: Plan
    scheduled: ScheduledPlan
    can_undo: bool
    can_redo: bool


@dataclass(frozen=True)
class ApplyOutcome:
    state: PlanState
    changes: list[Change]
    warnings: list[str]
    created_task_ids: list[int]
    summary: str


def _index(meta: list[VersionMeta], current: int) -> int:
    return next(i for i, m in enumerate(meta) if m.version_no == current)


def undo_target(meta: list[VersionMeta], current: int) -> int | None:
    i = _index(meta, current)
    turn = meta[i].turn_id
    if turn is not None:
        while i > 0 and meta[i - 1].turn_id == turn:
            i -= 1
    return meta[i - 1].version_no if i > 0 else None


def redo_target(meta: list[VersionMeta], current: int) -> int | None:
    i = _index(meta, current)
    if i + 1 >= len(meta):
        return None
    i += 1
    turn = meta[i].turn_id
    if turn is not None:
        while i + 1 < len(meta) and meta[i + 1].turn_id == turn:
            i += 1
    return meta[i].version_no


class PlanService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        bus: EventBus,
        locks: SessionLocks,
        *,
        max_versions: int = 50,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.bus = bus
        self.locks = locks
        self._max_versions = max_versions
        self._today = today

    async def create_session(self) -> tuple[str, uuid.UUID]:
        token = new_token()
        plan = build_demo_plan(self._today())
        async with self.sessionmaker() as db, db.begin():
            row = await repo.create_session(db, hash_token(token))
            await repo.add_version(
                db,
                session_id=row.id,
                version_no=1,
                snapshot=plan.model_dump(mode="json"),
                source="seed",
                turn_id=None,
                summary="Демо-план",
                diff=[],
            )
            row.current_version = 1
        return token, row.id

    async def resolve_session(self, token: str) -> uuid.UUID | None:
        async with self.sessionmaker() as db, db.begin():
            row = await repo.get_session_by_token_hash(db, hash_token(token))
            if row is None:
                return None
            await repo.touch_session(db, row.id)
            return row.id

    async def delete_session(self, session_id: uuid.UUID) -> None:
        async with self.sessionmaker() as db, db.begin():
            await repo.delete_session(db, session_id)

    async def get_state(self, session_id: uuid.UUID) -> PlanState:
        async with self.sessionmaker() as db:
            return await self._state(db, session_id)

    async def _state(self, db: AsyncSession, session_id: uuid.UUID) -> PlanState:
        session = await repo.get_session(db, session_id)
        if session is None:
            raise NoSession()
        version = await repo.get_version(db, session_id, session.current_version)
        if version is None:
            raise DomainError("Текущая версия плана не найдена")
        meta = await repo.list_version_meta(db, session_id)
        plan = Plan.model_validate(version.snapshot)
        return PlanState(
            version=session.current_version,
            plan=plan,
            scheduled=schedule(plan),
            can_undo=undo_target(meta, session.current_version) is not None,
            can_redo=redo_target(meta, session.current_version) is not None,
        )

    async def _guard_busy(self, session_id: uuid.UUID, source: Source) -> None:
        if source == "agent" or not self.locks.is_busy(session_id):
            return
        if source == "mcp" and await self.locks.wait_not_busy(session_id, MCP_WAIT_SECONDS):
            return
        raise AgentBusy()

    async def apply(
        self,
        session_id: uuid.UUID,
        ops: Sequence[Operation],
        *,
        source: Source,
        turn_id: uuid.UUID | None = None,
        confirmed: bool = False,
    ) -> ApplyOutcome:
        await self._guard_busy(session_id, source)
        async with self.locks.lock(session_id), self.sessionmaker() as db, db.begin():
            current = await self._state(db, session_id)
            if not confirmed and requires_confirmation(current.plan, ops):
                raise ConfirmationRequired(
                    "Пакет удаляет много задач. Спросите пользователя и повторите с confirmed=true"
                )
            result = apply_operations(current.plan, ops)
            summary = summarize_changes(result.changes)
            if result.changes:
                await self._commit(
                    db,
                    session_id,
                    current.version,
                    result.plan,
                    source,
                    turn_id,
                    summary,
                    [c.model_dump() for c in result.changes],
                )
            state = await self._state(db, session_id)
        if result.changes:
            changed_ids = sorted({c.task_id for c in result.changes})
            self._publish(session_id, state.version, source, turn_id, changed_ids)
        return ApplyOutcome(
            state, result.changes, result.warnings, result.created_task_ids, summary
        )

    async def replace(
        self,
        session_id: uuid.UUID,
        plan: Plan,
        *,
        source: Source,
        summary: str,
        chat_note: str | None = None,
    ) -> PlanState:
        await self._guard_busy(session_id, source)
        async with self.locks.lock(session_id), self.sessionmaker() as db, db.begin():
            current = await self._state(db, session_id)
            changes = diff_plans(current.scheduled, schedule(plan))
            await self._commit(
                db,
                session_id,
                current.version,
                plan,
                source,
                None,
                summary,
                [c.model_dump() for c in changes],
            )
            if chat_note:
                await repo.add_chat_message(
                    db, session_id=session_id, role="system", content=chat_note
                )
            state = await self._state(db, session_id)
        self._publish(session_id, state.version, source, None, sorted({c.task_id for c in changes}))
        return state

    async def reset(self, session_id: uuid.UUID) -> PlanState:
        return await self.replace(
            session_id, build_demo_plan(self._today()), source="reset", summary="Сброс к демо-плану"
        )

    async def undo(self, session_id: uuid.UUID, *, source: Source = "user") -> PlanState:
        return await self._move_pointer(session_id, undo_target, NothingToUndo(), source)

    async def redo(self, session_id: uuid.UUID) -> PlanState:
        return await self._move_pointer(session_id, redo_target, NothingToRedo(), "user")

    async def _move_pointer(
        self,
        session_id: uuid.UUID,
        target_fn: Callable[[list[VersionMeta], int], int | None],
        empty_error: DomainError,
        source: Source,
    ) -> PlanState:
        await self._guard_busy(session_id, source)
        async with self.locks.lock(session_id), self.sessionmaker() as db, db.begin():
            before = await self._state(db, session_id)
            target = target_fn(await repo.list_version_meta(db, session_id), before.version)
            if target is None:
                raise empty_error
            session = await repo.get_session(db, session_id)
            assert session is not None
            session.current_version = target
            await db.flush()
            state = await self._state(db, session_id)
        changed = sorted({c.task_id for c in diff_plans(before.scheduled, state.scheduled)})
        self._publish(session_id, state.version, source, None, changed)
        return state

    async def _commit(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        current_version: int,
        plan: Plan,
        source: Source,
        turn_id: uuid.UUID | None,
        summary: str,
        diff: list[dict[str, Any]],
    ) -> None:
        await repo.delete_versions_after(db, session_id, current_version)
        new_version = current_version + 1
        await repo.add_version(
            db,
            session_id=session_id,
            version_no=new_version,
            snapshot=plan.model_dump(mode="json"),
            source=source,
            turn_id=turn_id,
            summary=summary,
            diff=diff,
        )
        session = await repo.get_session(db, session_id)
        assert session is not None
        session.current_version = new_version
        await db.flush()
        await repo.prune_versions(db, session_id, keep=self._max_versions)

    def _publish(
        self,
        session_id: uuid.UUID,
        version: int,
        source: Source,
        turn_id: uuid.UUID | None,
        changed: list[int],
    ) -> None:
        self.bus.publish(
            session_id,
            {
                "type": "plan_changed",
                "version": version,
                "source": source,
                "turn_id": str(turn_id) if turn_id else None,
                "changed_task_ids": changed,
            },
        )
