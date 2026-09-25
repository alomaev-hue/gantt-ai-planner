# Gantt AI Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web app with an interactive Gantt chart (seeded demo plan), Excel import/export, and a chat agent (Claude via MCP) that bulk-edits the plan with instant chart updates; deployed with Docker Compose behind Caddy.

**Architecture:** FastAPI monolith (single uvicorn worker) with a pure-Python domain core (`app/domain`, `app/excel`) that owns scheduling (CPM, FS+lag, Mon–Fri), atomic operations and diffs. `PlanService` is the only mutation path (UI, agent, external MCP). Plans are stored as JSONB snapshots per version in PostgreSQL 17. The chat agent calls tools through an in-process MCP client bound to a FastMCP server that is also exposed at `/mcp`. React 19 SPA (SVAR Gantt) is served by the same container; live updates via SSE.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2 (async, asyncpg), Alembic, openpyxl + defusedxml, anthropic SDK, FastMCP, sse-starlette, pytest; Node 20, Vite, React 19, TypeScript strict, Tailwind v4, shadcn/ui, TanStack Query, `@svar-ui/react-gantt` 2.7.3, vitest, Playwright; Docker, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-25-gantt-ai-planner-design.md` — read it before starting any task; section numbers below (§N) refer to it.

## Global Constraints

- Python `>=3.12,<3.13` (pinned via `uv python pin 3.12`); Node 20; npm (no pnpm/yarn).
- Code, identifiers, comments, commit messages: English. All user-facing strings (UI, API error messages, agent-facing tool errors, Excel headers): Russian.
- Conventional Commits; every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Repo root: `gantt-ai-planner/`. Backend in `backend/` (package `app`), frontend in `frontend/`, deploy assets in `deploy/`, scripts in `scripts/`.
- `app/domain` and `app/excel` are pure: no imports of FastAPI, SQLAlchemy, anthropic, MCP, or I/O except bytes in/out. mypy `--strict` must pass for these two packages.
- Limits (spec §4.1, §9): name 1..200, description 0..2000, assignee 0..100, duration 1..999 workdays, lag 0..365 workdays, max 500 tasks, xlsx ≤ 2 MB, ≤ 50 versions per session.
- Workdays Mon–Fri, no holidays; dates are date-only (no time, no TZ).
- Dependency type: FS only with non-negative lag.
- Task ids are stable ints; `Plan.last_id` guarantees ids are never reused.
- Chat rate limits: 30 user messages/hour/session, 500/day global; agent max 15 tool iterations/turn.
- LLM: `LLM_PROVIDER=anthropic|fake` (default `fake` when no key), `LLM_MODEL` default `claude-sonnet-5`, fallback `claude-haiku-4-5-20251001`.
- Never log prompts, plan contents, people names or request bodies.
- Line endings LF (`.gitattributes`: `* text=auto eol=lf`).

## Review Focus

1. Excel whose header row is not row 1 (title rows above), with blank/formatted-but-empty rows in the middle and at the end, and over-long names → header detected, blanks skipped, long text truncated with a warning (never a 500). Test lives in Task 5.
2. Predecessor cells that Excel stores as floats (`3.0`) or strings `"3.0"`, `"3;4"`, `"3FS+2"` → parsed as ids 3/4 with lag 2. Test lives in Task 5.
3. A single agent batch that adds a task and immediately references its (predicted) id in `add_dependency` → works because ids are `last_id+1, +2…` and the render shows the next free id. Test lives in Task 3 (+ render line in Task 4).
4. Weekend dates coming from the LLM, the modal, or Excel (`move_task` to a Saturday, project start on Sunday) → normalized to the next Monday, no error. Tests live in Tasks 2 and 3.
5. Browser holding a cookie for a deleted/expired session → API answers `401 no_session`, the frontend transparently calls `POST /api/session` and retries once; the UI never ends up blank. Tests live in Task 9 (API) and Task 12 (client).

---

## File Structure

```
gantt-ai-planner/
  .gitattributes .gitignore .editorconfig .env.example docker-compose.yml Dockerfile .dockerignore
  backend/
    pyproject.toml uv.lock alembic.ini
    app/
      __init__.py main.py config.py
      domain/   __init__.py errors.py models.py calendar.py scheduler.py operations.py diff.py seed.py render.py
      excel/    __init__.py headers.py parse.py export.py
      db/       __init__.py base.py models.py engine.py repo.py
      migrations/ env.py script.py.mako versions/0001_initial.py
      services/ __init__.py events.py locks.py plan_service.py ratelimit.py sessions.py
      mcp_server/ __init__.py context.py server.py client.py
      agent/    __init__.py llm.py fake.py prompt.py loop.py
      api/      __init__.py deps.py errors.py routes_session.py routes_plan.py routes_chat.py routes_events.py
    tests/
      unit/ test_calendar.py test_scheduler.py test_operations.py test_diff.py test_seed_render.py test_excel_parse.py test_excel_export.py test_fake_llm.py
      integration/ conftest.py test_repo.py test_plan_service.py test_api_plan.py test_api_import_export.py test_mcp_tools.py test_agent_turn.py test_api_chat_events.py
  frontend/
    package.json vite.config.ts tsconfig.json index.html components.json
    src/ main.tsx App.tsx index.css
         api/ client.ts types.ts chatStream.ts
         hooks/ usePlan.ts useSessionEvents.ts useChat.ts
         components/ Toolbar.tsx SplitLayout.tsx
                     gantt/ GanttView.tsx mapping.ts mapping.test.ts locale.ts gantt.css
                     chat/ ChatPanel.tsx MessageItem.tsx DiffSummary.tsx
                     task/ TaskModal.tsx
                     import/ ImportDialog.tsx
                     ui/ (shadcn generated)
         lib/ dates.ts dates.test.ts
    e2e/ playwright.config.ts main.spec.ts
  deploy/ compose.prod.yml initdb/10-roles.sh caddy/ bootstrap.sh planner-deploy planner-deploy-wrapper backup.sh
  scripts/ make_sample_excel.py record_demo.ts deploy-manual.sh
  examples/sample-plan.xlsx
  docs/ roadmap-to-production.md runbook.md ai-usage.md demo.gif demo.mp4
  .github/ workflows/ci.yml workflows/deploy.yml dependabot.yml
```

---

# PHASE 1 — Core + deploy-ready

### Task 1: Repository scaffold + workday calendar

**Files:**
- Create: `.gitattributes`, `.gitignore`, `.editorconfig`, `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/domain/__init__.py`, `backend/app/domain/calendar.py`, `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`
- Test: `backend/tests/unit/test_calendar.py`

**Interfaces:**
- Produces: `app.domain.calendar` with `is_workday(d) -> bool`, `next_workday(d) -> date`, `prev_workday(d) -> date`, `add_workdays(d, n: int) -> date` (n may be negative), `workday_diff(a, b) -> int` (signed; `add_workdays(a, workday_diff(a, b)) == b` for workdays a, b).

- [ ] **Step 1: Root files**

`.gitattributes`:
```
* text=auto eol=lf
*.xlsx binary
*.png binary
*.gif binary
*.mp4 binary
```

`.gitignore`:
```
.env
secrets/
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
node_modules/
frontend/dist/
frontend/test-results/
frontend/playwright-report/
*.log
.DS_Store
```

`.editorconfig`:
```
root = true
[*]
end_of_line = lf
insert_final_newline = true
charset = utf-8
indent_style = space
indent_size = 4
[*.{ts,tsx,js,json,yml,yaml,css,html,md}]
indent_size = 2
```

- [ ] **Step 2: Backend project**

Run (from `backend/`):
```bash
uv init --lib --name gantt-ai-planner --no-readme --vcs none .   # if it creates src/ layout, delete it; we use app/
uv python pin 3.12
uv add pydantic
uv add --dev pytest pytest-asyncio ruff mypy
```
Then make sure `pyproject.toml` contains (merge, keep uv-generated `[project]` deps):
```toml
[project]
name = "gantt-ai-planner"
version = "0.1.0"
requires-python = ">=3.12,<3.13"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
ignore = ["RUF001", "RUF002", "RUF003"]  # Cyrillic strings are intentional

[tool.mypy]
python_version = "3.12"
plugins = ["pydantic.mypy"]
warn_unused_ignores = true

[[tool.mypy.overrides]]
module = ["app.domain.*", "app.excel.*"]
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
testpaths = ["tests"]
```
Create empty `app/__init__.py`, `app/domain/__init__.py`, `tests/__init__.py`, `tests/unit/__init__.py`.

- [ ] **Step 3: Write the failing test** `backend/tests/unit/test_calendar.py`

```python
from datetime import date

from app.domain.calendar import add_workdays, is_workday, next_workday, prev_workday, workday_diff

MON = date(2026, 9, 21)
FRI = date(2026, 9, 25)
SAT = date(2026, 9, 26)
SUN = date(2026, 9, 27)
NEXT_MON = date(2026, 9, 28)


def test_is_workday():
    assert is_workday(MON) and is_workday(FRI)
    assert not is_workday(SAT) and not is_workday(SUN)


def test_next_and_prev_workday():
    assert next_workday(MON) == MON
    assert next_workday(SAT) == NEXT_MON
    assert next_workday(SUN) == NEXT_MON
    assert prev_workday(SAT) == FRI
    assert prev_workday(FRI) == FRI


def test_add_workdays_forward():
    assert add_workdays(MON, 0) == MON
    assert add_workdays(MON, 4) == FRI
    assert add_workdays(FRI, 1) == NEXT_MON
    assert add_workdays(MON, 5) == NEXT_MON
    assert add_workdays(MON, 10) == date(2026, 10, 5)
    assert add_workdays(SAT, 0) == NEXT_MON  # weekend normalizes forward


def test_add_workdays_backward():
    assert add_workdays(NEXT_MON, -1) == FRI
    assert add_workdays(NEXT_MON, -5) == MON
    assert add_workdays(FRI, -4) == MON


def test_workday_diff_is_inverse_of_add():
    start = MON
    for n in range(-15, 16):
        target = add_workdays(start, n)
        assert workday_diff(start, target) == n
    assert workday_diff(FRI, NEXT_MON) == 1
    assert workday_diff(NEXT_MON, FRI) == -1
```

- [ ] **Step 4: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_calendar.py -q`
Expected: FAIL (`ModuleNotFoundError: app.domain.calendar`).

- [ ] **Step 5: Implement** `backend/app/domain/calendar.py`

```python
"""Workday arithmetic: Monday–Friday are workdays, no holidays."""

from datetime import date, timedelta

_ONE_DAY = timedelta(days=1)


def is_workday(d: date) -> bool:
    return d.weekday() < 5


def next_workday(d: date) -> date:
    """Return d if it is a workday, otherwise the following Monday."""
    while not is_workday(d):
        d += _ONE_DAY
    return d


def prev_workday(d: date) -> date:
    """Return d if it is a workday, otherwise the preceding Friday."""
    while not is_workday(d):
        d -= _ONE_DAY
    return d


def add_workdays(d: date, n: int) -> date:
    """Move n workdays from d (backwards when n < 0). Weekend d is normalized first."""
    d = next_workday(d) if n >= 0 else prev_workday(d)
    step = _ONE_DAY if n >= 0 else -_ONE_DAY
    weeks, remaining = divmod(abs(n), 5)
    d += step * 7 * weeks
    while remaining:
        d += step
        if is_workday(d):
            remaining -= 1
    return d


def workday_diff(a: date, b: date) -> int:
    """Signed number of workdays needed to move from workday a to workday b."""
    if a == b:
        return 0
    sign = 1 if b > a else -1
    lo, hi = (a, b) if sign > 0 else (b, a)
    weeks, _ = divmod((hi - lo).days, 7)
    count = weeks * 5
    d = lo + timedelta(days=7 * weeks)
    while d < hi:
        d += _ONE_DAY
        if is_workday(d):
            count += 1
    return sign * count
```

- [ ] **Step 6: Verify**

Run: `cd backend && uv run pytest tests/unit/test_calendar.py -q && uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: all pass (run `uv run ruff format .` first if format-check complains).

- [ ] **Step 7: Commit**

```bash
git add .gitattributes .gitignore .editorconfig backend
git commit -m "chore: scaffold backend project and add workday calendar"
```

---

### Task 2: Domain models, validation, scheduler (CPM)

**Files:**
- Create: `backend/app/domain/errors.py`, `backend/app/domain/models.py`, `backend/app/domain/scheduler.py`
- Test: `backend/tests/unit/test_scheduler.py`

**Interfaces:**
- Consumes: `app.domain.calendar` (Task 1).
- Produces:
  - `errors.py`: `DomainError(message, *, details=None)` with `.code`, `.message`, `.details`; subclasses `PlanValidationError` (`code="invalid_plan"`), `CycleError(cycle: list[int])` (`code="cycle"`, subclass of PlanValidationError), `OperationError(message, *, index=None, details=None)` (`code="invalid_operation"`), `ConfirmationRequired` (`code="confirmation_required"`).
  - `models.py`: `MAX_TASKS = 500`; `Task(id, name, description="", assignee=None, duration, constraint_start=None)`; `Dependency(predecessor_id, successor_id, lag=0)` (frozen); `Plan(project_start, last_id=0, tasks=[], dependencies=[])` — `last_id` auto-raised to max task id.
  - `scheduler.py`: `ScheduledTask(Task)` + `start, end, slack, is_critical, constrained_by, overallocated_with`; `ScheduledPlan(project_start, project_end, last_id, tasks, dependencies, critical_path)` with `.task(id) -> ScheduledTask` and `.to_plan() -> Plan`; `validate_plan(plan) -> None`; `topological_order(plan) -> list[int]`; `schedule(plan) -> ScheduledPlan`.

- [ ] **Step 1: Write the failing test** `backend/tests/unit/test_scheduler.py`

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_scheduler.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** `backend/app/domain/errors.py`

```python
from typing import Any


class DomainError(Exception):
    code = "domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class PlanValidationError(DomainError):
    code = "invalid_plan"


class CycleError(PlanValidationError):
    code = "cycle"

    def __init__(self, cycle: list[int]) -> None:
        path = " → ".join(str(i) for i in [*cycle, cycle[0]])
        super().__init__(f"Циклическая зависимость: {path}", details={"cycle": cycle})
        self.cycle = cycle


class OperationError(DomainError):
    code = "invalid_operation"

    def __init__(
        self, message: str, *, index: int | None = None, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message, details=details)
        self.index = index


class ConfirmationRequired(DomainError):
    code = "confirmation_required"
```

- [ ] **Step 4: Implement** `backend/app/domain/models.py`

```python
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_TASKS = 500


class Task(BaseModel):
    id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    assignee: str | None = Field(default=None, max_length=100)
    duration: int = Field(ge=1, le=999)
    constraint_start: date | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("assignee", mode="before")
    @classmethod
    def _blank_assignee_is_none(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class Dependency(BaseModel):
    model_config = ConfigDict(frozen=True)

    predecessor_id: int
    successor_id: int
    lag: int = Field(default=0, ge=0, le=365)


class Plan(BaseModel):
    project_start: date
    last_id: int = Field(default=0, ge=0)
    tasks: list[Task] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_last_id(self) -> "Plan":
        max_id = max((t.id for t in self.tasks), default=0)
        if self.last_id < max_id:
            self.last_id = max_id
        return self
```

- [ ] **Step 5: Implement** `backend/app/domain/scheduler.py`

```python
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
    visited: set[int] = set()
    for root in sorted(nodes):
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

        if root not in visited and (cycle := dfs(root)):
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
```

- [ ] **Step 6: Verify**

Run: `cd backend && uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(domain): add plan models and CPM scheduler"
```

---

### Task 3: Operations (atomic batches) + diff

**Files:**
- Create: `backend/app/domain/operations.py`, `backend/app/domain/diff.py`
- Test: `backend/tests/unit/test_operations.py`, `backend/tests/unit/test_diff.py`

**Interfaces:**
- Consumes: Task 2 models/scheduler/errors.
- Produces:
  - `diff.py`: `Change(task_id: int, task_name: str, field: ChangeField, before: str | int | None, after: str | int | None)`; `ChangeField = Literal["created","deleted","name","description","assignee","duration","constraint_start","predecessors","start","end"]`; `format_predecessors(deps: list[Dependency], task_id: int) -> str` (e.g. `"3, 5+2"`); `diff_plans(before: ScheduledPlan, after: ScheduledPlan) -> list[Change]`; `summarize_changes(changes: list[Change]) -> str`.
  - `operations.py`: models `PredRef`, `AddTask`, `UpdateTask`, `MoveTask`, `ClearConstraint`, `SetDependencies`, `AddDependency`, `RemoveDependency`, `DeleteTask`, `SetProjectStart`; `Operation` (discriminated union on `op`); `operations_adapter: TypeAdapter[list[Operation]]`; `ApplyResult(plan, scheduled, changes, warnings, created_task_ids)`; `apply_operations(plan: Plan, ops: Sequence[Operation]) -> ApplyResult`; `requires_confirmation(plan: Plan, ops: Sequence[Operation]) -> bool`.

- [ ] **Step 1: Write failing tests** `backend/tests/unit/test_operations.py`

```python
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
    res = apply_operations(base_plan(), ops({"op": "move_task", "id": 4, "start_date": "2026-09-26"}))
    assert res.plan.tasks[3].constraint_start == date(2026, 9, 28)
    assert res.scheduled.task(4).start == date(2026, 9, 28)


def test_move_before_predecessor_warns():
    res = apply_operations(base_plan(), ops({"op": "move_task", "id": 2, "start_date": "2026-09-21"}))
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
    res = apply_operations(base_plan(), ops({"op": "add_task", "name": "X", "duration": 1, "after_id": 1}))
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
        apply_operations(base_plan(), ops({"op": "add_dependency", "predecessor_id": 3, "successor_id": 1}))
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
    assert not requires_confirmation(plan, ops({"op": "delete_task", "id": 1}, {"op": "delete_task", "id": 2}))
    assert requires_confirmation(
        plan, ops({"op": "delete_task", "id": 1}, {"op": "delete_task", "id": 2}, {"op": "delete_task", "id": 3})
    )
    big = Plan(project_start=MON, tasks=[Task(id=i, name=str(i), duration=1) for i in range(1, 21)])
    six = ops(*({"op": "delete_task", "id": i} for i in range(1, 7)))
    assert requires_confirmation(big, six)


def test_move_task_requires_exactly_one_target():
    with pytest.raises(ValueError):
        ops({"op": "move_task", "id": 1})
    with pytest.raises(ValueError):
        ops({"op": "move_task", "id": 1, "shift_days": 1, "start_date": "2026-09-22"})
```

`backend/tests/unit/test_diff.py`:
```python
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
        Plan(project_start=MON, tasks=[Task(id=1, name="A", duration=1), Task(id=2, name="B", duration=1)])
    )
    after = schedule(
        Plan(
            project_start=MON,
            tasks=[Task(id=1, name="A2", duration=2, assignee="Анна"), Task(id=3, name="C", duration=1)],
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_operations.py tests/unit/test_diff.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** `backend/app/domain/diff.py`

```python
from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.domain.models import Dependency
from app.domain.scheduler import ScheduledPlan, ScheduledTask

ChangeField = Literal[
    "created", "deleted", "name", "description", "assignee", "duration",
    "constraint_start", "predecessors", "start", "end",
]
_TRACKED: tuple[ChangeField, ...] = (
    "name", "description", "assignee", "duration", "constraint_start", "start", "end",
)


class Change(BaseModel):
    task_id: int
    task_name: str
    field: ChangeField
    before: str | int | None = None
    after: str | int | None = None


def format_predecessors(deps: list[Dependency], task_id: int) -> str:
    items = sorted((d for d in deps if d.successor_id == task_id), key=lambda d: d.predecessor_id)
    return ", ".join(f"{d.predecessor_id}+{d.lag}" if d.lag else str(d.predecessor_id) for d in items)


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
            changes.append(Change(task_id=task.id, task_name=task.name, field="created", after=task.name))
            continue
        for field in _TRACKED:
            b, a = _value(prev, field), _value(task, field)
            if b != a:
                changes.append(Change(task_id=task.id, task_name=task.name, field=field, before=b, after=a))
        pb = format_predecessors(before.dependencies, task.id)
        pa = format_predecessors(after.dependencies, task.id)
        if pb != pa:
            changes.append(
                Change(task_id=task.id, task_name=task.name, field="predecessors", before=pb, after=pa)
            )
    for task in before.tasks:
        if task.id not in new:
            changes.append(Change(task_id=task.id, task_name=task.name, field="deleted", before=task.name))
    return changes


def summarize_changes(changes: list[Change]) -> str:
    created = {c.task_id for c in changes if c.field == "created"}
    deleted = {c.task_id for c in changes if c.field == "deleted"}
    changed = {c.task_id for c in changes} - created - deleted
    if not changes:
        return "Без изменений"
    parts = [f"Изменено задач: {len(changed)}"]
    if created:
        parts.append(f"добавлено: {len(created)}")
    if deleted:
        parts.append(f"удалено: {len(deleted)}")
    return ", ".join(parts)
```

- [ ] **Step 4: Implement** `backend/app/domain/operations.py`

```python
"""Plan operations. A batch is applied to a copy and validated as a whole (atomic)."""

from collections.abc import Sequence
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, model_validator

from app.domain.calendar import add_workdays, next_workday
from app.domain.diff import Change, diff_plans
from app.domain.errors import OperationError, PlanValidationError
from app.domain.models import MAX_TASKS, Dependency, Plan, Task
from app.domain.scheduler import ScheduledPlan, schedule


class PredRef(BaseModel):
    id: int
    lag: int = Field(default=0, ge=0, le=365)


class AddTask(BaseModel):
    op: Literal["add_task"]
    name: str
    description: str = ""
    assignee: str | None = None
    duration: int = Field(ge=1, le=999)
    predecessors: list[PredRef] = Field(default_factory=list)
    after_id: int | None = None


class UpdateTask(BaseModel):
    op: Literal["update_task"]
    id: int
    name: str | None = None
    description: str | None = None
    assignee: str | None = None  # "" clears
    duration: int | None = Field(default=None, ge=1, le=999)


class MoveTask(BaseModel):
    op: Literal["move_task"]
    id: int
    start_date: date | None = None
    shift_days: int | None = Field(default=None, ge=-2000, le=2000)

    @model_validator(mode="after")
    def _exactly_one(self) -> "MoveTask":
        if (self.start_date is None) == (self.shift_days is None):
            raise ValueError("укажите ровно одно из полей start_date или shift_days")
        return self


class ClearConstraint(BaseModel):
    op: Literal["clear_constraint"]
    id: int


class SetDependencies(BaseModel):
    op: Literal["set_dependencies"]
    id: int
    predecessors: list[PredRef]


class AddDependency(BaseModel):
    op: Literal["add_dependency"]
    predecessor_id: int
    successor_id: int
    lag: int = Field(default=0, ge=0, le=365)


class RemoveDependency(BaseModel):
    op: Literal["remove_dependency"]
    predecessor_id: int
    successor_id: int


class DeleteTask(BaseModel):
    op: Literal["delete_task"]
    id: int


class SetProjectStart(BaseModel):
    op: Literal["set_project_start"]
    date: date


Operation = Annotated[
    AddTask | UpdateTask | MoveTask | ClearConstraint | SetDependencies | AddDependency
    | RemoveDependency | DeleteTask | SetProjectStart,
    Field(discriminator="op"),
]
operations_adapter: TypeAdapter[list[Operation]] = TypeAdapter(list[Operation])


class ApplyResult(BaseModel):
    plan: Plan
    scheduled: ScheduledPlan
    changes: list[Change]
    warnings: list[str]
    created_task_ids: list[int]


def requires_confirmation(plan: Plan, ops: Sequence[Operation]) -> bool:
    existing = {t.id for t in plan.tasks}
    deleted = {op.id for op in ops if isinstance(op, DeleteTask) and op.id in existing}
    return len(deleted) > 5 or (bool(existing) and len(deleted) * 2 > len(existing))


def apply_operations(plan: Plan, ops: Sequence[Operation]) -> ApplyResult:
    before = schedule(plan)
    work = plan.model_copy(deep=True)
    created: list[int] = []
    moved: list[int] = []
    for index, op in enumerate(ops):
        try:
            _apply_one(work, op, created, moved)
        except OperationError as exc:
            exc.index = index
            exc.message = f"Операция {index + 1} ({op.op}): {exc.message}"
            raise
        except (ValidationError, PlanValidationError, ValueError) as exc:
            raise OperationError(f"Операция {index + 1} ({op.op}): {_short(exc)}", index=index) from exc
    if len(work.tasks) > MAX_TASKS:
        raise OperationError(f"В плане не может быть больше {MAX_TASKS} задач")
    try:
        work = Plan.model_validate(work.model_dump())
        after = schedule(work)
    except PlanValidationError as exc:
        raise OperationError(exc.message, details=exc.details) from exc
    return ApplyResult(
        plan=work,
        scheduled=after,
        changes=diff_plans(before, after),
        warnings=_constraint_warnings(after, moved),
        created_task_ids=created,
    )


def _short(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    if isinstance(exc, PlanValidationError):
        return exc.message
    return str(exc)


def _get(plan: Plan, task_id: int) -> Task:
    for task in plan.tasks:
        if task.id == task_id:
            return task
    raise OperationError(f"задачи {task_id} нет в плане")


def _upsert_dep(plan: Plan, pred: int, succ: int, lag: int) -> None:
    if pred == succ:
        raise OperationError(f"задача {succ} не может зависеть от самой себя")
    for i, d in enumerate(plan.dependencies):
        if d.predecessor_id == pred and d.successor_id == succ:
            plan.dependencies[i] = Dependency(predecessor_id=pred, successor_id=succ, lag=max(lag, d.lag))
            return
    plan.dependencies.append(Dependency(predecessor_id=pred, successor_id=succ, lag=lag))


def _apply_one(plan: Plan, op: Operation, created: list[int], moved: list[int]) -> None:
    match op:
        case AddTask():
            new_id = plan.last_id + 1
            task = Task(
                id=new_id, name=op.name, description=op.description,
                assignee=op.assignee, duration=op.duration,
            )
            if op.after_id is not None:
                anchor = plan.tasks.index(_get(plan, op.after_id))
                plan.tasks.insert(anchor + 1, task)
            else:
                plan.tasks.append(task)
            plan.last_id = new_id
            for p in op.predecessors:
                _get(plan, p.id)
                _upsert_dep(plan, p.id, new_id, p.lag)
            created.append(new_id)
        case UpdateTask():
            task = _get(plan, op.id)
            data = task.model_dump()
            for field in op.model_fields_set - {"op", "id"}:
                data[field] = getattr(op, field)
            plan.tasks[plan.tasks.index(task)] = Task.model_validate(data)
        case MoveTask():
            task = _get(plan, op.id)
            if op.start_date is not None:
                target = op.start_date
            else:
                assert op.shift_days is not None
                target = add_workdays(schedule(plan).task(op.id).start, op.shift_days)
            task.constraint_start = next_workday(target)
            moved.append(op.id)
        case ClearConstraint():
            _get(plan, op.id).constraint_start = None
        case SetDependencies():
            _get(plan, op.id)
            plan.dependencies = [d for d in plan.dependencies if d.successor_id != op.id]
            for p in op.predecessors:
                _get(plan, p.id)
                _upsert_dep(plan, p.id, op.id, p.lag)
        case AddDependency():
            _get(plan, op.predecessor_id)
            _get(plan, op.successor_id)
            _upsert_dep(plan, op.predecessor_id, op.successor_id, op.lag)
        case RemoveDependency():
            before = len(plan.dependencies)
            plan.dependencies = [
                d for d in plan.dependencies
                if not (d.predecessor_id == op.predecessor_id and d.successor_id == op.successor_id)
            ]
            if len(plan.dependencies) == before:
                raise OperationError(f"связи {op.predecessor_id} → {op.successor_id} нет")
        case DeleteTask():
            task = _get(plan, op.id)
            incoming = [d for d in plan.dependencies if d.successor_id == op.id]
            outgoing = [d for d in plan.dependencies if d.predecessor_id == op.id]
            plan.dependencies = [
                d for d in plan.dependencies if op.id not in (d.predecessor_id, d.successor_id)
            ]
            plan.tasks.remove(task)
            for a in incoming:
                for b in outgoing:
                    _upsert_dep(plan, a.predecessor_id, b.successor_id, a.lag + b.lag)
        case SetProjectStart():
            plan.project_start = next_workday(op.date)


def _constraint_warnings(after: ScheduledPlan, moved: list[int]) -> list[str]:
    warnings: list[str] = []
    ids = {t.id for t in after.tasks}
    for tid in dict.fromkeys(moved):
        if tid not in ids:
            continue
        task = after.task(tid)
        if task.constraint_start is None:
            continue
        wanted = next_workday(task.constraint_start)
        if task.start <= wanted:
            continue
        if task.constrained_by.startswith("predecessor:"):
            pid = int(task.constrained_by.split(":")[1])
            why = f"ограничено предшественником {pid} «{after.task(pid).name}»"
        else:
            why = "ограничено датой старта проекта"
        warnings.append(
            f"Задача {tid} «{task.name}» не может начаться {wanted:%d.%m.%Y}: "
            f"начало {task.start:%d.%m.%Y}, {why}"
        )
    return warnings
```

Note for the implementer: `move_task` before the project start is also reported (the `else` branch). Keep the `assert` narrowing for mypy; the model validator guarantees it.

- [ ] **Step 5: Verify**

Run: `cd backend && uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(domain): add atomic plan operations and change diff"
```

---

### Task 4: Demo seed + compact plan rendering for the LLM

**Files:**
- Create: `backend/app/domain/seed.py`, `backend/app/domain/render.py`
- Test: `backend/tests/unit/test_seed_render.py`

**Interfaces:**
- Consumes: Tasks 2–3.
- Produces: `seed.build_demo_plan(today: date) -> Plan` (project_start = Monday of the week containing `today - 14 days`); `render.render_plan_table(sp: ScheduledPlan, today: date) -> str`.

- [ ] **Step 1: Write failing test** `backend/tests/unit/test_seed_render.py`

```python
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
    assert "id | задача | исполнитель | длит | предш | не раньше | начало | конец | резерв | флаги" in text
    assert text.count("\n") >= len(sp.tasks) + 3
    assert "крит" in text and "перегруз" in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_seed_render.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement** `backend/app/domain/seed.py`

```python
"""Demo plan: «Запуск MVP мобильного приложения». All people are fictional."""

from datetime import date, timedelta

from app.domain.models import Dependency, Plan, Task

ANNA, IGOR, MARIA = "Анна Смирнова", "Игорь Петров", "Мария Козлова"
DMITRY, OLGA, SERGEY = "Дмитрий Волков", "Ольга Никитина", "Сергей Орлов"

# (id, name, description, assignee, duration, predecessors[(id, lag)])
_TASKS: list[tuple[int, str, str, str, int, list[tuple[int, int]]]] = [
    (1, "Сбор требований и приоритизация", "Интервью со стейкхолдерами, бэклог MVP", ANNA, 3, []),
    (2, "Исследование пользователей", "10 интервью с целевой аудиторией, персоны", MARIA, 4, []),
    (3, "Архитектура бэкенда", "Схема сервисов, модель данных, выбор инфраструктуры", IGOR, 3, [(1, 0)]),
    (4, "Сценарии и wireframes", "Ключевые пользовательские потоки в низкой детализации", MARIA, 5, [(1, 0), (2, 0)]),
    (5, "UI-кит и дизайн-система", "Цвета, типографика, компоненты", MARIA, 4, [(4, 0)]),
    (6, "Макеты ключевых экранов", "Онбординг, каталог, корзина, профиль", MARIA, 6, [(5, 0)]),
    (7, "CI/CD и окружения", "Пайплайны сборки, stage и prod окружения", IGOR, 2, [(3, 0)]),
    (8, "API авторизации", "Регистрация, вход по телефону, токены", IGOR, 4, [(3, 0)]),
    (9, "API каталога и поиска", "Категории, карточки товаров, полнотекстовый поиск", IGOR, 6, [(8, 0)]),
    (10, "API заказов и оплаты", "Корзина, заказы, интеграция с эквайрингом", IGOR, 7, [(8, 0)]),
    (11, "Каркас мобильного приложения", "Навигация, сетевой слой, хранилище", DMITRY, 3, [(3, 0), (7, 0)]),
    (12, "Экраны онбординга и входа", "Верстка и интеграция с API авторизации", DMITRY, 4, [(6, 0), (8, 0)]),
    (13, "Экран каталога", "Список, фильтры, карточка товара", DMITRY, 5, [(6, 0), (9, 0)]),
    (14, "Корзина и оформление заказа", "Корзина, чекаут, оплата", DMITRY, 6, [(10, 0), (13, 0)]),
    (15, "Push-уведомления", "Подключение FCM/APNs, настройки уведомлений", DMITRY, 3, [(11, 0)]),
    (16, "Аналитика и трекинг событий", "SDK аналитики, схема событий воронки", DMITRY, 4, [(11, 0)]),
    (17, "Тест-план и тест-кейсы", "Покрытие ключевых сценариев", OLGA, 4, [(4, 0)]),
    (18, "Функциональное тестирование", "Регресс по тест-кейсам на iOS и Android", OLGA, 6, [(12, 0), (13, 0), (14, 0)]),
    (19, "Нагрузочное тестирование API", "Сценарии пиковой нагрузки, отчёт", OLGA, 3, [(9, 0), (10, 0)]),
    (20, "Исправление критичных багов", "Баги блокеры и критичные по итогам тестирования", IGOR, 4, [(18, 0), (19, 0)]),
    (21, "Лендинг и материалы для сторов", "Скриншоты, описание, лендинг", SERGEY, 5, [(6, 0)]),
    (22, "Маркетинговая кампания запуска", "Таргет, PR, рассылка по базе", SERGEY, 7, [(21, 0)]),
    (23, "Публикация в App Store и Google Play", "Сборки, заполнение карточек, отправка на ревью", DMITRY, 3, [(20, 0), (21, 0)]),
    (24, "Бета-тест с фокус-группой", "Закрытая бета на 50 пользователей", ANNA, 5, [(23, 2)]),
    (25, "Релиз и ретроспектива", "Публичный релиз, разбор итогов", ANNA, 2, [(22, 0), (24, 0)]),
]


def build_demo_plan(today: date) -> Plan:
    anchor = today - timedelta(days=14)
    project_start = anchor - timedelta(days=anchor.weekday())
    tasks = [
        Task(id=i, name=n, description=d, assignee=a, duration=dur)
        for i, n, d, a, dur, _ in _TASKS
    ]
    deps = [
        Dependency(predecessor_id=p, successor_id=i, lag=lag)
        for i, *_, preds in _TASKS
        for p, lag in preds
    ]
    return Plan(project_start=project_start, tasks=tasks, dependencies=deps)
```

- [ ] **Step 4: Implement** `backend/app/domain/render.py`

```python
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
    return "\n".join(lines)
```

- [ ] **Step 5: Verify**

Run: `cd backend && uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: all pass. If `test_demo_plan_shape` fails on the overallocation or "today inside project" asserts, adjust `_TASKS` durations (not the test) until it passes, keeping 6 people and ≥1 lag.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(domain): add demo seed plan and LLM plan rendering"
```

---

### Task 5: Excel import parser

**Files:**
- Create: `backend/app/excel/__init__.py`, `backend/app/excel/headers.py`, `backend/app/excel/parse.py`
- Test: `backend/tests/unit/test_excel_parse.py`

**Interfaces:**
- Consumes: Tasks 1–2 (`Plan`, `Task`, `Dependency`, `topological_order`, `CycleError`, `next_workday`, `MAX_TASKS`).
- Produces: `headers.COLUMN_SYNONYMS: dict[str, tuple[str, ...]]` with keys `number, name, description, assignee, duration, predecessors, constraint`; `parse.ImportIssue(row: int | None, message: str)`; `parse.ImportResult(ok: bool, plan: Plan | None, errors: list[ImportIssue], warnings: list[ImportIssue])`; `parse.parse_plan_xlsx(data: bytes, project_start: date) -> ImportResult`; `parse.parse_duration(value: object) -> tuple[int, str | None]` (raises `ValueError` if unparseable; second item is a warning message).

- [ ] **Step 1: Add dependencies**

Run: `cd backend && uv add openpyxl defusedxml && uv add --dev types-openpyxl`

- [ ] **Step 2: Write failing test** `backend/tests/unit/test_excel_parse.py`

```python
from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.excel.parse import parse_duration, parse_plan_xlsx

MON = date(2026, 9, 21)


def xlsx(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADER = ["Задача", "Описание", "Исполнитель", "Длительность", "Предшественники"]


@pytest.mark.parametrize(
    ("raw", "expected", "warns"),
    [
        (5, 5, False), (5.0, 5, False), ("5", 5, False), ("5д", 5, False), ("5 д.", 5, False),
        ("5 дн", 5, False), ("5 дней", 5, False), ("5d", 5, False), ("1 нед", 5, False),
        ("2w", 10, False), ("2,5", 3, True), (None, 1, True), (0, 1, True), ("", 1, True),
    ],
)
def test_parse_duration(raw, expected, warns):
    value, warning = parse_duration(raw)
    assert value == expected
    assert (warning is not None) == warns


def test_parse_duration_invalid():
    with pytest.raises(ValueError):
        parse_duration("долго")


def test_basic_import_by_row_order_and_names():
    data = xlsx(
        [
            HEADER,
            ["Анализ", "Сбор требований", "Анна", 3, None],
            ["Дизайн", "", "Мария", "5д", "1"],
            ["Разработка", None, "Игорь", "2 нед", "1; Дизайн+2"],
        ]
    )
    res = parse_plan_xlsx(data, MON)
    assert res.ok, res.errors
    plan = res.plan
    assert [t.id for t in plan.tasks] == [1, 2, 3]
    assert plan.tasks[2].duration == 10
    assert {(d.predecessor_id, d.successor_id, d.lag) for d in plan.dependencies} == {
        (1, 2, 0), (1, 3, 0), (2, 3, 2),
    }
    assert plan.project_start == MON


def test_header_not_on_first_row_blank_rows_and_long_text():
    data = xlsx(
        [
            ["План переезда офиса"],
            [],
            ["№", "Название", "Ответственный", "Дни", "Зависимости"],
            [10, "Упаковка", "Олег", 2, None],
            [None, None, None, None, None],
            [20, "Х" * 250, None, 1, 10.0],
            [],
        ]
    )
    res = parse_plan_xlsx(data, MON)
    assert res.ok, res.errors
    assert [t.id for t in res.plan.tasks] == [10, 20]
    assert len(res.plan.tasks[1].name) == 200
    assert any("обрезано" in w.message for w in res.warnings)
    assert res.plan.dependencies[0].predecessor_id == 10


@pytest.mark.parametrize("cell", [3.0, "3.0", "3FS+2", "3 + 2д"])
def test_numeric_predecessor_variants(cell):
    rows = [HEADER] + [[f"T{i}", "", None, 1, None] for i in range(1, 4)] + [["T4", "", None, 1, cell]]
    res = parse_plan_xlsx(xlsx(rows), MON)
    assert res.ok, res.errors
    dep = res.plan.dependencies[0]
    assert (dep.predecessor_id, dep.successor_id) == (3, 4)
    assert dep.lag == (2 if "+" in str(cell) else 0)


def test_constraint_column_and_weekend_project_start():
    data = xlsx(
        [
            HEADER + ["Не раньше"],
            ["A", "", None, 1, None, datetime(2026, 10, 5)],
            ["B", "", None, 1, None, "06.10.2026"],
        ]
    )
    res = parse_plan_xlsx(data, date(2026, 9, 27))  # Sunday
    assert res.ok, res.errors
    assert res.plan.project_start == date(2026, 9, 28)
    assert [t.constraint_start for t in res.plan.tasks] == [date(2026, 10, 5), date(2026, 10, 6)]


def test_errors_are_collected_with_rows():
    data = xlsx(
        [
            HEADER,
            ["A", "", None, 1, "5"],       # row 2: unknown ref
            ["", "", None, 1, None],        # row 3: empty name but other cells -> error
            ["C", "", None, "долго", None],  # row 4: bad duration
            ["D", "", None, 1, "D"],         # row 5: self reference
        ]
    )
    res = parse_plan_xlsx(data, MON)
    assert not res.ok and res.plan is None
    rows = {e.row for e in res.errors}
    assert {2, 3, 4, 5} <= rows


def test_ambiguous_name_and_cycle():
    ambiguous = xlsx([HEADER, ["A", "", None, 1, None], ["A", "", None, 1, None], ["B", "", None, 1, "A"]])
    res = parse_plan_xlsx(ambiguous, MON)
    assert not res.ok and any("укажите №" in e.message for e in res.errors)

    cycle = xlsx([HEADER, ["A", "", None, 1, "2"], ["B", "", None, 1, "1"]])
    res = parse_plan_xlsx(cycle, MON)
    assert not res.ok and any("Циклическая зависимость" in e.message for e in res.errors)


def test_missing_required_columns_and_empty_file():
    res = parse_plan_xlsx(xlsx([["Описание", "Исполнитель"], ["x", "y"]]), MON)
    assert not res.ok and "задача" in res.errors[0].message.lower()
    res = parse_plan_xlsx(xlsx([HEADER]), MON)
    assert not res.ok and "нет задач" in res.errors[0].message


def test_not_an_xlsx():
    res = parse_plan_xlsx(b"not a zip", MON)
    assert not res.ok and "xlsx" in res.errors[0].message


def test_duplicate_numbers_and_too_many_tasks():
    dup = xlsx([["№", *HEADER], [1, "A", "", None, 1, None], [1, "B", "", None, 1, None]])
    assert any("повторяется" in e.message for e in parse_plan_xlsx(dup, MON).errors)
    many = xlsx([HEADER] + [[f"T{i}", "", None, 1, None] for i in range(501)])
    assert any("500" in e.message for e in parse_plan_xlsx(many, MON).errors)
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_excel_parse.py -q` → FAIL (module missing).

- [ ] **Step 4: Implement** `backend/app/excel/headers.py`

```python
COLUMN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "number": ("№", "#", "id", "номер", "n"),
    "name": ("задача", "название", "наименование", "task", "name"),
    "description": ("описание", "description"),
    "assignee": ("исполнитель", "ответственный", "assignee", "owner", "resource"),
    "duration": ("длительность", "дни", "длительность (дн)", "duration", "days"),
    "predecessors": ("предшественники", "зависимости", "predecessors", "depends on"),
    "constraint": ("не раньше", "начать не раньше", "snet", "start no earlier than"),
}


def normalize_header(value: object) -> str:
    return " ".join(str(value).strip().casefold().split()) if value is not None else ""


def match_column(value: object) -> str | None:
    header = normalize_header(value)
    for key, names in COLUMN_SYNONYMS.items():
        if header in names:
            return key
    return None
```

- [ ] **Step 5: Implement** `backend/app/excel/parse.py`

```python
"""Tolerant .xlsx plan importer (spec §9.1). Collects all issues instead of failing fast."""

import math
import re
import zipfile
from datetime import date, datetime
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel

from app.domain.calendar import next_workday
from app.domain.errors import CycleError
from app.domain.models import MAX_TASKS, Dependency, Plan, Task
from app.domain.scheduler import topological_order
from app.excel.headers import match_column

LIMITS = {"name": 200, "description": 2000, "assignee": 100}
_DURATION_RE = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*(д|дн|дня|дней|день|d|day|days|н|нед|недел[яьи]|w|wk|week|weeks)?\.?$"
)
_NUM_REF_RE = re.compile(r"^(\d+)(?:[.,]0+)?\s*(?:fs|он)?\s*(?:\+\s*(\d+)\s*(?:д|дн|d)?\.?)?$")
_NAME_LAG_RE = re.compile(r"^(.*?)\s*\+\s*(\d+)\s*(?:д|дн|d)?\.?$")
_OTHER_TYPES_RE = re.compile(r"^\d+\s*(ss|ff|sf|нн|оо|но)\b")


class ImportIssue(BaseModel):
    row: int | None
    message: str


class ImportResult(BaseModel):
    ok: bool
    plan: Plan | None
    errors: list[ImportIssue]
    warnings: list[ImportIssue]


def parse_duration(value: object) -> tuple[int, str | None]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return 1, "длительность не указана, принята 1 день"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number, unit = float(value), None
    else:
        m = _DURATION_RE.match(str(value).strip().casefold())
        if not m:
            raise ValueError(f"не удалось распознать длительность «{value}»")
        number, unit = float(m.group(1).replace(",", ".")), m.group(2)
    if unit and unit[0] in ("н", "w"):
        number *= 5
    if number <= 0:
        return 1, "длительность 0, принята 1 день"
    days = math.ceil(number)
    warning = None if days == number else f"длительность {number:g} округлена до {days}"
    if days > 999:
        raise ValueError("длительность больше 999 дней")
    return days, warning


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _fail(errors: list[ImportIssue], warnings: list[ImportIssue]) -> ImportResult:
    return ImportResult(ok=False, plan=None, errors=errors, warnings=warnings)


def parse_plan_xlsx(data: bytes, project_start: date) -> ImportResult:
    errors: list[ImportIssue] = []
    warnings: list[ImportIssue] = []
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, InvalidFileException, KeyError, OSError, ValueError):
        return _fail([ImportIssue(row=None, message="Файл не является корректным .xlsx")], [])
    ws = wb.worksheets[0]
    rows = [(i, list(r)) for i, r in enumerate(ws.iter_rows(values_only=True), start=1)]
    wb.close()

    header_row: int | None = None
    columns: dict[str, int] = {}
    for row_no, values in rows[:30]:
        mapped = {key: idx for idx, v in enumerate(values) if (key := match_column(v))}
        if "name" in mapped:
            header_row, columns = row_no, mapped
            break
    if header_row is None or "duration" not in columns:
        missing = "«Задача»" if header_row is None else "«Длительность»"
        return _fail([ImportIssue(row=None, message=f"Не найдена обязательная колонка {missing}")], [])

    def cell(values: list[Any], key: str) -> Any:
        idx = columns.get(key)
        return values[idx] if idx is not None and idx < len(values) else None

    raw_tasks: list[dict[str, Any]] = []
    for row_no, values in rows:
        if row_no <= header_row or all(_text(v) == "" for v in values):
            continue
        name = _text(cell(values, "name"))
        if not name:
            errors.append(ImportIssue(row=row_no, message="Пустое название задачи"))
            continue
        item: dict[str, Any] = {"row": row_no, "name": name}
        for key in ("name", "description", "assignee"):
            text = name if key == "name" else _text(cell(values, key))
            if len(text) > LIMITS[key]:
                text = text[: LIMITS[key]]
                warnings.append(ImportIssue(row=row_no, message=f"Поле «{key}» обрезано до {LIMITS[key]} символов"))
            item[key] = text
        try:
            item["duration"], warn = parse_duration(cell(values, "duration"))
            if warn:
                warnings.append(ImportIssue(row=row_no, message=warn.capitalize()))
        except ValueError as exc:
            errors.append(ImportIssue(row=row_no, message=str(exc).capitalize()))
            continue
        item["number"] = cell(values, "number")
        item["preds"] = _text(cell(values, "predecessors"))
        raw_constraint = cell(values, "constraint")
        item["constraint"] = _as_date(raw_constraint) if _text(raw_constraint) else None
        if _text(raw_constraint) and item["constraint"] is None:
            warnings.append(ImportIssue(row=row_no, message=f"Дата «{raw_constraint}» не распознана и пропущена"))
        raw_tasks.append(item)

    if not raw_tasks and not errors:
        return _fail([ImportIssue(row=None, message="В файле нет задач")], warnings)
    if len(raw_tasks) > MAX_TASKS:
        return _fail([ImportIssue(row=None, message=f"Больше {MAX_TASKS} задач в файле")], warnings)

    # ids: from «№» column if present, else 1..n
    use_numbers = "number" in columns
    ids: dict[int, int] = {}  # row -> id
    seen: dict[int, int] = {}
    for position, item in enumerate(raw_tasks, start=1):
        if not use_numbers:
            ids[item["row"]] = position
            continue
        text = _text(item["number"])
        if not text.isdigit() or int(text) < 1:
            errors.append(ImportIssue(row=item["row"], message="«№» должен быть положительным целым числом"))
            continue
        number = int(text)
        if number in seen:
            errors.append(ImportIssue(row=item["row"], message=f"№ {number} повторяется (строка {seen[number]})"))
            continue
        seen[number] = item["row"]
        ids[item["row"]] = number

    by_position = {pos: ids.get(it["row"]) for pos, it in enumerate(raw_tasks, start=1)}
    by_name: dict[str, list[int]] = {}
    for it in raw_tasks:
        if it["row"] in ids:
            by_name.setdefault(it["name"].casefold(), []).append(ids[it["row"]])
    known_ids = set(ids.values())

    deps: dict[tuple[int, int], int] = {}
    for it in raw_tasks:
        row, succ = it["row"], ids.get(it["row"])
        if succ is None or not it["preds"]:
            continue
        for token in (t.strip() for t in re.split(r"[;,\n]", it["preds"]) if t.strip()):
            ref, lag = _resolve(token, use_numbers, by_position, by_name, known_ids)
            if isinstance(ref, str):
                errors.append(ImportIssue(row=row, message=ref))
                continue
            if ref == succ:
                errors.append(ImportIssue(row=row, message="Задача не может зависеть от самой себя"))
                continue
            deps[(ref, succ)] = max(lag, deps.get((ref, succ), 0))

    if errors:
        return _fail(errors, warnings)

    plan = Plan(
        project_start=next_workday(project_start),
        tasks=[
            Task(
                id=ids[it["row"]], name=it["name"], description=it["description"],
                assignee=it["assignee"] or None, duration=it["duration"],
                constraint_start=it["constraint"],
            )
            for it in raw_tasks
        ],
        dependencies=[Dependency(predecessor_id=p, successor_id=s, lag=lag) for (p, s), lag in deps.items()],
    )
    try:
        topological_order(plan)
    except CycleError as exc:
        rows_by_id = {v: k for k, v in ids.items()}
        rows = ", ".join(str(rows_by_id[i]) for i in exc.cycle)
        return _fail([ImportIssue(row=None, message=f"{exc.message} (строки {rows})")], warnings)
    return ImportResult(ok=True, plan=plan, errors=[], warnings=warnings)


def _resolve(
    token: str,
    use_numbers: bool,
    by_position: dict[int, int | None],
    by_name: dict[str, list[int]],
    known_ids: set[int],
) -> tuple[int | str, int]:
    low = token.casefold()
    if _OTHER_TYPES_RE.match(low):
        return "Поддерживается только тип связи «окончание–начало»", 0
    m = _NUM_REF_RE.match(low)
    if m:
        number, lag = int(m.group(1)), int(m.group(2) or 0)
        ref = number if use_numbers else by_position.get(number)
        if ref is None or ref not in known_ids:
            return f"Предшественник «{token}» не найден", 0
        return ref, lag
    name, lag = token, 0
    m = _NAME_LAG_RE.match(token)
    if m:
        name, lag = m.group(1), int(m.group(2))
    matches = by_name.get(name.strip().casefold(), [])
    if not matches:
        return f"Предшественник «{token}» не найден", 0
    if len(matches) > 1:
        return f"Название «{name}» встречается несколько раз — укажите №", 0
    return matches[0], lag
```

- [ ] **Step 6: Verify**

Run: `cd backend && uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: all pass. (`ruff format` may rewrap long lines — run it.)

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(excel): add tolerant xlsx plan importer"
```

---

### Task 6: Excel export + round-trip

**Files:**
- Create: `backend/app/excel/export.py`
- Test: `backend/tests/unit/test_excel_export.py`

**Interfaces:**
- Consumes: Tasks 2, 4, 5.
- Produces: `export.EXPORT_HEADERS: list[str]`; `export.export_plan_xlsx(sp: ScheduledPlan) -> bytes`.

- [ ] **Step 1: Write failing test** `backend/tests/unit/test_excel_export.py`

```python
from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from app.domain.operations import apply_operations, operations_adapter
from app.domain.scheduler import schedule
from app.domain.seed import build_demo_plan
from app.excel.export import EXPORT_HEADERS, export_plan_xlsx
from app.excel.parse import parse_plan_xlsx

TODAY = date(2026, 9, 25)


def test_export_layout():
    sp = schedule(build_demo_plan(TODAY))
    wb = load_workbook(BytesIO(export_plan_xlsx(sp)))
    ws = wb["План"]
    assert [c.value for c in ws[1]] == EXPORT_HEADERS
    assert ws.freeze_panes == "A2"
    assert ws.max_row == len(sp.tasks) + 1
    first = sp.tasks[0]
    row = [c.value for c in ws[2]]
    assert row[0] == first.id and row[1] == first.name
    assert row[7].date() == first.start and row[8].date() == first.end


def test_round_trip_preserves_plan_including_constraints_and_lags():
    plan = build_demo_plan(TODAY)
    res = apply_operations(
        plan,
        operations_adapter.validate_python(
            [
                {"op": "move_task", "id": 21, "start_date": "2026-10-12"},
                {"op": "delete_task", "id": 7},
            ]
        ),
    )
    sp = res.scheduled
    imported = parse_plan_xlsx(export_plan_xlsx(sp), sp.project_start)
    assert imported.ok, imported.errors
    p2 = imported.plan
    assert [t.model_dump() for t in p2.tasks] == [t.model_dump() for t in res.plan.tasks]
    key = lambda d: (d.predecessor_id, d.successor_id, d.lag)  # noqa: E731
    assert sorted(map(key, p2.dependencies)) == sorted(map(key, res.plan.dependencies))
    sp2 = schedule(p2)
    assert [(t.start, t.end) for t in sp2.tasks] == [(t.start, t.end) for t in sp.tasks]
```

- [ ] **Step 2: Run to verify it fails** → `uv run pytest tests/unit/test_excel_export.py -q` FAIL.

- [ ] **Step 3: Implement** `backend/app/excel/export.py`

```python
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.domain.diff import format_predecessors
from app.domain.scheduler import ScheduledPlan

EXPORT_HEADERS = [
    "№", "Задача", "Описание", "Исполнитель", "Длительность", "Предшественники",
    "Не раньше", "Начало", "Окончание", "Резерв", "Критическая",
]
_WIDTHS = [6, 40, 50, 22, 14, 18, 13, 13, 13, 9, 12]
_DATE_COLUMNS = (7, 8, 9)  # 1-based: «Не раньше», «Начало», «Окончание»


def export_plan_xlsx(sp: ScheduledPlan) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "План"
    ws.append(EXPORT_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for t in sp.tasks:
        ws.append(
            [
                t.id, t.name, t.description, t.assignee or "", t.duration,
                format_predecessors(sp.dependencies, t.id), t.constraint_start,
                t.start, t.end, t.slack, "да" if t.is_critical else "",
            ]
        )
    for row in ws.iter_rows(min_row=2):
        for col in _DATE_COLUMNS:
            row[col - 1].number_format = "DD.MM.YYYY"
    for i, width in enumerate(_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Verify**

Run: `cd backend && uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy app`
Expected: all pass. If the round-trip fails because `description` `""` vs `None` or constraint datetime vs date, fix the parser/exporter (not the test).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(excel): add plan export with lossless round-trip"
```

---
