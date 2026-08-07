import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.nodes import (
    planner_node,
    research_node,
    browser_node,
    integration_node,
    reporting_node,
    human_review_node,
    notification_node,
)
from app.mulesoft import update_order_in_erp, get_order_from_erp
from app.browser_agent import BrowserAgent


def _state(**overrides):
    base = {
        "thread_id": "t1",
        "event": {
            "order_number": "ORD-10001",
            "exception_type": "vendor_status_mismatch",
            "severity": "high",
            "description": "unit",
        },
        "plan": ["research_order", "check_vendor_portal", "generate_report"],
        "research_data": {
            "order": {
                "found": True,
                "order_number": "ORD-10001",
                "status": "processing",
                "customer_email": "a@x.com",
                "customer_id": "C1",
                "vendor_id": "V1",
                "total_amount": 10,
                "currency": "USD",
                "tracking_number": None,
            },
            "exception": {
                "found": True,
                "exception_type": "vendor_status_mismatch",
                "severity": "high",
                "description": "mismatch",
                "status": "open",
                "detected_at": "2026-07-25T00:00:00Z",
            },
        },
        "browser_evidence": {"portal_status": "In Transit", "success": True, "source": "playwright"},
        "integration_result": {
            "success": True,
            "system": "mulesoft_mock",
            "old_status": "processing",
            "new_status": "processing",
            "notes": "n",
        },
        "report": "r",
        "confidence": 0.88,
        "human_decision": "approved",
        "human_notes": "ok",
        "status": "investigating",
        "messages": [],
        "error": None,
        "agents_executed": [],
        "notification_result": {},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_planner_node_fallback_plan():
    with patch("app.agents.nodes.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="not-json"))
        result = await planner_node(_state())
    assert result["error"] is None
    assert isinstance(result["plan"], list)
    assert "planner" in result["agents_executed"]


@pytest.mark.asyncio
async def test_research_node_success():
    with patch("app.agents.nodes.get_order_details") as go, patch(
        "app.agents.nodes.get_exception_context"
    ) as ge:
        go.ainvoke = AsyncMock(return_value={"found": True, "order_number": "ORD-10001"})
        ge.ainvoke = AsyncMock(return_value={"found": True})
        result = await research_node(_state())
    assert result["error"] is None
    assert "research" in result["agents_executed"]


@pytest.mark.asyncio
async def test_browser_node_truncation():
    with patch("app.browser_agent.browser_agent") as ba, patch(
        "app.agents.nodes.save_vendor_status"
    ) as sv:
        ba.check_vendor_status = AsyncMock(
            return_value={
                "order_number": "ORD-10001",
                "portal_status": "In Transit",
                "success": True,
                "raw_text": "A" * 1000,
                "tracking_number": None,
                "source": "playwright",
            }
        )
        sv.ainvoke = AsyncMock(return_value={"success": True})
        result = await browser_node(_state())
    assert len(result["browser_evidence"]["raw_text"]) <= 304
    assert "browser" in result["agents_executed"]


@pytest.mark.asyncio
async def test_integration_node_success():
    with patch("app.agents.nodes.update_order_in_erp", new_callable=AsyncMock) as mock_upd:
        mock_upd.return_value = {"success": True, "system": "mulesoft_mock"}
        result = await integration_node(_state())
    assert result["error"] is None
    assert "integration" in result["agents_executed"]


@pytest.mark.asyncio
async def test_reporting_and_notification_and_human():
    r = await reporting_node(_state())
    assert "OpsForge Investigation Report" in r["report"]

    with patch(
        "app.notify.send_final_notification",
        new_callable=AsyncMock,
    ) as send_final:
        send_final.return_value = {
            "type": "final_notification",
            "channel": "email",
            "status": "sent",
            "to": ["ops-team@company.com"],
            "subject": "[OpsForge][COMPLETED] ORD-10001 (auto)",
            "sent_at": "2026-08-03T00:00:00+00:00",
        }
        n = await notification_node(_state(report="hello"))

    assert n["error"] is None
    assert "final_email" in n["notification_result"]
    assert n["notification_result"]["final_email"]["status"] == "sent"

    h = await human_review_node(_state(human_decision="approved"))
    assert h["error"] is None


@pytest.mark.asyncio
async def test_mulesoft_update_and_get():
    mock_order = MagicMock()
    mock_order.status.value = "exception"
    mock_order.notes = ""
    mock_order.updated_at = None
    mock_order.order_number = "ORD-10001"
    mock_order.customer_id = "C1"
    mock_order.total_amount = 10
    mock_order.tracking_number = None
    mock_order.vendor_id = "V1"

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_order
    session.execute.return_value = result
    session.add = MagicMock()

    with patch("app.mulesoft.get_db_context") as ctx:
        ctx.return_value.__aenter__.return_value = session
        upd = await update_order_in_erp("ORD-10001", "processing", "n", {"thread_id": "t"})
        got = await get_order_from_erp("ORD-10001")
    assert upd["success"] is True
    assert got["success"] is True


@pytest.mark.asyncio
async def test_browser_agent_check_vendor_status_mocked_playwright():
    agent = BrowserAgent()
    agent.browser = MagicMock()

    page = AsyncMock()
    page.goto = AsyncMock()
    page.locator = MagicMock()

    # Playwright locator.inner_text is awaited
    async def _inner_text():
        return "In Transit"

    portal_locator = MagicMock()
    portal_locator.inner_text = AsyncMock(return_value="In Transit")
    eta_locator = MagicMock()
    eta_locator.inner_text = AsyncMock(return_value="2026-07-31")
    track_locator = MagicMock()
    track_locator.inner_text = AsyncMock(return_value="TRK-0001-IT")
    body_locator = MagicMock()
    body_locator.inner_text = AsyncMock(return_value="Vendor portal body")

    def locator_side_effect(selector):
        return {
            "#portal-status": portal_locator,
            "#eta": eta_locator,
            "#tracking-number": track_locator,
            "body": body_locator,
        }.get(selector, portal_locator)

    page.locator.side_effect = locator_side_effect

    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    agent.browser.new_context = AsyncMock(return_value=context)

    evidence = await agent.check_vendor_status(
        order_number="ORD-10001",
        tracking_number=None,
        exception_type="vendor_status_mismatch",
    )

    assert evidence["success"] is True
    assert evidence["portal_status"] == "In Transit"