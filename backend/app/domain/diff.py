from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.domain.models import Dependency
from app.domain.scheduler import ScheduledPlan, ScheduledTask

ChangeField = Literal[
    "created",
    "deleted",
    "name",
    "description",
    "assignee",
    "duration",
    "constraint_start",
    "predecessors",
    "start",
    "end",
]
_TRACKED: tuple[ChangeField, ...] = (
    "name",
    "description",
    "assignee",
    "duration",
    "constraint_start",
    "start",
    "end",
)


class Change(BaseModel):
    task_id: int
    task_name: str
    field: ChangeField
    before: str | int | None = None
    after: str | int | None = None


def format_predecessors(deps: list[Dependency], task_id: int) -> str:
    items = sorted((d for d in deps if d.successor_id == task_id), key=lambda d: d.predecessor_id)
    parts = [f"{d.predecessor_id}+{d.lag}" if d.lag else str(d.predecessor_id) for d in items]
    return ", ".join(parts)


def _value(task: ScheduledTask, field: ChangeField) -> str | int | None:
    raw = getattr(task, field)
    if isinstance(raw, date):
        return raw.isoformat()
    if raw is None or isinstance(raw, (str, int)):
        return raw
    raise TypeError(field)


def diff_plans(before: ScheduledPlan, after: ScheduledPlan) -> list[Change]:
    old = {t.id: t for t in before.tasks}
    new = {t.id: t for t in after.tasks}
    changes: list[Change] = []
    for task in after.tasks:
        prev = old.get(task.id)
        if prev is None:
            changes.append(
                Change(
                    task_id=task.id,
                    task_name=task.name,
                    field="created",
                    after=task.name,
                )
            )
            continue
        for field in _TRACKED:
            b, a = _value(prev, field), _value(task, field)
            if b != a:
                changes.append(
                    Change(
                        task_id=task.id,
                        task_name=task.name,
                        field=field,
                        before=b,
                        after=a,
                    )
                )
        pb = format_predecessors(before.dependencies, task.id)
        pa = format_predecessors(after.dependencies, task.id)
        if pb != pa:
            changes.append(
                Change(
                    task_id=task.id,
                    task_name=task.name,
                    field="predecessors",
                    before=pb,
                    after=pa,
                )
            )
    for task in before.tasks:
        if task.id not in new:
            changes.append(
                Change(
                    task_id=task.id,
                    task_name=task.name,
                    field="deleted",
                    before=task.name,
                )
            )
    return changes


def summarize_changes(changes: list[Change]) -> str:
    created = {c.task_id for c in changes if c.field == "created"}
    deleted = {c.task_id for c in changes if c.field == "deleted"}
    changed = {c.task_id for c in changes} - created - deleted
    if not changes:
        return "Без изменений"
    parts: list[str] = []
    for verb, ids in (("изменено", changed), ("добавлено", created), ("удалено", deleted)):
        if ids:
            # Only the leading part names the unit: "Добавлено задач: 1, удалено: 2".
            parts.append(f"{verb}{'' if parts else ' задач'}: {len(ids)}")
    text = ", ".join(parts)
    return text[0].upper() + text[1:]
