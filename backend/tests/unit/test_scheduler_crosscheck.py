"""Independent cross-check of the CPM scheduler against NetworkX (BSD-3, dev-only).

For ~200 random DAG plans (no constraints), we build a NetworkX DiGraph in
"workday index" space (source -> every task, weight 0; predecessor -> successor,
weight predecessor.duration + lag; every task -> sink, weight task.duration) and
compute, via Bellman-Ford longest paths (safe here: DAG, no negative cycles):

- earliest start of a task = longest path length from source to the task node
- "distance to completion" of a task = longest path length from the task node to
  the sink node; latest start = project_end_index - that distance
- project_end (exclusive workday index) = longest path length from source to sink

These are compared against our own `schedule()` (Kahn's algorithm + workday-date
arithmetic). A couple of hand-checked SNET-constraint cases are added separately,
since NetworkX does not model start-no-earlier-than constraints.
"""

import random
from datetime import date

import networkx as nx
import pytest

from app.domain.calendar import workday_diff
from app.domain.models import Dependency, Plan, Task
from app.domain.scheduler import schedule

PROJECT_START = date(2026, 9, 21)  # a Monday
assert PROJECT_START.weekday() == 0

SEED = 20260925
N_PLANS = 200


def _random_plan(rng: random.Random) -> Plan:
    n_tasks = rng.randint(5, 40)
    tasks = [
        Task(id=i, name=f"Задача {i}", duration=rng.randint(1, 10)) for i in range(1, n_tasks + 1)
    ]
    deps: list[Dependency] = []
    seen: set[tuple[int, int]] = set()
    # Only allow edges from a lower id to a higher id, so the plan is acyclic
    # by construction, then thin them out randomly.
    for i in range(1, n_tasks + 1):
        for j in range(i + 1, n_tasks + 1):
            if rng.random() < 0.12:
                key = (i, j)
                if key not in seen:
                    seen.add(key)
                    deps.append(Dependency(predecessor_id=i, successor_id=j, lag=rng.randint(0, 3)))
    return Plan(project_start=PROJECT_START, tasks=tasks, dependencies=deps)


def _networkx_cpm(plan: Plan) -> tuple[dict[int, int], dict[int, int], int]:
    """Return (earliest_start_index, latest_start_index, project_end_exclusive_index)."""
    by_id = {t.id: t for t in plan.tasks}
    g = nx.DiGraph()
    g.add_node("source")
    g.add_node("sink")
    for task in plan.tasks:
        g.add_node(task.id)
        g.add_edge("source", task.id, weight=0)
        g.add_edge(task.id, "sink", weight=task.duration)
    for d in plan.dependencies:
        g.add_edge(
            d.predecessor_id,
            d.successor_id,
            weight=by_id[d.predecessor_id].duration + d.lag,
        )

    # Longest path from source == shortest path with negated weights (safe: DAG).
    g_neg = nx.DiGraph()
    g_neg.add_nodes_from(g.nodes)
    for u, v, data in g.edges(data=True):
        g_neg.add_edge(u, v, weight=-data["weight"])
    dist_from_source = nx.single_source_bellman_ford_path_length(g_neg, "source", weight="weight")
    earliest = {tid: -dist_from_source[tid] for tid in by_id}
    project_end_exclusive = -dist_from_source["sink"]

    g_rev_neg = g_neg.reverse(copy=True)
    dist_from_sink = nx.single_source_bellman_ford_path_length(g_rev_neg, "sink", weight="weight")
    distance_to_sink = {tid: -dist_from_sink[tid] for tid in by_id}
    latest = {tid: project_end_exclusive - distance_to_sink[tid] for tid in by_id}

    return earliest, latest, project_end_exclusive


@pytest.mark.parametrize("plan_index", range(N_PLANS))
def test_scheduler_matches_networkx_cpm(plan_index: int) -> None:
    rng = random.Random(SEED + plan_index)
    plan = _random_plan(rng)
    sp = schedule(plan)
    earliest, latest, project_end_exclusive = _networkx_cpm(plan)

    for task in sp.tasks:
        our_start_idx = workday_diff(sp.project_start, task.start)
        our_end_idx = workday_diff(sp.project_start, task.end)
        assert our_start_idx == earliest[task.id], (plan_index, task.id)
        assert our_end_idx == earliest[task.id] + task.duration - 1, (plan_index, task.id)

        nx_slack = latest[task.id] - earliest[task.id]
        assert task.slack == nx_slack, (plan_index, task.id)
        assert task.is_critical == (task.slack == 0), (plan_index, task.id)

    our_end_idx = workday_diff(sp.project_start, sp.project_end)
    assert our_end_idx == project_end_exclusive - 1, plan_index


def test_snet_constraint_delays_start_hand_checked() -> None:
    # Task 1 has no predecessors but a constraint 5 workdays after project start;
    # NetworkX doesn't model SNET, so this is a plain hand-checked assertion.
    plan = Plan(
        project_start=PROJECT_START,
        tasks=[Task(id=1, name="A", duration=2, constraint_start=date(2026, 9, 28))],
    )
    sp = schedule(plan)
    constraint_idx = workday_diff(PROJECT_START, date(2026, 9, 28))
    start_idx = workday_diff(sp.project_start, sp.task(1).start)
    assert start_idx >= constraint_idx


def test_snet_constraint_with_predecessor_hand_checked() -> None:
    # Task 2 depends on task 1 (duration 3, no lag) AND has its own SNET
    # constraint two workdays after project start (weaker than the predecessor).
    plan = Plan(
        project_start=PROJECT_START,
        tasks=[
            Task(id=1, name="A", duration=3),
            Task(id=2, name="B", duration=1, constraint_start=date(2026, 9, 23)),
        ],
        dependencies=[Dependency(predecessor_id=1, successor_id=2)],
    )
    sp = schedule(plan)
    constraint_idx = workday_diff(PROJECT_START, date(2026, 9, 23))
    start_idx = workday_diff(sp.project_start, sp.task(2).start)
    assert start_idx >= constraint_idx
