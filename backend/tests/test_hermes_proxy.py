import httpx
import pytest
import respx


@pytest.mark.asyncio
@respx.mock
async def test_hermes_proxy_requires_auth(app_client):
    response = await app_client.get("/hermes/x")
    assert response.status_code == 401


@pytest.mark.asyncio
@respx.mock
async def test_hermes_proxy_forwards_authenticated_request(app_client):
    route = respx.get("http://hermes:9119/x").mock(
        return_value=httpx.Response(200, text="hi", headers={"content-type": "text/plain"})
    )
    login = await app_client.post("/api/auth/login", json={"password": "testpw"})
    assert login.status_code == 204

    response = await app_client.get("/hermes/x")

    assert response.status_code == 200
    assert response.text == "hi"
    assert route.called
