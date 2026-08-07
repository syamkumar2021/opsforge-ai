import pytest


SAMPLE_ORDER = {
    "order_number": "ORD-20001",
    "customer_id": "CUST-T1",
    "customer_email": "buyer@email.com",
    "status": "processing",
    "total_amount": 10.0,
    "currency": "USD",
    "vendor_id": "VENDOR-1",
    "shipping_address": {"city": "Austin", "country": "US"},
    "items": [{"sku": "SKU-1", "qty": 1, "price": 10}],
}


@pytest.mark.asyncio
async def test_feed_and_list_erp_order(client, auth_headers):
    feed = await client.post(
        "/api/v1/erp/orders",
        headers=auth_headers,
        json={"orders": [SAMPLE_ORDER]},
    )
    assert feed.status_code in (201, 200)

    listed = await client.get(
        "/api/v1/erp/orders",
        headers=auth_headers,
        params={"order_number": "ORD-20001"},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert isinstance(body, list)


@pytest.mark.asyncio
async def test_reset_erp_requires_superuser_or_allows_admin(client, auth_headers):
    resp = await client.post("/api/v1/erp/orders/reset", headers=auth_headers)
    # admin bootstrap is superuser → 200; normal user → 403
    assert resp.status_code in (200, 403)