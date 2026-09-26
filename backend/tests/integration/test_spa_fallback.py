import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.main import create_app

from .conftest import TODAY


@pytest.fixture
async def spa_client(settings, sessionmaker, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>SPA</title>", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    cfg = settings.model_copy(update={"static_dir": str(tmp_path)})
    app = create_app(cfg, sessionmaker=sessionmaker, today=lambda: TODAY)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


async def test_client_routes_and_files_are_served_by_the_spa(spa_client):
    assert "SPA" in (await spa_client.get("/some/client/route")).text
    assert (await spa_client.get("/favicon.svg")).text == "<svg/>"


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/nope"), ("GET", "/api"), ("POST", "/api/plan/nope"), ("DELETE", "/api/x/y")],
)
async def test_unknown_api_paths_get_a_json_404_not_the_spa(spa_client, method, path):
    r = await spa_client.request(method, path)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["error"]["code"] == "not_found"


async def test_known_api_routes_still_work(spa_client):
    assert (await spa_client.get("/api/meta")).status_code == 200
    assert (await spa_client.get("/api/openapi.json")).status_code == 200
    assert (await spa_client.get("/healthz")).status_code == 200


async def test_head_is_answered_like_get_for_spa_paths(spa_client):
    # Uptime monitors and link checkers probe with HEAD; a 405 on "/" looks like an outage.
    for path in ("/", "/some/client/route", "/favicon.svg"):
        r = await spa_client.head(path)
        assert r.status_code == 200, path
        assert r.content == b""
    r = await spa_client.head("/api/nope")
    assert r.status_code == 404
