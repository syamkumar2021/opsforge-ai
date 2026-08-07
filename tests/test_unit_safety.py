import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.execution_handler import _map_status, _safe_confidence
from app.models import ExecutionStatus
from app.agents.graph import should_continue_after_planner, should_go_to_human
from app.agents.nodes import human_review_node, reporting_node


def test_map_status_case_insensitive_safety():
    assert _map_status("WaItInG_HuMaN") == ExecutionStatus.WAITING_HUMAN
    assert _map_status("COMPLETED") == ExecutionStatus.COMPLETED
    assert _safe_confidence(1) == 1.0


def test_routing_safety_edges():
    # empty/missing plan should end safely
    assert should_continue_after_planner({}) == "end"
    assert should_continue_after_planner({"plan": []}) == "end"
    # high confidence + low severity => reporting
    assert should_go_to_human({"confidence": 0.99, "event": {"severity": "medium"}}) == "reporting"


@pytest.mark.asyncio
async def test_human_and_report_safety():
    state = {
        "thread_id": "safe-1",
        "event": {
            "order_number": "ORD-10001",
            "exception_type": "vendor_status_mismatch",
            "severity": "low",
            "description": "safety",
        },
        "plan": ["generate_report"],
        "research_data": {"order": {"status": "processing", "order_number": "ORD-10001"}, "exception": {}},
        "browser_evidence": {"portal_status": "Delivered", "success": True, "source": "playwright"},
        "integration_result": {"success": True, "system": "mulesoft_mock"},
        "report": "",
        "confidence": 0.91,
        "human_decision": "approved",
        "human_notes": "ok",
        "status": "investigating",
        "messages": [],
        "error": None,
        "agents_executed": [],
        "notification_result": {},
    }
    h = await human_review_node(state)
    assert h["error"] is None
    r = await reporting_node(state)
    assert "OpsForge Investigation Report" in r["report"]