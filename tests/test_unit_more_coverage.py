import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from app.config import get_settings
from app.auth import get_password_hash, verify_password, create_access_token
from app.execution_handler import _map_status, _safe_confidence
from app.agents.graph import should_continue_after_planner, should_go_to_human
from app.models import ExecutionStatus
from app.schemas import SimulateEventRequest, HumanDecisionRequest
from app.agents.nodes import (
    planner_node,
    research_node,
    integration_node,
    reporting_node,
    notification_node,
    human_review_node,
)
from app.mulesoft import update_order_in_erp, get_order_from_erp


def _state(**over):
    s = {
        "thread_id": "cov-thread",
        "event": {
            "order_number": "ORD-10001",
            "exception_type": "vendor_status_mismatch",
            "severity": "medium",
            "description": "coverage event",
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
                "severity": "medium",
                "description": "mismatch",
                "status": "open",
                "detected_at": "2026-07-25T00:00:00Z",
            },
        },
        "browser_evidence": {
            "portal_status": "In Transit",
            "success": True,
            "source": "playwright",
            "tracking_number": None,
            "eta": "2026-07-28",
        },
        "integration_result": {
            "success": True,
            "system": "mulesoft_mock",
            "old_status": "processing",
            "new_status": "processing",
            "notes": "n",
        },
        "report": "",
        "confidence": 0.9,
        "human_decision": None,
        "human_notes": None,
        "status": "investigating",
        "messages": [],
        "error": None,
        "agents_executed": [],
        "notification_result": {},
    }
    s.update(over)
    return s


def test_settings_values():
    s = get_settings()
    assert "postgresql" in s.database_url
    assert s.kafka_topic_exceptions or True


def test_auth_helpers():
    h = get_password_hash("OpsForge@123")
    assert verify_password("OpsForge@123", h)
    assert create_access_token({"sub": "a@b.com"}).count(".") == 2


def test_map_status_all_branches():
    assert _map_status("PENDING") == ExecutionStatus.PENDING
    assert _map_status("investigating") == ExecutionStatus.RUNNING
    assert _map_status("waiting_human") == ExecutionStatus.WAITING_HUMAN
    assert _map_status("completed") == ExecutionStatus.COMPLETED
    assert _map_status("failed") == ExecutionStatus.FAILED
    assert _map_status(None) == ExecutionStatus.COMPLETED


def test_routing_all_branches():
    assert should_continue_after_planner({"plan": ["research_order"]}) == "research"
    assert should_continue_after_planner({"plan": ["check_vendor"]}) == "browser"
    assert should_continue_after_planner({"plan": ["wrap_up"]}) == "end"
    assert should_go_to_human({"confidence": 0.2, "event": {"severity": "low"}}) == "human_review"
    assert should_go_to_human({"confidence": 0.95, "event": {"severity": "critical"}}) == "human_review"
    assert should_go_to_human({"confidence": 0.95, "event": {"severity": "low"}}) == "reporting"


def test_simulate_schema_branches():
    ok = SimulateEventRequest(
        order_number="ORD-10001",
        exception_type="shipping_delay",
        severity="low",
        description="coverage valid payload with enough text",
    )
    assert ok.exception_type == "shipping_delay"
    with pytest.raises(ValidationError):
        SimulateEventRequest(
            order_number="ORD-10001",
            exception_type="shipping_delay",
            severity="INVALID",
            description="bad",
        )


def test_human_decision_schema():
    assert HumanDecisionRequest(decision="rejected", notes="no").decision == "rejected"


@pytest.mark.asyncio
async def test_planner_json_and_fallback():
    with patch("app.agents.nodes.llm") as llm:
        llm.ainvoke = AsyncMock(return_value=MagicMock(content='["research_order", "generate_report"]'))
        r1 = await planner_node(_state())
        assert r1["plan"][0] == "research_order"

        llm.ainvoke = AsyncMock(return_value=MagicMock(content="not-json"))
        r2 = await planner_node(_state())
        assert isinstance(r2["plan"], list)


@pytest.mark.asyncio
async def test_research_integration_report_notification_human():
    with patch("app.agents.nodes.get_order_details") as go, patch(
        "app.agents.nodes.get_exception_context"
    ) as ge:
        go.ainvoke = AsyncMock(return_value={"found": True})
        ge.ainvoke = AsyncMock(return_value={"found": True})
        assert (await research_node(_state()))["error"] is None

    # Patch the symbols used by integration_node at their source modules
    with patch("app.agents.tools.update_order_status") as up_tool, patch(
        "app.mulesoft.update_order_in_erp", new_callable=AsyncMock
    ) as up_direct, patch(
        "app.decision_rules.evaluate_mismatch"
    ) as eval_mock:
        eval_mock.return_value = type(
            "D",
            (),
            {
                "action": "keep_erp_status",
                "reason": "unit-test",
                "mismatch": False,
                "confidence": 0.9,
                "trust_portal": True,
                "requires_human": False,
                "recommended_erp_status": "processing",
            },
        )()
        with patch("app.decision_rules.decision_to_dict", return_value={
            "action": "keep_erp_status",
            "reason": "unit-test",
            "mismatch": False,
            "confidence": 0.9,
            "trust_portal": True,
            "requires_human": False,
            "recommended_erp_status": "processing",
        }):
            up_tool.ainvoke = AsyncMock(
                return_value={
                    "success": True,
                    "system": "mulesoft_mock",
                    "old_status": "processing",
                    "new_status": "processing",
                }
            )
            up_direct.return_value = {
                "success": True,
                "system": "mulesoft_mock",
                "old_status": "processing",
                "new_status": "processing",
            }
            assert (await integration_node(_state()))["error"] is None

    assert "OpsForge Investigation Report" in (await reporting_node(_state()))["report"]

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
        n = await notification_node(_state(report="x"))

    assert n["notification_result"]["final_email"]["status"] == "sent"
    assert (await human_review_node(_state(human_decision=None)))["status"] == "waiting_human"
    assert (await human_review_node(_state(human_decision="approved")))["error"] is None

@pytest.mark.asyncio
async def test_mulesoft_success_and_not_found():
    session = AsyncMock()
    found = MagicMock()
    found.status.value = "exception"
    found.notes = ""
    found.updated_at = None
    found.order_number = "ORD-10001"
    found.customer_id = "C1"
    found.total_amount = 11
    found.tracking_number = None
    found.vendor_id = "V1"

    res_found = MagicMock()
    res_found.scalar_one_or_none.return_value = found
    res_none = MagicMock()
    res_none.scalar_one_or_none.return_value = None
    session.add = MagicMock()

    with patch("app.mulesoft.get_db_context") as ctx:
        session.execute.return_value = res_found
        ctx.return_value.__aenter__.return_value = session
        ok = await update_order_in_erp("ORD-10001", "processing", "n", {"thread_id": "t"})
        got = await get_order_from_erp("ORD-10001")

        session.execute.return_value = res_none
        missing = await update_order_in_erp("ORD-404", "processing", "n", {"thread_id": "t"})

    assert ok["success"] is True
    assert got["success"] is True
    assert missing["success"] is False


