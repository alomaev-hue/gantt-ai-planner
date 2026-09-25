from datetime import date

from app.domain.render import render_plan_table
from app.domain.scheduler import schedule
from app.domain.seed import build_demo_plan

TODAY = date(2026, 9, 25)  # Friday


def test_demo_plan_shape():
    plan = build_demo_plan(TODAY)
    sp = schedule(plan)
    assert plan.project_start == date(2026, 9, 7)  # Monday of the week of 2026-09-11
    assert 22 <= len(plan.tasks) <= 28
    assert len({t.assignee for t in plan.tasks}) == 6
    assert sp.critical_path, "demo must have a critical path"
    assert any(t.overallocated_with for t in sp.tasks), "demo must contain an overallocation"
    assert any(d.lag > 0 for d in plan.dependencies)
    assert sp.project_start <= TODAY <= sp.project_end
    assert all(t.description for t in plan.tasks)


def test_render_contains_header_rows_and_next_id():
    sp = schedule(build_demo_plan(TODAY))
    text = render_plan_table(sp, TODAY)
    assert "Сегодня: 2026-09-25" in text
    assert "Следующий свободный id: " + str(sp.last_id + 1) in text
    expected_header = (
        "id | задача | исполнитель | длит | предш | не раньше | начало | конец | резерв | флаги"
    )
    assert expected_header in text
    assert text.count("\n") >= len(sp.tasks) + 3
    assert "крит" in text and "перегруз" in text
