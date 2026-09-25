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
    _, r1 = await run(first)
    assert r1.tool_calls[0].name == "find_tasks"
    assert "дмитри" in r1.tool_calls[0].input["assignee"]
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
    _, r2 = await run(msgs)
    ops = r2.tool_calls[0].input["operations"]
    assert [o["id"] for o in ops] == [11, 12] and all(o["shift_days"] == 3 for o in ops)


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
