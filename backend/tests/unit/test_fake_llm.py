import json

from app.agent.fake import FakeLLM
from app.agent.llm import Completed, TextDelta


async def run(messages):
    deltas, result = [], None
    async for ev in FakeLLM().stream(system=[], tools=[], messages=messages):
        if isinstance(ev, TextDelta):
            deltas.append(ev.text)
        elif isinstance(ev, Completed):
            result = ev.result
    return "".join(deltas), result


async def test_move_rule():
    _, r = await run([{"role": "user", "content": "Перенеси задачу 3 на 2 дня"}])
    assert r.stop_reason == "tool_use"
    assert r.tool_calls[0].name == "apply_operations"
    assert r.tool_calls[0].input == {"operations": [{"op": "move_task", "id": 3, "shift_days": 2}]}


async def test_bulk_move_two_steps():
    first = [{"role": "user", "content": "Сдвинь все задачи Дмитрия на 3 дня"}]
    deltas1, r1 = await run(first)
    assert r1.tool_calls[0].name == "find_tasks"
    assert "дмитри" in r1.tool_calls[0].input["assignee"]
    # The pending shift must travel out-of-band (in the tool_use id), never as text that
    # would be streamed to the client or persisted as chat content.
    assert "[fake]" not in deltas1
    assert not any(b.get("type") == "text" for b in r1.content)
    assert r1.tool_calls[0].id.startswith("fake_shift_3_")
    found = json.dumps({"result": [{"id": 11}, {"id": 12}]})
    msgs = [
        *first,
        {"role": "assistant", "content": r1.content},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r1.tool_calls[0].id, "content": found}
            ],
        },
    ]
    deltas2, r2 = await run(msgs)
    ops = r2.tool_calls[0].input["operations"]
    assert [o["id"] for o in ops] == [11, 12] and all(o["shift_days"] == 3 for o in ops)
    assert "[fake]" not in deltas2
    assert not any(b.get("type") == "text" and "[fake]" in b.get("text", "") for b in r2.content)


async def test_final_text_after_tool_result_and_help():
    msgs = [
        {"role": "user", "content": "Удали задачу 7"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "fake_1", "name": "apply_operations", "input": {}}
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "fake_1",
                    "content": json.dumps({"summary": "Изменено задач: 3, удалено: 1"}),
                }
            ],
        },
    ]
    text, r = await run(msgs)
    assert r.stop_reason == "end_turn" and "Изменено задач: 3" in text
    text, _ = await run([{"role": "user", "content": "привет"}])
    assert "демо-режиме" in text


async def test_assign_keeps_original_case():
    _, r = await run([{"role": "user", "content": "Назначь задачу 5 на Анну Смирнову."}])
    op = r.tool_calls[0].input["operations"][0]
    assert op == {"op": "update_task", "id": 5, "assignee": "Анну Смирнову"}


def _system_table(*assignees):
    header = (
        "id | задача | исполнитель | длит | предш | не раньше | начало | конец | резерв | флаги"
    )
    rows = [
        f"{i + 1} | Задача {i + 1} | {name} | 1 | — | — | 2026-01-01 | 2026-01-02 | 0 | —"
        for i, name in enumerate(assignees)
    ]
    return [{"type": "text", "text": "\n".join([header, *rows])}]


async def run_assign(text, *assignees):
    system = _system_table(*assignees)
    messages = [{"role": "user", "content": text}]
    result = None
    async for ev in FakeLLM().stream(system=system, tools=[], messages=messages):
        if isinstance(ev, Completed):
            result = ev.result
    return result


async def test_assign_matches_existing_assignee_by_stem():
    r = await run_assign("Назначь задачу 5 на Наталью Белову.", "Наталья Белова", "Игорь Петров")
    op = r.tool_calls[0].input["operations"][0]
    assert op == {"op": "update_task", "id": 5, "assignee": "Наталья Белова"}


async def test_assign_matches_existing_assignee_by_stem_second_name():
    r = await run_assign("Назначь задачу 5 на Игоря Петрова.", "Наталья Белова", "Игорь Петров")
    op = r.tool_calls[0].input["operations"][0]
    assert op == {"op": "update_task", "id": 5, "assignee": "Игорь Петров"}


async def test_assign_unknown_name_kept_as_typed():
    r = await run_assign("Назначь задачу 5 на Василия Пупкина.", "Наталья Белова", "Игорь Петров")
    op = r.tool_calls[0].input["operations"][0]
    assert op == {"op": "update_task", "id": 5, "assignee": "Василия Пупкина"}


async def test_assign_ambiguous_match_kept_as_typed():
    r = await run_assign("Назначь задачу 5 на Сашу Иванова.", "Саша Иванов", "Саша Иванова")
    op = r.tool_calls[0].input["operations"][0]
    assert op == {"op": "update_task", "id": 5, "assignee": "Сашу Иванова"}
