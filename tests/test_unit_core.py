import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.auth import get_password_hash, verify_password, create_access_token
from app.execution_handler import _map_status, _safe_confidence
from app.models import (
    ExecutionStatus,
    OrderStatus,
    ExceptionType,
    ExceptionSeverity,
    ExceptionStatus,
    User,
    Order,
    OrderException,
    AgentExecution,
    VendorStatus,
    IntegrationLog,
)
from app.schemas import SimulateEventRequest, HumanDecisionRequest, UserCreate
from app.agents.graph import should_continue_after_planner, should_go_to_human


def test_settings_core_fields():
    s = get_settings()
    assert s.database_url
    assert s.kafka_bootstrap_servers
    assert s.openai_model
    assert s.app_name


def test_password_hash_and_verify():
    h = get_password_hash("OpsForge@123")
    assert verify_password("OpsForge@123", h) is True
    assert verify_password("wrong", h) is False


def test_create_access_token():
    token = create_access_token({"sub": "admin@opsforge.ai"})
    assert isinstance(token, str)
    assert len(token.split(".")) == 3


def test_status_mapping_matrix():
    assert _map_status("pending") == ExecutionStatus.PENDING
    assert _map_status("running") == ExecutionStatus.RUNNING
    assert _map_status("investigating") == ExecutionStatus.RUNNING
    assert _map_status("waiting_human") == ExecutionStatus.WAITING_HUMAN
    assert _map_status("completed") == ExecutionStatus.COMPLETED
    assert _map_status("failed") == ExecutionStatus.FAILED
    assert _map_status(None) == ExecutionStatus.COMPLETED
    assert _map_status("UNKNOWN") == ExecutionStatus.FAILED


def test_safe_confidence_values():
    assert _safe_confidence(0.88) == 0.88
    assert _safe_confidence("0.5") == 0.5
    assert _safe_confidence(None) is None
    assert _safe_confidence("x") is None


def test_schema_simulate_valid():
    p = SimulateEventRequest(
        order_number="ORD-10001",
        exception_type="vendor_status_mismatch",
        severity="high",
        description="valid simulate schema coverage path for unit tests",
    )
    assert p.severity == "high"


def test_schema_simulate_invalid():
    with pytest.raises(ValidationError):
        SimulateEventRequest(
            order_number="ORD-10001",
            exception_type="bad",
            severity="high",
            description="x",
        )


def test_schema_human_decision():
    p = HumanDecisionRequest(decision="approved", notes="n")
    assert p.decision == "approved"


def test_schema_user_create():
    payload = UserCreate(
        email="unit.tester@opsforge.ai",
        password="OpsForge@123",
        full_name="Unit Tester",
    )
    assert payload.email == "unit.tester@opsforge.ai"
    assert payload.full_name == "Unit Tester"


def test_model_tablenames():
    assert User.__tablename__ == "users"
    assert Order.__tablename__ == "orders"
    assert OrderException.__tablename__ == "order_exceptions"
    assert AgentExecution.__tablename__ == "agent_executions"
    assert VendorStatus.__tablename__ == "vendor_status"
    assert IntegrationLog.__tablename__ == "integration_logs"


def test_enum_values():
    assert OrderStatus.PROCESSING.value == "processing"
    assert ExceptionType.VENDOR_STATUS_MISMATCH.value == "vendor_status_mismatch"
    assert ExceptionSeverity.CRITICAL.value == "critical"
    assert ExceptionStatus.OPEN.value == "open"
    assert ExecutionStatus.FAILED.value == "failed"


def test_graph_routing_helpers():
    assert should_continue_after_planner({"plan": ["research_order"]}) == "research"
    assert should_continue_after_planner({"plan": ["check_vendor_portal"]}) == "browser"
    assert should_continue_after_planner({"plan": ["done"]}) == "end"

    assert should_go_to_human({"confidence": 0.5, "event": {"severity": "low"}}) == "human_review"
    assert should_go_to_human({"confidence": 0.9, "event": {"severity": "high"}}) == "human_review"
    assert should_go_to_human({"confidence": 0.9, "event": {"severity": "low"}}) == "reporting"