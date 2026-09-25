"""CPM scheduling: forward pass (early dates), backward pass (slack), overallocation."""

from collections import defaultdict
from datetime import date

from pydantic import BaseModel, Field

from app.domain.calendar import add_workdays, next_workday, workday_diff
from app.domain.errors import CycleError, PlanValidationError
from app.domain.models import Dependency, Plan, Task


class ScheduledTask(Task):
    start: date
    end: date
    slack: int
    is_critical: bool
    constrained_by: str  # "project_start" | "constraint" | "predecessor:<id>"
    overallocated_with: list[int] = Field(default_factory=list)


class ScheduledPlan(BaseModel):
    project_start: date
    project_end: date
    last_id: int
    tasks: list[ScheduledTask]
    dependencies: list[Dependency]
    critical_path: list[int]

    def task(self, task_id: int) -> ScheduledTask:
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    def to_plan(self) -> Plan:
        fields = set(Task.model_fields)
        return Plan(
            project_start=self.project_start,
            last_id=self.last_id,
            tasks=[Task(**t.model_dump(include=fields)) for t in self.tasks],
            dependencies=list(self.dependencies),
        )


def validate_plan(plan: Plan) -> None:
    ids: set[int] = set()
    for task in plan.tasks:
        if task.id in ids:
            raise PlanValidationError(f"№ {task.id} повторяется")
        ids.add(task.id)
    seen: set[tuple[int, int]] = set()
    for d in plan.dependencies:
        for ref in (d.predecessor_id, d.successor_id):
            if ref not in ids:
                raise PlanValidationError(f"Задача {ref} не существует")
        if d.predecessor_id == d.successor_id:
            raise PlanValidationError(f"Задача {d.successor_id} не может зависеть от самой себя")
        key = (d.predecessor_id, d.successor_id)
        if key in seen:
            raise PlanValidationError(f"Связь {key[0]} → {key[1]} дублируется")
        seen.add(key)


def topological_order(plan: Plan) -> list[int]:
    """Kahn's algorithm; ties keep the task-list order. Raises CycleError."""
    succs: dict[int, list[int]] = defaultdict(list)
    indegree = {t.id: 0 for t in plan.tasks}
    for d in plan.dependencies:
        succs[d.predecessor_id].append(d.successor_id)
        indegree[d.successor_id] += 1
    position = {t.id: i for i, t in enumerate(plan.tasks)}
    ready = sorted((tid for tid, deg in indegree.items() if deg == 0), key=position.__getitem__)
    order: list[int] = []
    while ready:
        tid = ready.pop(0)
        order.append(tid)
        for s in succs[tid]:
            indegree[s] -= 1
            if indegree[s] == 0:
                ready.append(s)
                ready.sort(key=position.__getitem__)
    if len(order) != len(indegree):
        remaining = {tid for tid, deg in indegree.items() if deg > 0}
        raise CycleError(_find_cycle(remaining, succs))
    return order


def _find_cycle(nodes: set[int], succs: dict[int, list[int]]) -> list[int]:
    def _build_dfs_for_root(root: int) -> tuple[list[int] | None, set[int]]:
        visited: set[int] = set()
        stack: list[int] = []
        on_stack: set[int] = set()

        def dfs(node: int) -> list[int] | None:
            visited.add(node)
            stack.append(node)
            on_stack.add(node)
            for nxt in succs.get(node, []):
                if nxt not in nodes:
                    continue
                if nxt in on_stack:
                    return stack[stack.index(nxt) :]
                if nxt not in visited and (found := dfs(nxt)):
                    return found
            stack.pop()
            on_stack.discard(node)
            return None

        return dfs(root), visited

    visited_global: set[int] = set()
    for root in sorted(nodes):
        if root not in visited_global:
            cycle, visited = _build_dfs_for_root(root)
            visited_global.update(visited)
            if cycle:
                return cycle
    return sorted(nodes)


def schedule(plan: Plan) -> ScheduledPlan:
    validate_plan(plan)
    order = topological_order(plan)
    by_id = {t.id: t for t in plan.tasks}
    preds: dict[int, list[Dependency]] = defaultdict(list)
    succs: dict[int, list[Dependency]] = defaultdict(list)
    for d in plan.dependencies:
        preds[d.successor_id].append(d)
        succs[d.predecessor_id].append(d)

    project_start = next_workday(plan.project_start)
    start: dict[int, date] = {}
    end: dict[int, date] = {}
    reason: dict[int, str] = {}
    for tid in order:
        task = by_id[tid]
        es, why = project_start, "project_start"
        if task.constraint_start is not None:
            c = next_workday(task.constraint_start)
            if c > es:
                es, why = c, "constraint"
        for d in preds[tid]:
            candidate = add_workdays(end[d.predecessor_id], 1 + d.lag)
            if candidate > es:
                es, why = candidate, f"predecessor:{d.predecessor_id}"
        start[tid], end[tid], reason[tid] = es, add_workdays(es, task.duration - 1), why

    project_end = max(end.values(), default=project_start)
    late_start: dict[int, date] = {}
    for tid in reversed(order):
        lf = project_end
        for d in succs[tid]:
            candidate = add_workdays(late_start[d.successor_id], -(1 + d.lag))
            if candidate < lf:
                lf = candidate
        late_start[tid] = add_workdays(lf, -(by_id[tid].duration - 1))

    overlaps = _overallocations(plan.tasks, start, end)
    tasks: list[ScheduledTask] = []
    for task in plan.tasks:
        slack = max(0, workday_diff(start[task.id], late_start[task.id]))
        tasks.append(
            ScheduledTask(
                **task.model_dump(),
                start=start[task.id],
                end=end[task.id],
                slack=slack,
                is_critical=slack == 0,
                constrained_by=reason[task.id],
                overallocated_with=sorted(overlaps[task.id]),
            )
        )
    critical = sorted((t for t in tasks if t.is_critical), key=lambda t: (t.start, t.id))
    return ScheduledPlan(
        project_start=project_start,
        project_end=project_end,
        last_id=plan.last_id,
        tasks=tasks,
        dependencies=list(plan.dependencies),
        critical_path=[t.id for t in critical],
    )


def _overallocations(
    tasks: list[Task], start: dict[int, date], end: dict[int, date]
) -> dict[int, set[int]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for task in tasks:
        if task.assignee:
            groups[task.assignee.strip().casefold()].append(task.id)
    result: dict[int, set[int]] = defaultdict(set)
    for ids in groups.values():
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                if start[a] <= end[b] and start[b] <= end[a]:
                    result[a].add(b)
                    result[b].add(a)
    return result
