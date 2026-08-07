from datetime import datetime, timezone
from typing import Any, Dict, Optional
from app.decorators import async_log, langsmith_trace
from app.email_service import send_email


def _event(state: Dict[str, Any]) -> Dict[str, Any]:
    return state.get("event") or {}


def build_hitl_email(state: Dict[str, Any]) -> Dict[str, str]:
    event = _event(state)
    research = state.get("research_data") or {}
    browser = state.get("browser_evidence") or {}
    integ = state.get("integration_result") or {}
    decision = integ.get("decision") or {}

    order_number = event.get("order_number", "UNKNOWN")
    severity = event.get("severity", "n/a")
    exception_type = event.get("exception_type", "n/a")
    erp_status = (research.get("order") or {}).get("status", "n/a")
    portal_status = browser.get("portal_status", "n/a")
    reason = decision.get("reason") or "Human approval required."
    recommended = decision.get("recommended_erp_status") or "n/a"
    confidence = state.get("confidence", decision.get("confidence", "n/a"))
    thread_id = state.get("thread_id", "n/a")

    subject = f"[OpsForge][ACTION REQUIRED] {order_number} needs approval (severity={severity})"
    body = f"""OpsForge HITL Alert

A case requires human approval.

Thread ID: {thread_id}
Order: {order_number}
Exception: {exception_type}
Severity: {severity}
Confidence: {confidence}

Evidence
- ERP status: {erp_status}
- Portal status: {portal_status}

Policy
- Reason: {reason}
- Recommended ERP status: {recommended}
- Action: {decision.get('action', 'n/a')}

Please review and approve/reject in OpsForge Console.
"""
    return {"subject": subject, "body": body}

@langsmith_trace(name="build_final_email")
def build_final_email(state: Dict[str, Any]) -> Dict[str, str]:
    event = _event(state)
    integ = state.get("integration_result") or {}
    decision = integ.get("decision") or {}
    research = state.get("research_data") or {}
    browser = state.get("browser_evidence") or {}
    order = research.get("order") or {}

    order_number = event.get("order_number", "UNKNOWN")
    severity = event.get("severity", "n/a")
    exception_type = event.get("exception_type", "n/a")
    human_decision = state.get("human_decision") or "auto"
    approved_by = state.get("approved_by") or "system"
    notes = state.get("human_notes") or "n/a"
    old_status = integ.get("old_status", "n/a")
    new_status = integ.get("new_status", "n/a")
    recommended = decision.get("recommended_erp_status") or "n/a"
    action = decision.get("action") or "n/a"
    thread_id = state.get("thread_id", "n/a")
    confidence = state.get("confidence", "n/a")
    portal_status = browser.get("portal_status") or integ.get("portal_status") or "n/a"
    erp_before = integ.get("erp_status_before") or order.get("status") or old_status or "n/a"
    applied_after_approval = integ.get("applied_after_approval")
    agents = state.get("agents_executed") or []

    decision_l = str(human_decision).lower()

    # Post-decision reason: never keep "Human approval required..." wording
    if decision_l == "approved":
        outcome = (
            f"Approved by {approved_by}. "
            f"ERP status changed from '{old_status}' to '{new_status}'."
        )
        reason = (
            f"Human approved the investigation. "
            f"Recommended ERP status was '{recommended}'. "
            f"Final ERP integration status is now '{new_status}' "
            f"(previous '{old_status}'). "
            f"Portal evidence: '{portal_status}'."
        )
    elif decision_l == "rejected":
        outcome = (
            f"Rejected by {approved_by}. "
            f"ERP status left unchanged at '{old_status}'."
        )
        reason = (
            f"Human rejected the recommended ERP update to '{recommended}'. "
            f"ERP remains '{old_status}'. Portal evidence: '{portal_status}'."
        )
    else:
        outcome = f"Auto-completed. ERP status {old_status} -> {new_status}."
        reason = (
            f"Case completed without human approval. "
            f"Policy action='{action}', recommended='{recommended}'. "
            f"Final ERP status '{new_status}' (from '{old_status}'). "
            f"Portal evidence: '{portal_status}'."
        )

    subject = f"[OpsForge][COMPLETED] {order_number} ({human_decision})"
    body = f"""OpsForge Final Notification

Thread ID: {thread_id}
Order: {order_number}
Exception Type: {exception_type}
Severity: {severity}
Confidence: {confidence}
Agents: {' -> '.join(agents) if agents else 'n/a'}

Evidence Snapshot
- ERP before: {erp_before}
- Portal status: {portal_status}
- Integration old status: {old_status}
- Integration new status: {new_status}
- Recommended ERP status: {recommended}
- Policy action: {action}
- Applied after approval: {applied_after_approval}

Outcome
- {outcome}
- Human notes: {notes}

Final reason
- {reason}

This message was sent automatically by OpsForge.
"""
    return {"subject": subject, "body": body}

@langsmith_trace(name="send_hitl_alert", run_type="tool")
async def send_hitl_alert(state: Dict[str, Any]) -> Dict[str, Any]:
    content = build_hitl_email(state)
    result = await send_email(content["subject"], content["body"])
    return {
        "type": "hitl_alert",
        "channel": "email",
        **result,
    }


async def send_final_notification(state: Dict[str, Any]) -> Dict[str, Any]:
    content = build_final_email(state)
    result = await send_email(content["subject"], content["body"])
    return {
        "type": "final_notification",
        "channel": "email",
        **result,
    }