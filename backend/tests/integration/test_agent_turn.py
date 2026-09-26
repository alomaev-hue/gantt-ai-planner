from datetime import date

from app.agent.llm import Completed, LLMError, LLMToolCall, LLMTurnResult, TextDelta
from app.agent.loop import Agent
from app.db import repo
from app.domain.calendar import add_workdays

TODAY = date(2026, 9, 25)


async def collect(agent, sid, text):
    return [ev async for ev in agent.run_turn(sid, text)]


async def new_sid(app):
    _, sid = await app.state.service.create_session()
    return sid


async def test_turn_moves_task_and_reports(app):
    sid = await new_sid(app)
    events = await collect(app.state.agent, sid, "Перенеси задачу 1 на 2 дня")
    types = [e["type"] for e in events]
    assert "tool_started" in types and "plan_changed" in types and types[-1] == "done"
    done = events[-1]
    assert done["summary"].startswith("Изменено задач") and any(
        c["task_id"] == 1 for c in done["changes"]
    )
    assert (await app.state.service.get_state(sid)).version == 2
    assert (await app.state.service.undo(sid)).version == 1


async def test_bulk_move_is_one_undo_group(app):
    sid = await new_sid(app)
    events = await collect(app.state.agent, sid, "Сдвинь все задачи Дмитрия на 3 дня")
    assert events[-1]["type"] == "done" and events[-1]["changes"]
    assert (await app.state.service.undo(sid)).version == 1
    async with app.state.service.sessionmaker() as db:
        msgs = await repo.recent_chat_messages(db, sid, 10)
    assert all("[fake]" not in m.content for m in msgs)


async def test_bulk_shift_moves_each_task_and_project_end_exactly_n_workdays(app):
    # Regression: shifting a chain (Дмитрий owns successive tasks in the demo plan) used to
    # compound — successors moved 6 and 9 workdays and project_end moved 9 instead of 3.
    sid = await new_sid(app)
    before = (await app.state.service.get_state(sid)).scheduled
    dmitry = [t.id for t in before.tasks if t.assignee and t.assignee.startswith("Дмитри")]
    assert len(dmitry) >= 2
    events = await collect(app.state.agent, sid, "Сдвинь все задачи Дмитрия на 3 дня")
    assert events[-1]["type"] == "done"
    after = (await app.state.service.get_state(sid)).scheduled
    for tid in dmitry:
        assert after.task(tid).start == add_workdays(before.task(tid).start, 3), tid
    assert after.project_end == add_workdays(before.project_end, 3)


async def test_turn_persists_chat_and_clears_busy(app):
    sid = await new_sid(app)
    await collect(app.state.agent, sid, "привет")
    async with app.state.service.sessionmaker() as db:
        msgs = await repo.recent_chat_messages(db, sid, 10)
    assert [m.role for m in msgs] == ["user", "assistant"] and "демо-режиме" in msgs[1].content
    assert not app.state.service.locks.is_busy(sid)


async def test_iteration_cap(app):
    class Looping:
        async def stream(self, *, system, tools, messages):
            call = LLMToolCall(id=f"x{len(messages)}", name="get_plan", input={})
            yield Completed(
                LLMTurnResult(
                    text="",
                    tool_calls=[call],
                    stop_reason="tool_use",
                    content=[{"type": "tool_use", "id": call.id, "name": "get_plan", "input": {}}],
                )
            )

    sid = await new_sid(app)
    agent = Agent(
        Looping(), app.state.tool_client, app.state.service, today=lambda: TODAY, max_iterations=3
    )
    events = await collect(agent, sid, "зациклись")
    assert events[-1]["type"] == "error" and events[-1]["code"] == "too_many_steps"
    assert not app.state.service.locks.is_busy(sid)


async def test_llm_error_is_reported(app):
    class Broken:
        async def stream(self, *, system, tools, messages):
            raise LLMError("llm_unavailable", "LLM временно недоступна, попробуйте позже")
            yield  # pragma: no cover

    sid = await new_sid(app)
    agent = Agent(Broken(), app.state.tool_client, app.state.service, today=lambda: TODAY)
    events = await collect(agent, sid, "что-нибудь")
    assert events[-1] == {
        "type": "error",
        "code": "llm_unavailable",
        "message": "LLM временно недоступна, попробуйте позже",
    }
    assert not app.state.service.locks.is_busy(sid)


async def test_llm_error_after_partial_text_persists_error_not_partial(app):
    class PartialThenBroken:
        async def stream(self, *, system, tools, messages):
            yield TextDelta("Сейчас перене")
            raise LLMError("llm_unavailable", "LLM временно недоступна, попробуйте позже")

    sid = await new_sid(app)
    agent = Agent(
        PartialThenBroken(), app.state.tool_client, app.state.service, today=lambda: TODAY
    )
    events = await collect(agent, sid, "что-нибудь")
    assert events[-1] == {
        "type": "error",
        "code": "llm_unavailable",
        "message": "LLM временно недоступна, попробуйте позже",
    }
    async with app.state.service.sessionmaker() as db:
        msgs = await repo.recent_chat_messages(db, sid, 10)
    assistant_msg = msgs[-1]
    assert assistant_msg.role == "assistant"
    assert assistant_msg.content == "LLM временно недоступна, попробуйте позже"
    assert "Сейчас перене" not in assistant_msg.content
    assert assistant_msg.meta["partial_text"] == "Сейчас перене"
    assert assistant_msg.meta["error"] == "llm_unavailable"
