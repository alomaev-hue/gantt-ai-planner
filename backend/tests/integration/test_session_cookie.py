import httpx
from asgi_lifespan import LifespanManager

from app.main import create_app

from .conftest import TODAY

TTL_SECONDS = 14 * 86400


async def test_cookie_lifetime_is_refreshed_on_every_visit(session_client):
    # Spec: the session lives 14 days after the LAST visit, so the browser cookie must be
    # re-issued with a fresh Max-Age whenever the session is used, not only when created.
    r = await session_client.get("/api/plan")
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert set_cookie.startswith(f"sid={session_client.cookies['sid']};")
    assert f"Max-Age={TTL_SECONDS}" in set_cookie and "HttpOnly" in set_cookie


async def test_delete_session_really_clears_the_secure_host_cookie(settings, sessionmaker):
    # A __Host- cookie is only accepted (and so only deletable) with Secure; a deletion
    # without it is ignored by browsers and the stale cookie lingers.
    secure = settings.model_copy(update={"cookie_secure": True})
    app = create_app(secure, sessionmaker=sessionmaker, today=lambda: TODAY)
    async with LifespanManager(app):
        token, _ = await app.state.service.create_session()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as c:
            r = await c.delete("/api/session", headers={"cookie": f"__Host-sid={token}"})
    assert r.status_code == 204
    cleared = [h for h in r.headers.get_list("set-cookie") if h.startswith("__Host-sid=")]
    assert len(cleared) == 1
    attrs = cleared[0].lower()
    assert "max-age=0" in attrs and "secure" in attrs and "path=/" in attrs
