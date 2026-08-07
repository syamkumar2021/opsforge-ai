import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.email_service import send_email, _as_recipients
from app.notify import (
    build_hitl_email,
    build_final_email,
    send_hitl_alert,
    send_final_notification,
)


def test_as_recipients_string_and_list():
    assert _as_recipients("a@x.com, b@y.com") == ["a@x.com", "b@y.com"]
    assert _as_recipients(["a@x.com", " b@y.com "]) == ["a@x.com", "b@y.com"]
    assert _as_recipients("") == []


@pytest.mark.asyncio
async def test_send_email_success():
    with patch("app.email_service.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = None
        result = await send_email(
            subject="Test subject",
            body="Test body",
            to="ops-team@company.com",
        )
    assert result["status"] == "sent"
    assert result["to"] == ["ops-team@company.com"]
    assert result["subject"] == "Test subject"
    assert "sent_at" in result
    mock_send.assert_awaited()


@pytest.mark.asyncio
async def test_send_email_no_recipients():
    with patch("app.email_service.settings") as settings:
        settings.notify_email_to = ""
        settings.smtp_from = "opsforge@local.test"
        settings.smtp_host = "mailpit"
        settings.smtp_port = 1025
        settings.smtp_user = ""
        settings.smtp_password = ""
        settings.smtp_tls = False
        result = await send_email(subject="X", body="Y", to="")
    assert result["status"] == "failed"
    assert result["error"] == "No recipients configured"


@pytest.mark.asyncio
async def test_send_email_smtp_failure():
    with patch(
        "app.email_service.aiosmtplib.send",
        new_callable=AsyncMock,
        side_effect=Exception("smtp down"),
    ):
        result = await send_email(
            subject="Test subject",
            body="Test body",
            to="ops-team@company.com",
        )
    assert result["status"] == "failed"
    assert "smtp down" in result["error"]


def _sample_state(**overrides):
    base = {
        "thread_id": "t-1",
        "event": {
            "order_number": "ORD-10001",
            "severity": "high",
            "exception_type": "vendor_status_mismatch",
            "description": "mismatch case",
        },
        "confidence": 0.91,
        "human_decision": None,
        "human_notes": None,
        "approved_by": None,
        "agents_executed": ["planner", "research", "browser", "integration"],
        "research_data": {"order": {"status": "processing", "found": True}},
        "browser_evidence": {
            "portal_status": "In Transit",
            "tracking_number": "TRK-1",
            "eta": "2026-08-10",
            "success": True,
        },
        "integration_result": {
            "old_status": "processing",
            "new_status": "processing",
            "erp_status_before": "processing",
            "portal_status": "In Transit",
            "applied_after_approval": False,
            "decision": {
                "action": "update_erp_status",
                "reason": "Mismatch confirmed",
                "recommended_erp_status": "shipped",
                "requires_human": True,
                "confidence": 0.91,
            },
        },
        "report": "OpsForge Investigation Report",
    }
    base.update(overrides)
    return base


def test_build_hitl_email_contains_action_required():
    content = build_hitl_email(_sample_state())
    assert "ACTION REQUIRED" in content["subject"]
    assert "ORD-10001" in content["body"]
    assert "Human approval" in content["body"] or "approval" in content["body"].lower()


def test_build_final_email_approved_wording():
    content = build_final_email(
        _sample_state(
            human_decision="approved",
            approved_by="admin@opsforge.ai",
            human_notes="ok",
            integration_result={
                "old_status": "processing",
                "new_status": "shipped",
                "erp_status_before": "processing",
                "portal_status": "In Transit",
                "applied_after_approval": True,
                "decision": {
                    "action": "update_erp_status",
                    "reason": "old pending text should not dominate",
                    "recommended_erp_status": "shipped",
                    "requires_human": False,
                },
            },
        )
    )
    assert "COMPLETED" in content["subject"]
    assert "approved" in content["body"].lower()
    assert "processing" in content["body"]
    assert "shipped" in content["body"]
    assert "Human approval required" not in content["body"]


def test_build_final_email_rejected_wording():
    content = build_final_email(
        _sample_state(
            human_decision="rejected",
            approved_by="admin@opsforge.ai",
            integration_result={
                "old_status": "processing",
                "new_status": "processing",
                "decision": {
                    "action": "update_erp_status",
                    "reason": "Mismatch confirmed",
                    "recommended_erp_status": "shipped",
                    "requires_human": False,
                },
            },
        )
    )
    assert "rejected" in content["body"].lower()
    assert "unchanged" in content["body"].lower() or "left unchanged" in content["body"].lower()


def test_build_final_email_auto_wording():
    content = build_final_email(
        _sample_state(
            human_decision=None,
            integration_result={
                "old_status": "processing",
                "new_status": "shipped",
                "decision": {
                    "action": "update_erp_status",
                    "reason": "Auto policy",
                    "recommended_erp_status": "shipped",
                    "requires_human": False,
                },
            },
        )
    )
    assert "Auto-completed" in content["body"] or "auto" in content["subject"].lower()


@pytest.mark.asyncio
async def test_send_hitl_alert_uses_email_service():
    with patch("app.notify.send_email", new_callable=AsyncMock) as mocked:
        mocked.return_value = {
            "status": "sent",
            "to": ["ops-team@company.com"],
            "subject": "HITL",
            "sent_at": "2026-08-03T00:00:00+00:00",
        }
        result = await send_hitl_alert(_sample_state())
    assert result["type"] == "hitl_alert"
    assert result["status"] == "sent"
    mocked.assert_awaited()


@pytest.mark.asyncio
async def test_send_final_notification_uses_email_service():
    with patch("app.notify.send_email", new_callable=AsyncMock) as mocked:
        mocked.return_value = {
            "status": "sent",
            "to": ["ops-team@company.com"],
            "subject": "FINAL",
            "sent_at": "2026-08-03T00:00:00+00:00",
        }
        result = await send_final_notification(
            _sample_state(human_decision="approved", approved_by="admin@opsforge.ai")
        )
    assert result["type"] == "final_notification"
    assert result["status"] == "sent"
    mocked.assert_awaited()