from typing import Literal

from pydantic import BaseModel

from app.domain.diff import Change
from app.domain.operations import Operation
from app.domain.scheduler import ScheduledPlan
from app.excel.parse import ImportIssue
from app.services.plan_service import PlanState


class PlanResponse(BaseModel):
    version: int
    can_undo: bool
    can_redo: bool
    agent_busy: bool
    plan: ScheduledPlan


class ApplyRequest(BaseModel):
    ops: list[Operation]


class ApplyResponse(PlanResponse):
    changes: list[Change]
    warnings: list[str]
    summary: str
    created_task_ids: list[int]


class ImportSuccess(BaseModel):
    ok: Literal[True]
    plan: PlanResponse
    warnings: list[ImportIssue]


class ImportFailure(BaseModel):
    ok: Literal[False]
    errors: list[ImportIssue]
    warnings: list[ImportIssue]


def to_plan_response(state: PlanState, busy: bool) -> PlanResponse:
    return PlanResponse(
        version=state.version,
        can_undo=state.can_undo,
        can_redo=state.can_redo,
        agent_busy=busy,
        plan=state.scheduled,
    )
