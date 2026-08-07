import pytest

from app.agents.nodes import reporting_node


def _as_text(value):
    """Normalize accidental tuple/list values from state/report fields."""
    if isinstance(value, (tuple, list)):
        return str(value[0]) if value else ""
    return value


@pytest.mark.asyncio
async def test_reporting_node_includes_structured_and_approved_by():
    state = {
        "thread_id": "t-1",
        "event": {
            "order_number": "ORD-10001",
            "exception_type": "vendor_status_mismatch",
            "severity": "high",
            "description": "mismatch",
        },
        "research_data": {
            "order": {
                "found": True,
                "status": "processing",
                "order_number": "ORD-10001",
                "customer_email": "a@x.com",
                "customer_id": "C1",
                "vendor_id": "V1",
                "total_amount": 10,
                "currency": "USD",
            },
            "exception": {},
        },
        "browser_evidence": {
            "portal_status": "In Transit",
            "tracking_number": "TRK-0001-IT",
            "eta": "2026-07-31",
            "success": True,
            "source": "playwright",
        },
        "integration_result": {
            "system": "mulesoft_mock",
            "success": True,
            "old_status": "processing",
            "new_status": "shipped",
            "notes": "approved update",
            "decision": {
                "mismatch": True,
                "reason": "ERP behind portal",
                "action": "update_erp_status",
                "recommended_erp_status": "shipped",
                "requires_human": True,
                "trust_portal": True,
            },
        },
        "plan": ["research_order", "check_vendor_portal"],
        "confidence": 0.92,
        "human_decision": "approved",
        "human_notes": "looks good",
        "approved_by": "personb@opsforge.ai",
        "messages": [],
        "agents_executed": ["planner", "research", "browser", "integration"],
        "error": None,
        "notification_result": {},
        "status": "investigating",
        "report": "",
        "report_structured": {},
    }

    out = await reporting_node(state)

    assert out.get("error") is None
    assert "report" in out
    assert "report_structured" in out

    structured = out["report_structured"]
    assert structured["case"]["order_number"] == "ORD-10001"

    approved_by = _as_text(structured["case"].get("approved_by"))
    assert approved_by == "personb@opsforge.ai"

    assert structured["decision_policy"]["recommended_erp_status"] == "shipped"

    report = out["report"]
    assert "ORD-10001" in report
    assert ("personb@opsforge.ai" in report) or ("Approved By" in report)