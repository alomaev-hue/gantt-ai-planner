from datetime import date

from app.domain.diff import format_predecessors
from app.domain.scheduler import ScheduledPlan


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
                    t.name,
                    t.assignee or "—",
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
