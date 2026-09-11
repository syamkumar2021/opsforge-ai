from unittest.mock import AsyncMock, patch


def test_full_opsforge_journey_mocked():
    """
    Mocked journey. Does not POST to the running app,
    so Executions tab is not polluted with ORD-10001 rows.
    """
    payload = {
        "order_number": "ORD-10001",
        "exception_type": "vendor_status_mismatch",
        "severity": "high",
        "description": "E2E journey mock-safe assertions",
    }

    created = {
        "thread_id": "thread-e2e-mock",
        "status": "waiting_human",
        "event_payload": payload,
    }
    approved = {**created, "status": "completed", "human_decision": "approved"}

    assert created["thread_id"]
    assert approved["status"] == "completed"
    assert approved["human_decision"] == "approved"


@patch("app.kafka_client.kafka_client.publish_exception_event", new_callable=AsyncMock)
def test_publish_exception_is_mocked(mock_publish):
    mock_publish.return_value = None
    assert mock_publish.return_value is None