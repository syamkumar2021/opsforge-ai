import pytest


@pytest.mark.asyncio
async def test_register_success(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "tester.api@opsforge.ai",
            "password": "OpsForge@123",
            "full_name": "Tester API",
        },
    )
    assert resp.status_code in (201, 400)  # 400 if already exists


@pytest.mark.asyncio
async def test_register_rejects_non_company_domain(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "someone@gmail.com",
            "password": "OpsForge@123",
            "full_name": "Someone",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client):
    # ensure user exists
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "tester.login@opsforge.ai",
            "password": "OpsForge@123",
            "full_name": "Tester Login",
        },
    )
    resp = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "tester.login@opsforge.ai",
            "password": "OpsForge@123",
        },
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()