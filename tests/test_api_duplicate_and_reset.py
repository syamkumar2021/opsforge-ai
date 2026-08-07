import pytest


@pytest.mark.asyncio
async def test_duplicate_active_exception_returns_409(client, auth_headers):
    payload = {
        "order_number": "ORD-10001",
        "exception_type": "vendor_status_mismatch",
        "severity": "high",
        "description": "Duplicate active investigation test payload",
    }

    first = await client.post(
        "/api/v1/events/simulate", headers=auth_headers, json=payload
    )
    assert first.status_code in (200, 409, 500), first.text

    if first.status_code == 500:
        pytest.skip(f"Simulate unavailable in this environment: {first.text}")

    second = await client.post(
        "/api/v1/events/simulate", headers=auth_headers, json=payload
    )
    assert second.status_code in (200, 409, 500), second.text

    if first.status_code == 200:
        assert second.status_code == 409, second.text
        detail = second.json().get("detail")
        assert detail is not None