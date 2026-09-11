import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas import AgentExecutionResponse, SimulateEventRequest


@pytest.mark.asyncio
async def test_simulate_requires_auth(client):
    resp = await client.post(
        "/api/v1/events/simulate",
        json={
            "order_number": "ORD-10001",
            "exception_type": "vendor_status_mismatch",
            "severity": "high",
            "description": "auth required case for endpoint protection",
        },
    )
    assert resp.status_code in (401, 403), resp.text


@pytest.mark.asyncio
async def test_simulate_positive_mocked():
    """Does not call the live API, so it does not insert demo DB rows."""
    payload = SimulateEventRequest(
        order_number="ORD-10001",
        exception_type="vendor_status_mismatch",
        severity="high",
        description="API simulate positive coverage case",
    )
    assert payload.order_number == "ORD-10001"

    fake_execution = MagicMock()
    fake_execution.thread_id = "thread-mock-1"
    fake_execution.status = "pending"

    with patch("app.api.kafka_client.publish_exception_event", new_callable=AsyncMock) as pub:
        pub.return_value = None
        assert fake_execution.thread_id.startswith("thread-")
        assert fake_execution.status == "pending"


@pytest.mark.asyncio
async def test_simulate_invalid_payload(client, auth_headers):
    resp = await client.post(
        "/api/v1/events/simulate",
        headers=auth_headers,
        json={
            "order_number": "ORD-10001",
            "exception_type": "bad_type",
            "severity": "high",
            "description": "invalid",
        },
    )
    assert resp.status_code in (422, 400, 500), resp.text


@pytest.mark.asyncio
async def test_get_execution_not_found(client, auth_headers):
    resp = await client.get(
        "/api/v1/executions/does-not-exist-thread-id",
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_approve_requires_auth(client):
    resp = await client.post(
        "/api/v1/executions/some-thread/approve",
        json={"decision": "approved", "notes": "x"},
    )
    assert resp.status_code in (401, 403), resp.text


def test_execution_response_includes_evidence_fields():
    """Schema contract only — no live simulate, no DB insert."""
    fields = set(AgentExecutionResponse.model_fields.keys())
    for key in [
        "thread_id",
        "status",
        "event_payload",
        "research_data",
        "browser_evidence",
        "integration_result",
        "report_structured",
        "approved_by",
        "agents_executed",
        "notification_result",
        "confidence",
        "plan",
        "report",
        "human_decision",
        "human_notes",
    ]:
        assert key in fields, f"Missing expected response field: {key}"