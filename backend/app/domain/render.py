from datetime import date

from app.domain.diff import format_predecessors
from app.domain.scheduler import ScheduledPlan


def _sanitize_cell(value: str) -> str:
    """Task names/assignees are free text and may themselves contain "|" or newlines; keep the
    rendered table at exactly 10 " | "-separated columns per row (both for the fake LLM's own
    parser and to keep the table unambiguous for a real model) by neutralizing the delimiter and
    collapsing any embedded whitespace, including newlines, to single spaces."""
    return " ".join(value.replace("|", "¦").split())


def render_plan_table(sp: ScheduledPlan, today: date) -> str:
    lines = [
        f"Сегодня: {today.isoformat()}. Старт проекта: {sp.project_start.isoformat()}. "
        f"Окончание: {sp.project_end.isoformat()}. Задач: {len(sp.tasks)}. "
        f"Следующий свободный id: {sp.last_id + 1}.",
        "Критический путь: " + (", ".join(map(str, sp.critical_path)) or "—"),
        "id | задача | исполнитель | длит | предш | не раньше | начало | конец | резерв | флаги",
    ]
    for t in sp.tasks:
        flags = []
        if t.is_critical:
            flags.append("крит")
        if t.overallocated_with:
            flags.append("перегруз(" + ",".join(map(str, t.overallocated_with)) + ")")
        lines.append(
            " | ".join(
                [
                    str(t.id),
                    _sanitize_cell(t.name),
                    _sanitize_cell(t.assignee) if t.assignee else "—",
                    str(t.duration),
                    format_predecessors(sp.dependencies, t.id) or "—",
                    t.constraint_start.isoformat() if t.constraint_start else "—",
                    t.start.isoformat(),
                    t.end.isoformat(),
                    str(t.slack),
                    " ".join(flags) or "—",
                ]
            )
        )
    return "\n".join(lines) + "\n"
