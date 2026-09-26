from datetime import date

import pytest

from app.domain.errors import CycleError, PlanValidationError
from app.domain.models import Dependency, Plan, Task
from app.domain.scheduler import schedule, topological_order

MON = date(2026, 9, 21)


def t(id: int, dur: int, assignee: str | None = None, **kw: object) -> Task:
    return Task(id=id, name=f"Задача {id}", duration=dur, assignee=assignee, **kw)


def dep(p: int, s: int, lag: int = 0) -> Dependency:
    return Dependency(predecessor_id=p, successor_id=s, lag=lag)


def test_single_task_starts_at_project_start():
    sp = schedule(Plan(project_start=MON, tasks=[t(1, 3)]))
    task = sp.task(1)
    assert (task.start, task.end) == (MON, date(2026, 9, 23))
    assert sp.project_end == date(2026, 9, 23)
    assert task.constrained_by == "project_start"


def test_project_start_on_weekend_is_normalized():
    sp = schedule(Plan(project_start=date(2026, 9, 27), tasks=[t(1, 1)]))  # Sunday
    assert sp.project_start == date(2026, 9, 28)
    assert sp.task(1).start == date(2026, 9, 28)


def test_fs_dependency_with_lag_skips_weekend():
    plan = Plan(project_start=MON, tasks=[t(1, 5), t(2, 2)], dependencies=[dep(1, 2, lag=1)])
    sp = schedule(plan)
    assert sp.task(1).end == date(2026, 9, 25)  # Fri
    assert sp.task(2).start == date(2026, 9, 29)  # Mon +1 lag -> Tue
    assert sp.task(2).constrained_by == "predecessor:1"


def test_constraint_delays_task_and_is_normalized():
    plan = Plan(project_start=MON, tasks=[t(1, 2, constraint_start=date(2026, 9, 26))])  # Saturday
    task = schedule(plan).task(1)
    assert task.start == date(2026, 9, 28)
    assert task.constrained_by == "constraint"


def test_constraint_earlier_than_predecessor_is_ignored():
    plan = Plan(
        project_start=MON,
        tasks=[t(1, 5), t(2, 1, constraint_start=MON)],
        dependencies=[dep(1, 2)],
    )
    assert schedule(plan).task(2).start == date(2026, 9, 28)


def test_critical_path_and_slack():
    # 1(3) -> 3(2); 2(1) -> 3 ; 2 has slack 2
    plan = Plan(
        project_start=MON,
        tasks=[t(1, 3), t(2, 1), t(3, 2)],
        dependencies=[dep(1, 3), dep(2, 3)],
    )
    sp = schedule(plan)
    assert sp.task(1).is_critical and sp.task(3).is_critical
    assert not sp.task(2).is_critical
    assert sp.task(2).slack == 2
    assert sp.critical_path == [1, 3]


def test_overallocation_detected_for_same_assignee_overlap():
    plan = Plan(
        project_start=MON,
        tasks=[t(1, 3, "Анна"), t(2, 2, "анна "), t(3, 2, "Игорь"), t(4, 1, "Анна")],
        dependencies=[dep(1, 4)],
    )
    sp = schedule(plan)
    assert sp.task(1).overallocated_with == [2]
    assert sp.task(2).overallocated_with == [1]
    assert sp.task(3).overallocated_with == []
    assert sp.task(4).overallocated_with == []  # starts after 1 ends, after 2 ends


def test_cycle_detected():
    plan = Plan(
        project_start=MON,
        tasks=[t(1, 1), t(2, 1), t(3, 1)],
        dependencies=[dep(1, 2), dep(2, 3), dep(3, 1)],
    )
    with pytest.raises(CycleError) as exc:
        topological_order(plan)
    assert sorted(exc.value.cycle) == [1, 2, 3]
    assert "Циклическая зависимость" in exc.value.message


@pytest.mark.parametrize(
    ("tasks", "deps", "fragment"),
    [
        ([t(1, 1), t(1, 2)], [], "повторяется"),
        ([t(1, 1)], [dep(1, 9)], "не существует"),
        ([t(1, 1)], [dep(1, 1)], "самой себя"),
        ([t(1, 1), t(2, 1)], [dep(1, 2), dep(1, 2, 3)], "дублируется"),
    ],
)
def test_validation_errors(tasks, deps, fragment):
    with pytest.raises(PlanValidationError) as exc:
        schedule(Plan(project_start=MON, tasks=tasks, dependencies=deps))
    assert fragment in exc.value.message


def test_last_id_never_below_max_id_and_empty_plan():
    assert Plan(project_start=MON, tasks=[t(7, 1)]).last_id == 7
    assert Plan(project_start=MON, last_id=10, tasks=[t(7, 1)]).last_id == 10
    sp = schedule(Plan(project_start=MON))
    assert sp.tasks == [] and sp.project_end == MON


def test_assignee_blank_becomes_none_and_to_plan_roundtrip():
    plan = Plan(project_start=MON, tasks=[t(1, 1, "  ")])
    assert plan.tasks[0].assignee is None
    assert schedule(plan).to_plan() == plan
