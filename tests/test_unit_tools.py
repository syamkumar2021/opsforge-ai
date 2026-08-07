import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_order_details_tool_path():
    from app.agents.tools import get_order_details

    mock_order = MagicMock()
    mock_order.id = "id1"
    mock_order.order_number = "ORD-10001"
    mock_order.status.value = "processing"
    mock_order.customer_id = "C1"
    mock_order.customer_email = "a@x.com"
    mock_order.total_amount = 10
    mock_order.currency = "USD"
    mock_order.shipping_address = {}
    mock_order.items = []
    mock_order.vendor_id = "V1"
    mock_order.tracking_number = None
    mock_order.notes = None
    mock_order.created_at = None
    mock_order.updated_at = None

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_order
    session.execute.return_value = result

    with patch("app.agents.tools.get_db_context") as ctx:
        ctx.return_value.__aenter__.return_value = session
        # support both callable tool and .ainvoke style
        if hasattr(get_order_details, "ainvoke"):
            out = await get_order_details.ainvoke({"order_number": "ORD-10001"})
        else:
            out = await get_order_details("ORD-10001")
    assert out["found"] is True or out.get("order_number") == "ORD-10001"