async def test_session_cookie_and_plan(client):
    r = await client.get("/api/plan")
    assert r.status_code == 401 and r.json()["error"]["code"] == "no_session"
    r = await client.post("/api/session")
    assert r.status_code == 200 and "sid" in r.cookies
    body = (await client.get("/api/plan")).json()
    assert body["version"] == 1 and len(body["plan"]["tasks"]) == 25
    assert body["plan"]["tasks"][0]["start"]
    assert body["can_undo"] is False and body["agent_busy"] is False


async def test_stale_cookie_gets_401_then_new_session(client):
    client.cookies.set("sid", "stale-token")
    assert (await client.get("/api/plan")).status_code == 401
    assert (await client.post("/api/session")).status_code == 200
    assert (await client.get("/api/plan")).status_code == 200


async def test_session_post_is_idempotent(session_client):
    first = session_client.cookies["sid"]
    await session_client.post("/api/session")
    assert session_client.cookies["sid"] == first


async def test_operations_undo_redo(session_client):
    r = await session_client.post(
        "/api/plan/operations", json={"ops": [{"op": "update_task", "id": 1, "duration": 6}]}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 2 and body["summary"].startswith("Изменено задач")
    assert any(c["field"] == "duration" for c in body["changes"])
    assert (await session_client.post("/api/plan/undo")).json()["version"] == 1
    assert (await session_client.post("/api/plan/redo")).json()["version"] == 2


async def test_errors_envelope(session_client):
    r = await session_client.post(
        "/api/plan/operations", json={"ops": [{"op": "delete_task", "id": 999}]}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_operation"
    r = await session_client.post("/api/plan/operations", json={"ops": [{"op": "nope"}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = await session_client.post("/api/plan/undo")
    assert r.status_code == 409 and r.json()["error"]["message"] == "Нечего отменять"


async def test_bad_origin_rejected(session_client):
    r = await session_client.post("/api/plan/reset", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "bad_origin"


async def test_reset_and_delete_session(session_client):
    await session_client.post(
        "/api/plan/operations", json={"ops": [{"op": "delete_task", "id": 1}]}
    )
    assert len((await session_client.post("/api/plan/reset")).json()["plan"]["tasks"]) == 25
    assert (await session_client.delete("/api/session")).status_code == 204
    assert (await session_client.get("/api/plan")).status_code == 401


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
