from datetime import date

import pytest

from app.domain.errors import OperationError
from app.domain.models import Dependency, Plan, Task
from app.domain.operations import apply_operations, operations_adapter, requires_confirmation

MON = date(2026, 9, 21)


def base_plan() -> Plan:
    # 1(3d) -> 2(2d) -> 3(1d); 4 independent
    return Plan(
        project_start=MON,
        tasks=[
            Task(id=1, name="Анализ", duration=3, assignee="Анна"),
            Task(id=2, name="Разработка", duration=2, assignee="Игорь"),
            Task(id=3, name="Тест", duration=1, assignee="Ольга"),
            Task(id=4, name="Маркетинг", duration=2),
        ],
        dependencies=[
            Dependency(predecessor_id=1, successor_id=2),
            Dependency(predecessor_id=2, successor_id=3),
        ],
    )


def ops(*raw: dict) -> list:
    return operations_adapter.validate_python(list(raw))


def test_move_task_by_shift_cascades_to_successors():
    res = apply_operations(base_plan(), ops({"op": "move_task", "id": 1, "shift_days": 2}))
    assert res.scheduled.task(1).start == date(2026, 9, 23)
    assert res.scheduled.task(3).start == date(2026, 9, 30)
    fields = {(c.task_id, c.field) for c in res.changes}
    assert {(1, "constraint_start"), (1, "start"), (2, "start"), (3, "start")} <= fields


def test_move_task_to_saturday_is_normalized_to_monday():
    res = apply_operations(
        base_plan(),
        ops({"op": "move_task", "id": 4, "start_date": "2026-09-26"}),
    )
    assert res.plan.tasks[3].constraint_start == date(2026, 9, 28)
    assert res.scheduled.task(4).start == date(2026, 9, 28)


def test_move_before_predecessor_warns():
    res = apply_operations(
        base_plan(),
        ops({"op": "move_task", "id": 2, "start_date": "2026-09-21"}),
    )
    assert res.scheduled.task(2).start == date(2026, 9, 24)
    assert any("ограничено предшественником 1" in w for w in res.warnings)


def test_add_task_then_reference_predicted_id_in_same_batch():
    res = apply_operations(
        base_plan(),
        ops(
            {"op": "add_task", "name": "Документация", "duration": 2, "predecessors": [{"id": 3}]},
            {"op": "add_dependency", "predecessor_id": 5, "successor_id": 4, "lag": 1},
        ),
    )
    assert res.created_task_ids == [5]
    assert res.scheduled.task(5).start == date(2026, 9, 29)
    assert res.scheduled.task(4).start == add_expected(res.scheduled.task(5).end, 2)


def add_expected(d: date, n: int) -> date:
    from app.domain.calendar import add_workdays

    return add_workdays(d, n)


def test_add_task_after_id_inserts_in_order():
    res = apply_operations(
        base_plan(),
        ops({"op": "add_task", "name": "X", "duration": 1, "after_id": 1}),
    )
    assert [t.id for t in res.plan.tasks] == [1, 5, 2, 3, 4]


def test_update_task_reassign_and_clear_assignee():
    res = apply_operations(
        base_plan(),
        ops(
            {"op": "update_task", "id": 2, "assignee": "Мария", "duration": 4},
            {"op": "update_task", "id": 3, "assignee": ""},
        ),
    )
    assert res.plan.tasks[1].assignee == "Мария" and res.plan.tasks[1].duration == 4
    assert res.plan.tasks[2].assignee is None


def test_set_and_remove_dependencies():
    res = apply_operations(
        base_plan(),
        ops(
            {"op": "set_dependencies", "id": 3, "predecessors": [{"id": 4, "lag": 1}]},
            {"op": "remove_dependency", "predecessor_id": 1, "successor_id": 2},
        ),
    )
    pairs = {(d.predecessor_id, d.successor_id, d.lag) for d in res.plan.dependencies}
    assert pairs == {(4, 3, 1)}


def test_delete_task_bridges_dependencies():
    plan = base_plan()
    plan.dependencies = [
        Dependency(predecessor_id=1, successor_id=2, lag=1),
        Dependency(predecessor_id=2, successor_id=3, lag=2),
    ]
    res = apply_operations(plan, ops({"op": "delete_task", "id": 2}))
    assert [t.id for t in res.plan.tasks] == [1, 3, 4]
    assert [(d.predecessor_id, d.successor_id, d.lag) for d in res.plan.dependencies] == [(1, 3, 3)]
    assert any(c.field == "deleted" and c.task_id == 2 for c in res.changes)


def test_deleted_ids_are_never_reused():
    res = apply_operations(base_plan(), ops({"op": "delete_task", "id": 4}))
    res2 = apply_operations(res.plan, ops({"op": "add_task", "name": "Новая", "duration": 1}))
    assert res2.created_task_ids == [5]


def test_batch_is_atomic_on_error():
    plan = base_plan()
    with pytest.raises(OperationError) as exc:
        apply_operations(
            plan,
            ops(
                {"op": "update_task", "id": 1, "name": "Переименовано"},
                {"op": "update_task", "id": 99, "name": "Нет такой"},
            ),
        )
    assert exc.value.index == 1
    assert "99" in exc.value.message
    assert plan.tasks[0].name == "Анализ"  # input untouched


def test_cycle_is_rejected():
    with pytest.raises(OperationError) as exc:
        apply_operations(
            base_plan(),
            ops(
                {
                    "op": "add_dependency",
                    "predecessor_id": 3,
                    "successor_id": 1,
                }
            ),
        )
    assert "Циклическая зависимость" in exc.value.message


def test_set_project_start_and_clear_constraint():
    plan = base_plan()
    plan.tasks[3].constraint_start = date(2026, 10, 5)
    res = apply_operations(
        plan,
        ops({"op": "set_project_start", "date": "2026-10-04"}, {"op": "clear_constraint", "id": 4}),
    )
    assert res.plan.project_start == date(2026, 10, 5)
    assert res.plan.tasks[3].constraint_start is None


def test_invalid_field_values_become_operation_error():
    with pytest.raises(OperationError):
        apply_operations(base_plan(), ops({"op": "update_task", "id": 1, "name": ""}))


def test_requires_confirmation_thresholds():
    plan = base_plan()  # 4 tasks
    assert not requires_confirmation(plan, ops({"op": "delete_task", "id": 1}))
    assert not requires_confirmation(
        plan, ops({"op": "delete_task", "id": 1}, {"op": "delete_task", "id": 2})
    )
    assert requires_confirmation(
        plan,
        ops(
            {"op": "delete_task", "id": 1},
            {"op": "delete_task", "id": 2},
            {"op": "delete_task", "id": 3},
        ),
    )
    big = Plan(
        project_start=MON,
        tasks=[Task(id=i, name=str(i), duration=1) for i in range(1, 21)],
    )
    six = ops(*({"op": "delete_task", "id": i} for i in range(1, 7)))
    assert requires_confirmation(big, six)


def test_move_task_requires_exactly_one_target():
    with pytest.raises(ValueError):
        ops({"op": "move_task", "id": 1})
    with pytest.raises(ValueError):
        ops({"op": "move_task", "id": 1, "shift_days": 1, "start_date": "2026-09-22"})


def test_shifting_predecessor_and_successor_moves_each_exactly_once():
    # Chain 1 -> 2 -> 3, every task shifted +3 in one batch: each must start exactly 3 workdays
    # later than before the batch (the successor must not also inherit its predecessor's shift).
    before = apply_operations(base_plan(), []).scheduled
    res = apply_operations(
        base_plan(),
        ops(*({"op": "move_task", "id": i, "shift_days": 3} for i in (1, 2, 3))),
    )
    for tid in (1, 2, 3):
        assert res.scheduled.task(tid).start == add_expected(before.task(tid).start, 3), tid
    assert res.scheduled.project_end == add_expected(before.project_end, 3)


def test_shift_order_does_not_matter_within_a_batch():
    forward = apply_operations(
        base_plan(), ops(*({"op": "move_task", "id": i, "shift_days": 2} for i in (1, 2)))
    )
    backward = apply_operations(
        base_plan(), ops(*({"op": "move_task", "id": i, "shift_days": 2} for i in (2, 1)))
    )
    assert [t.start for t in forward.scheduled.tasks] == [t.start for t in backward.scheduled.tasks]


def test_repeated_shift_of_one_task_accumulates():
    before = apply_operations(base_plan(), []).scheduled
    res = apply_operations(
        base_plan(),
        ops(
            {"op": "move_task", "id": 4, "shift_days": 2},
            {"op": "move_task", "id": 4, "shift_days": 1},
        ),
    )
    assert res.scheduled.task(4).start == add_expected(before.task(4).start, 3)


def test_shift_of_task_created_in_same_batch_uses_its_scheduled_start():
    res = apply_operations(
        base_plan(),
        ops(
            {"op": "add_task", "name": "Новая", "duration": 1, "predecessors": [{"id": 3}]},
            {"op": "move_task", "id": 5, "shift_days": 2},
        ),
    )
    first_free_day = add_expected(res.scheduled.task(3).end, 1)
    assert res.scheduled.task(5).start == add_expected(first_free_day, 2)


def test_batch_size_is_capped():
    from app.domain.operations import MAX_BATCH_OPS

    assert MAX_BATCH_OPS == 200
    at_cap = ops(*({"op": "update_task", "id": 4, "duration": 2} for _ in range(MAX_BATCH_OPS)))
    apply_operations(base_plan(), at_cap)
    over = ops(*({"op": "update_task", "id": 4, "duration": 2} for _ in range(MAX_BATCH_OPS + 1)))
    with pytest.raises(OperationError) as exc:
        apply_operations(base_plan(), over)
    assert "не больше 200 операций" in exc.value.message
