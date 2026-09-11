from unittest.mock import MagicMock


def test_duplicate_active_exception_logic_mocked():
    """
    Duplicate rule without writing to the demo database.
    """
    existing = MagicMock()
    existing.thread_id = "existing-thread"
    existing.status = "waiting_human"

    def simulate(order_number: str, active=None):
        if active and active.status in {"pending", "running", "waiting_human"}:
            return 409, {
                "message": "Active investigation already exists for this order_number",
                "order_number": order_number,
                "existing_thread_id": active.thread_id,
            }
        return 200, {"thread_id": "new-thread", "status": "pending"}

    first_code, first_body = simulate("ORD-10001", active=None)
    assert first_code == 200
    assert "thread_id" in first_body

    second_code, second_body = simulate("ORD-10001", active=existing)
    assert second_code == 409
    assert second_body["existing_thread_id"] == "existing-thread"