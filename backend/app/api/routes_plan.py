import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import check_origin, get_service, require_session
from app.api.schemas import (
    ApplyRequest,
    ApplyResponse,
    ImportFailure,
    ImportSuccess,
    PlanResponse,
    to_plan_response,
)
from app.excel.export import export_plan_xlsx
from app.excel.parse import parse_plan_xlsx
from app.services.errors import FileTooLarge

router = APIRouter(prefix="/api/plan", tags=["plan"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_GUILLEMETS = re.compile(r"[«»]")
_WHITESPACE = re.compile(r"\s+")
FALLBACK_FILENAME = "plan.xlsx"


def sanitize_filename(raw: str | None) -> str:
    """Cleans an uploaded filename before it's echoed back into a chat note/summary (spec §9.1):
    strips control chars/newlines (no injecting fake log lines into the note), collapses
    whitespace, drops «» (we add our own around the name), and caps length."""
    if not raw:
        return FALLBACK_FILENAME
    cleaned = _CONTROL_CHARS.sub("", raw)
    cleaned = _GUILLEMETS.sub("", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    if not cleaned:
        return FALLBACK_FILENAME
    return cleaned[:100]


@router.get("")
async def get_plan(
    request: Request, session_id: uuid.UUID = Depends(require_session)
) -> PlanResponse:
    service = get_service(request)
    state = await service.get_state(session_id)
    return to_plan_response(state, service.locks.is_busy(session_id))


@router.post("/operations", dependencies=[Depends(check_origin)])
async def apply_operations(
    request: Request, body: ApplyRequest, session_id: uuid.UUID = Depends(require_session)
) -> ApplyResponse:
    service = get_service(request)
    outcome = await service.apply(session_id, body.ops, source="user")
    return ApplyResponse(
        version=outcome.state.version,
        can_undo=outcome.state.can_undo,
        can_redo=outcome.state.can_redo,
        agent_busy=service.locks.is_busy(session_id),
        plan=outcome.state.scheduled,
        changes=outcome.changes,
        warnings=outcome.warnings,
        summary=outcome.summary,
        created_task_ids=outcome.created_task_ids,
    )


@router.post("/undo", dependencies=[Depends(check_origin)])
async def undo(request: Request, session_id: uuid.UUID = Depends(require_session)) -> PlanResponse:
    service = get_service(request)
    state = await service.undo(session_id)
    return to_plan_response(state, service.locks.is_busy(session_id))


@router.post("/redo", dependencies=[Depends(check_origin)])
async def redo(request: Request, session_id: uuid.UUID = Depends(require_session)) -> PlanResponse:
    service = get_service(request)
    state = await service.redo(session_id)
    return to_plan_response(state, service.locks.is_busy(session_id))


@router.post("/reset", dependencies=[Depends(check_origin)])
async def reset(request: Request, session_id: uuid.UUID = Depends(require_session)) -> PlanResponse:
    service = get_service(request)
    state = await service.reset(session_id)
    return to_plan_response(state, service.locks.is_busy(session_id))


@router.post("/import", dependencies=[Depends(check_origin)])
async def import_plan(
    request: Request,
    file: UploadFile,
    project_start: date = Form(...),
    session_id: uuid.UUID = Depends(require_session),
) -> Response:
    settings = request.app.state.settings
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise FileTooLarge(f"Файл больше {settings.max_upload_mb} МБ")
    result = parse_plan_xlsx(data, project_start)
    if not result.ok or result.plan is None:
        body = ImportFailure(ok=False, errors=result.errors, warnings=result.warnings)
        return JSONResponse(body.model_dump(mode="json"), status_code=422)
    name = sanitize_filename(file.filename)
    service = get_service(request)
    state = await service.replace(
        session_id,
        result.plan,
        source="import",
        summary=f"Импорт {name}",
        chat_note=f"Загружен план «{name}», задач: {len(result.plan.tasks)}",
    )
    ok = ImportSuccess(
        ok=True,
        plan=to_plan_response(state, service.locks.is_busy(session_id)),
        warnings=result.warnings,
    )
    return JSONResponse(ok.model_dump(mode="json"))


@router.get("/export")
async def export_plan(
    request: Request, session_id: uuid.UUID = Depends(require_session)
) -> Response:
    service = get_service(request)
    state = await service.get_state(session_id)
    data = export_plan_xlsx(state.scheduled)
    filename = f"plan-{date.today():%Y-%m-%d}.xlsx"
    return Response(
        data,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
