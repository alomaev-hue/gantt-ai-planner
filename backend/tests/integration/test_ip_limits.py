import httpx
from starlette.requests import Request

from app.api.deps import client_ip


def _client(app, **headers):
    transport = httpx.ASGITransport(app=app)  # peer address is 127.0.0.1
    return httpx.AsyncClient(transport=transport, base_url="http://testserver", headers=headers)


async def test_session_creation_is_limited_per_ip(app):
    app.state.settings.session_limit_per_ip_hour = 2
    statuses = []
    for _ in range(3):
        async with _client(app) as c:
            statuses.append((await c.post("/api/session")).status_code)
    assert statuses == [200, 200, 429]
    async with _client(app) as c:
        r = await c.post("/api/session")
    assert r.json()["error"]["code"] == "rate_limited"
    assert "сесси" in r.json()["error"]["message"]


async def test_reusing_a_valid_session_does_not_count(session_client, app):
    app.state.settings.session_limit_per_ip_hour = 1  # the fixture already used the one slot
    for _ in range(3):
        assert (await session_client.post("/api/session")).status_code == 200


async def test_forwarded_for_is_ignored_unless_proxy_is_trusted(app):
    app.state.settings.session_limit_per_ip_hour = 1
    async with _client(app, **{"x-forwarded-for": "1.1.1.1"}) as c:
        assert (await c.post("/api/session")).status_code == 200
    async with _client(app, **{"x-forwarded-for": "2.2.2.2"}) as c:  # spoofing doesn't help
        assert (await c.post("/api/session")).status_code == 429


async def test_trusted_proxy_uses_the_address_it_appended(app):
    app.state.settings.session_limit_per_ip_hour = 1
    app.state.settings.trust_proxy = True
    # Caddy sets/appends the real peer as the LAST hop; earlier hops are client-supplied.
    async with _client(app, **{"x-forwarded-for": "6.6.6.6, 203.0.113.7"}) as c:
        assert (await c.post("/api/session")).status_code == 200
    async with _client(app, **{"x-forwarded-for": "7.7.7.7, 203.0.113.7"}) as c:
        assert (await c.post("/api/session")).status_code == 429
    async with _client(app, **{"x-forwarded-for": "203.0.113.8"}) as c:
        assert (await c.post("/api/session")).status_code == 200


async def test_chat_is_limited_per_ip_across_sessions(app):
    app.state.settings.chat_limit_per_ip_hour = 1
    async with _client(app) as a, _client(app) as b:
        await a.post("/api/session")
        await b.post("/api/session")
        async with a.stream("POST", "/api/chat", json={"message": "привет"}) as r:
            assert r.status_code == 200
            [chunk async for chunk in r.aiter_text()]
        r = await b.post("/api/chat", json={"message": "привет"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


def test_client_ip_without_peer_falls_back(app):
    request = Request({"type": "http", "headers": [], "client": None, "app": app})
    assert client_ip(request) == "unknown"
