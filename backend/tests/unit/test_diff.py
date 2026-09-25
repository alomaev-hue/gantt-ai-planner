from datetime import date

from app.domain.diff import diff_plans, format_predecessors, summarize_changes
from app.domain.models import Dependency, Plan, Task
from app.domain.scheduler import schedule

MON = date(2026, 9, 21)


def test_format_predecessors():
    deps = [
        Dependency(predecessor_id=5, successor_id=9, lag=2),
        Dependency(predecessor_id=3, successor_id=9),
        Dependency(predecessor_id=1, successor_id=2),
    ]
    assert format_predecessors(deps, 9) == "3, 5+2"
    assert format_predecessors(deps, 1) == ""


def test_diff_detects_created_deleted_and_field_changes():
    before = schedule(
        Plan(
            project_start=MON,
            tasks=[
                Task(id=1, name="A", duration=1),
                Task(id=2, name="B", duration=1),
            ],
        )
    )
    after = schedule(
        Plan(
            project_start=MON,
            tasks=[
                Task(id=1, name="A2", duration=2, assignee="Анна"),
                Task(id=3, name="C", duration=1),
            ],
            dependencies=[Dependency(predecessor_id=1, successor_id=3)],
        )
    )
    changes = diff_plans(before, after)
    as_tuples = {(c.task_id, c.field, c.before, c.after) for c in changes}
    assert (1, "name", "A", "A2") in as_tuples
    assert (1, "duration", 1, 2) in as_tuples
    assert (1, "assignee", None, "Анна") in as_tuples
    assert (1, "end", "2026-09-21", "2026-09-22") in as_tuples
    assert (3, "created", None, "C") in as_tuples
    assert (2, "deleted", "B", None) in as_tuples
    assert summarize_changes(changes) == "Изменено задач: 1, добавлено: 1, удалено: 1"


def test_summary_without_changes():
    assert summarize_changes([]) == "Без изменений"
