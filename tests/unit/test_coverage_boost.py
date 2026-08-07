import pytest
from pydantic import ValidationError

from app.decision_rules import compute_confidence, evaluate_mismatch, decision_to_dict
from app.execution_handler import _map_status, _safe_confidence
from app.models import ExecutionStatus
from app.mock_portal import portal_status_for
from app.schemas import SimulateEventRequest, HumanDecisionRequest, UserCreate


def test_map_status_all_values():
    assert _map_status("pending") == ExecutionStatus.PENDING
    assert _map_status("running") == ExecutionStatus.RUNNING
    assert _map_status("investigating") == ExecutionStatus.RUNNING
    assert _map_status("waiting_human") == ExecutionStatus.WAITING_HUMAN
    assert _map_status("completed") == ExecutionStatus.COMPLETED
    assert _map_status("failed") == ExecutionStatus.FAILED
    assert _map_status(None) == ExecutionStatus.COMPLETED
    assert _map_status("UNKNOWN") == ExecutionStatus.FAILED


def test_safe_confidence_values():
    assert _safe_confidence(0.92) == 0.92
    assert _safe_confidence("0.5") == 0.5
    assert _safe_confidence(None) is None
    assert _safe_confidence("bad") is None


def test_compute_confidence_branches():
    assert compute_confidence(erp_found=True, browser_success=False, mismatch=False, portal_status=None) == 0.35
    assert compute_confidence(erp_found=False, browser_success=True, mismatch=False, portal_status="In Transit") == 0.58
    assert compute_confidence(erp_found=True, browser_success=True, mismatch=True, portal_status="In Transit") == 0.92
    assert compute_confidence(erp_found=True, browser_success=True, mismatch=False, portal_status="In Transit") == 0.84


def test_evaluate_mismatch_browser_fail():
    d = evaluate_mismatch(
        erp_status="processing",
        portal_status="In Transit",
        browser_success=False,
        severity="low",
        exception_type="vendor_status_mismatch",
        erp_found=True,
    )
    assert d.action == "keep_erp_status"
    assert d.requires_human is True
    assert decision_to_dict(d)["action"] == "keep_erp_status"


def test_evaluate_mismatch_erp_not_found():
    d = evaluate_mismatch(
        erp_status=None,
        portal_status="In Transit",
        browser_success=True,
        severity="medium",
        exception_type="vendor_status_mismatch",
        erp_found=False,
    )
    assert d.action == "keep_erp_status"
    assert "not found" in d.reason.lower()


def test_portal_status_rules():
    assert portal_status_for("ORD-10001")[0] == "In Transit"
    assert portal_status_for("ORD-10002")[0] == "Out for Delivery"
    assert portal_status_for("ORD-10003")[0] == "Delivered"
    assert portal_status_for("ORD-10004")[0] == "Exception - Address Issue"
    assert portal_status_for("ORD-10001", "shipping_delay")[0] == "Delayed"
    assert portal_status_for("ORD-10001", "inventory_shortage")[0] == "On Hold - Inventory"


def test_simulate_schema_valid_and_invalid():
    ok = SimulateEventRequest(
        order_number="ORD-10001",
        exception_type="vendor_status_mismatch",
        severity="high",
        description="valid simulate schema coverage payload",
    )
    assert ok.order_number == "ORD-10001"

    with pytest.raises(ValidationError):
        SimulateEventRequest(
            order_number="ORD-10001",
            exception_type="not_valid_type",
            severity="high",
            description="x",
        )


def test_human_decision_and_user_create_schema():
    h = HumanDecisionRequest(decision="approved", notes="ok")
    assert h.decision == "approved"

    u = UserCreate(
        email="coverage.user@opsforge.ai",
        password="OpsForge@123",
        full_name="Coverage User",
    )
    assert u.email.endswith("@opsforge.ai")