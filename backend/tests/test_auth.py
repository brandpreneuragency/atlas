async def test_login_wrong_password_401(app_client):
    response = await app_client.post("/api/auth/login", json={"password": "nope"})
    assert response.status_code == 401


async def test_login_ok_sets_cookie_and_me_works(app_client):
    response = await app_client.post("/api/auth/login", json={"password": "testpw"})
    assert response.status_code == 204
    assert "atlas_session" in response.cookies
    assert "HttpOnly" in response.headers["set-cookie"]

    me = await app_client.get("/api/me")
    assert me.status_code == 200
    assert me.json() == {"authenticated": True}


async def test_unauthenticated_api_401(app_client):
    response = await app_client.get("/api/agents")
    assert response.status_code == 401


async def test_mutating_route_requires_csrf_header(app_client):
    login = await app_client.post("/api/auth/login", json={"password": "testpw"})
    assert login.status_code == 204

    missing = await app_client.post("/api/killswitch", json={"paused": True})
    assert missing.status_code == 403

    ok = await app_client.post(
        "/api/killswitch",
        json={"paused": True},
        headers={"X-Atlas-CSRF": "1"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"paused": True}


async def test_login_rate_limit(app_client):
    statuses = []
    for _ in range(6):
        response = await app_client.post("/api/auth/login", json={"password": "nope"})
        statuses.append(response.status_code)
    assert statuses[:5] == [401, 401, 401, 401, 401]
    assert statuses[5] == 429


async def test_health_is_public(app_client):
    response = await app_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["hermes"] == {"runs_api": "mock"}
