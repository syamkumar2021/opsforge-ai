import pytest


@pytest.mark.asyncio
async def test_health_positive(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "healthy"


@pytest.mark.asyncio
async def test_docs_positive(client):
    resp = await client.get("/docs")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_positive(client):
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@opsforge.ai", "password": "OpsForge@123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert body.get("token_type", "").lower() == "bearer"


@pytest.mark.asyncio
async def test_login_negative_wrong_password(client):
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@opsforge.ai", "password": "wrong-password"},
    )
    assert resp.status_code in (400, 401), resp.text


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    resp = await client.get("/api/v1/me")
    assert resp.status_code in (401, 403), resp.text


@pytest.mark.asyncio
async def test_me_with_auth(client, auth_headers):
    resp = await client.get("/api/v1/me", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert "email" in resp.json()