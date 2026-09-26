import asyncio
import json

import httpx

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


async def test_chat_daily_limit_is_atomic_under_concurrency(app):
    """Regression for the check-then-insert race: the day-level count and the chat
    message insert used to happen in separate transactions (check in the route,
    insert later inside run_turn()), so concurrent requests from different sessions
    could all pass the count check before any of them committed its insert and
    together blow past chat_limit_per_day. With the atomic check+reserve under
    pg_advisory_xact_lock, at most the limit's worth of requests can ever succeed,
    however many fire at once.
    """
    app.state.settings.chat_limit_per_day = 3
    transport = httpx.ASGITransport(app=app)

    async def one_request() -> int:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            assert (await c.post("/api/session")).status_code == 200
            r = await c.post("/api/chat", json={"message": "привет"})
            return r.status_code

    statuses = await asyncio.gather(*(one_request() for _ in range(6)))
    assert statuses.count(200) <= 3
    assert statuses.count(200) + statuses.count(429) == 6


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


async def test_busy_after_reservation_leaves_no_orphan_user_message(
    app, session_client, monkeypatch
):
    """Two sends from one session can both pass the route's is_busy() check; the loser only
    learns it is busy inside the SSE stream (after its user message was reserved). That
    reserved message must be removed, and the stream must end with an agent_busy error."""
    service = app.state.service
    token = session_client.cookies.get("sid")
    sid = await service.resolve_session(token)
    monkeypatch.setattr(service.locks, "is_busy", lambda _sid: False)
    async with (
        service.locks.agent_turn(sid),  # another turn is running
        session_client.stream("POST", "/api/chat", json={"message": "ещё"}) as r,
    ):
        assert r.status_code == 200
        body = "".join([chunk async for chunk in r.aiter_text()])
    events = parse_sse(body)
    assert events[-1]["event"] == "error" and events[-1]["data"]["code"] == "agent_busy"
    assert (await session_client.get("/api/chat/history")).json() == []
