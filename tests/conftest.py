import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def client():
    """
    Call the already-running Docker backend.
    Avoids ASGITransport / asyncpg event-loop issues.
    """
    async with AsyncClient(base_url="http://127.0.0.1:8000", timeout=60.0) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client):
    resp = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "admin@opsforge.ai",
            "password": "OpsForge@123",
        },
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}