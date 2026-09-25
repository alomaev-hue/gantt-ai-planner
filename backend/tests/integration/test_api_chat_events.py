import asyncio
import json

from app.api.routes_events import event_stream


def parse_sse(body: str) -> list[dict]:
    events, current = [], {}
    for line in body.splitlines():
        if line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line[5:].strip())
        elif not line.strip() and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


async def test_chat_streams_events(session_client):
    async with session_client.stream(
        "POST", "/api/chat", json={"message": "Перенеси задачу 1 на 1 день"}
    ) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in r.aiter_text()])
    events = parse_sse(body)
    assert events[-1]["event"] == "done"
    history = (await session_client.get("/api/chat/history")).json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["meta"]["summary"].startswith("Изменено задач")


async def test_chat_rate_limit(app, session_client):
    app.state.settings.chat_limit_per_hour = 1
    async with session_client.stream("POST", "/api/chat", json={"message": "привет"}) as r:
        [c async for c in r.aiter_text()]
    r = await session_client.post("/api/chat", json={"message": "ещё"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


async def test_chat_validation(session_client):
    assert (await session_client.post("/api/chat", json={"message": ""})).status_code == 422


async def test_event_stream_generator(app):
    _, sid = await app.state.service.create_session()
    bus = app.state.service.bus
    gen = event_stream(bus, sid, busy=False)
    first = await asyncio.wait_for(gen.__anext__(), 1)
    assert first["event"] == "agent_status"
    bus.publish(sid, {"type": "plan_changed", "version": 2})
    second = await asyncio.wait_for(gen.__anext__(), 1)
    assert second["event"] == "plan_changed"
    await gen.aclose()
    assert sid not in bus._subs
