import asyncio
import logging
import uuid

from app.logging_setup import AccessLogMiddleware, configure


async def _app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"secret-body-content"})


def _run(scope):
    async def receive():
        return {"type": "http.request"}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    middleware = AccessLogMiddleware(_app)
    asyncio.run(middleware(scope, receive, send))
    return sent


def test_access_log_line_has_no_query_string_or_body(caplog):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/plan",
        "query_string": b"token=abc123&password=hunter2",
        "headers": [(b"cookie", b"sid=topsecret")],
        "state": {},
    }
    with caplog.at_level(logging.INFO, logger="app.access"):
        _run(scope)

    lines = [r.message for r in caplog.records if r.name == "app.access"]
    assert len(lines) == 1
    line = lines[0]
    parts = line.split()
    assert parts[0] == "GET"
    assert parts[1] == "/api/plan"
    assert parts[2] == "200"
    assert parts[-1] == "sid=-"
    assert "token=abc123" not in line
    assert "password" not in line
    assert "hunter2" not in line
    assert "secret-body-content" not in line
    assert "cookie" not in line.lower()


def test_access_log_uses_session_id_prefix_from_request_state(caplog):
    sid = uuid.uuid4()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/chat",
        "query_string": b"",
        "state": {"session_id": sid},
    }
    with caplog.at_level(logging.INFO, logger="app.access"):
        _run(scope)

    line = next(r.message for r in caplog.records if r.name == "app.access")
    assert f"sid={str(sid)[:8]}" in line


def test_configure_sets_level_and_disables_uvicorn_access_log():
    configure("DEBUG")
    try:
        assert logging.getLogger().level == logging.DEBUG
        assert logging.getLogger("uvicorn.access").disabled is True
    finally:
        logging.getLogger("uvicorn.access").disabled = False
        logging.basicConfig(level=logging.WARNING, force=True)
