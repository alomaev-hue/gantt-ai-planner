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


async def test_task_history_lists_edits_newest_first(session_client):
    await session_client.post(
        "/api/plan/operations", json={"ops": [{"op": "update_task", "id": 1, "duration": 6}]}
    )
    await session_client.post(
        "/api/plan/operations", json={"ops": [{"op": "update_task", "id": 1, "name": "Новое имя"}]}
    )
    r = await session_client.get("/api/plan/tasks/1/history")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["version"] > body[1]["version"]
    assert all(entry["source"] == "user" for entry in body)
    assert all(entry["created_at"] for entry in body)
    assert body[0]["changes"][0]["field"] == "name"
    assert body[1]["changes"][0]["field"] == "duration"
    # untouched task: exists but has no history entries yet, not a 404.
    r2 = await session_client.get("/api/plan/tasks/2/history")
    assert r2.status_code == 200 and r2.json() == []


async def test_task_history_shows_agent_source(session_client):
    async with session_client.stream(
        "POST", "/api/chat", json={"message": "Перенеси задачу 1 на 1 день"}
    ) as r:
        [_ async for _ in r.aiter_text()]
    r = await session_client.get("/api/plan/tasks/1/history")
    assert r.status_code == 200
    body = r.json()
    assert body and body[0]["source"] == "agent"


async def test_task_history_unknown_task_404(session_client):
    r = await session_client.get("/api/plan/tasks/999/history")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
