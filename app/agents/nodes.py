import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agents.state import AgentState
from app.agents.tools import (
    get_exception_context,
    get_order_details,
    save_vendor_status,
)
from app.config import get_settings
from app.decorators import async_log, langsmith_trace
from app.mulesoft import update_order_in_erp
from app.decision_rules import compute_confidence

logger = logging.getLogger(__name__)
settings = get_settings()

llm = ChatOpenAI(
    model=settings.openai_model,
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    temperature=0.1,
)


def _with_agent(state: AgentState, agent_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Append agent name to agents_executed list."""
    agents: List[str] = list(state.get("agents_executed") or [])
    if agent_name not in agents:
        agents.append(agent_name)
    payload["agents_executed"] = agents
    return payload


@async_log
@langsmith_trace(name="node_planner")
async def planner_node(state: AgentState) -> Dict[str, Any]:
    """Planner Agent: create investigation plan."""
    try:
        event = state["event"]
        system_prompt = (
            "You are the Planner Agent in an enterprise operations system. "
            "Analyze the exception event and create a clear step-by-step investigation plan. "
            "Return only a JSON list of steps. "
            'Example: ["research_order", "check_vendor_portal", "generate_report"]'
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Exception Event:\n{json.dumps(event, indent=2)}"),
        ]
        response = await llm.ainvoke(messages)
        plan_text = (response.content or "").strip()

        try:
            plan = json.loads(plan_text)
            if not isinstance(plan, list):
                plan = ["research_order", "check_vendor_portal", "generate_report"]
        except Exception:
            plan = ["research_order", "check_vendor_portal", "generate_report"]

        return _with_agent(
            state,
            "planner",
            {
                "plan": plan,
                "status": "investigating",
                "error": None,
                "messages": [AIMessage(content=f"Plan created: {plan}")],
            },
        )
    except Exception as e:
        logger.exception(f"Planner node failed: {e}")
        return _with_agent(
            state,
            "planner",
            {
                "status": "failed",
                "error": str(e),
                "messages": [AIMessage(content=f"Planner node failed: {str(e)}")],
            },
        )


@async_log
@langsmith_trace(name="node_research")
async def research_node(state: AgentState) -> Dict[str, Any]:
    """Research Agent: load order + exception context from PostgreSQL."""
    try:
        order_number = state["event"].get("order_number", "UNKNOWN")
        order_data = await get_order_details.ainvoke({"order_number": order_number})
        exception_data = await get_exception_context.ainvoke({"order_number": order_number})
        research_data = {"order": order_data, "exception": exception_data}

        return _with_agent(
            state,
            "research",
            {
                "research_data": research_data,
                "error": None,
                "messages": [AIMessage(content="Research completed successfully.")],
            },
        )
    except Exception as e:
        logger.exception(f"Research node failed: {e}")
        return _with_agent(
            state,
            "research",
            {
                "status": "failed",
                "error": str(e),
                "messages": [AIMessage(content=f"Research node failed: {str(e)}")],
            },
        )


@async_log
@langsmith_trace(name="node_browser")
async def browser_node(state: AgentState) -> Dict[str, Any]:
    """Browser Agent: collect portal evidence using Playwright."""
    try:
        from app.browser_agent import browser_agent
        from app.decision_rules import compute_confidence

        order_number = state["event"].get("order_number", "UNKNOWN")
        tracking_number = (
            state.get("research_data", {}).get("order", {}).get("tracking_number")
        )

        evidence = await browser_agent.check_vendor_status(
            order_number=order_number,
            tracking_number=tracking_number,
            exception_type=state["event"].get("exception_type"),
        )

        # Truncate raw text for clean demos/API responses
        raw = evidence.get("raw_text") or ""
        if len(raw) > 300:
            evidence["raw_text"] = raw[:300] + "..."

        await save_vendor_status.ainvoke(
            {
                "order_number": order_number,
                "portal_status": evidence.get("portal_status"),
                "tracking_number": evidence.get("tracking_number"),
                "raw_evidence": evidence,
            }
        )

        # Evidence-based confidence (not a flat 0.88)
        erp_found = bool(
            (state.get("research_data") or {}).get("order", {}).get("found", True)
        )
        confidence = compute_confidence(
            erp_found=erp_found,
            browser_success=bool(evidence.get("success")),
            mismatch=False,  # final mismatch confidence is refined in integration node
            portal_status=evidence.get("portal_status"),
        )

        return _with_agent(
            state,
            "browser",
            {
                "browser_evidence": evidence,
                "confidence": confidence,
                "error": None,
                "messages": [
                    AIMessage(
                        content=(
                            f"Browser agent finished. Status: {evidence.get('portal_status')}, "
                            f"confidence: {confidence}"
                        )
                    )
                ],
            },
        )
    except Exception as e:
        logger.exception(f"Browser node failed: {e}")
        return _with_agent(
            state,
            "browser",
            {
                "status": "failed",
                "error": str(e),
                "confidence": 0.35,
                "messages": [AIMessage(content=f"Browser node failed: {str(e)}")],
            },
        )

@async_log
@langsmith_trace(name="node_integration")
async def integration_node(state: AgentState) -> Dict[str, Any]:
    """
    Integration Agent:
    - Evaluate ERP vs Vendor Portal evidence using decision rules
    - If HITL required: do NOT update ERP yet
    - If auto path: apply recommended ERP status via MuleSoft mock
    """
    try:
        from app.decision_rules import decision_to_dict, evaluate_mismatch

        order_number = state["event"].get("order_number", "UNKNOWN")
        thread_id = state.get("thread_id", "unknown")
        severity = state["event"].get("severity", "medium")
        exception_type = state["event"].get("exception_type", "other")

        research = state.get("research_data", {}) or {}
        evidence = state.get("browser_evidence", {}) or {}

        erp_status = (research.get("order") or {}).get("status")
        portal_status = evidence.get("portal_status")
        browser_success = bool(evidence.get("success"))
        confidence = float(state.get("confidence") or 0.0)

        decision = evaluate_mismatch(
            erp_status=erp_status,
            portal_status=portal_status,
            browser_success=browser_success,
            severity=severity,
            exception_type=exception_type,
            confidence=confidence,
        )
        decision_dict = decision_to_dict(decision)

        if decision.requires_human:
            # Pending approval: keep ERP unchanged
            result = {
                "success": True,
                "system": "mulesoft_mock",
                "order_number": order_number,
                "old_status": erp_status,
                "new_status": erp_status,
                "notes": f"{decision.reason} | Pending human approval before ERP status change.",
                "updated_at": None,
                "extra_data": {
                    "thread_id": thread_id,
                    "decision": decision_dict,
                    "portal_status": portal_status,
                    "erp_status_before": erp_status,
                },
            }
        else:
            # Auto path: apply recommended status now
            new_status = decision.recommended_erp_status or erp_status
            from app.agents.tools import update_order_status

            result = await update_order_status.ainvoke(
                {
                    "order_number": order_number,
                    "new_status": new_status,
                    "notes": decision.reason,
                    "extra_data": {
                        "thread_id": thread_id,
                        "decision": decision_dict,
                        "portal_status": portal_status,
                        "erp_status_before": erp_status,
                    },
                }
            )

        integration_result = {
            **result,
            "decision": decision_dict,
            "portal_status": portal_status,
            "erp_status_before": erp_status,
            "applied_after_approval": False,
        }

        return _with_agent(
            state,
            "integration",
            {
                "integration_result": integration_result,
                "confidence": float(decision_dict.get("confidence") or confidence),
                "error": None,
                "messages": [
                    AIMessage(
                        content=(
                            "Integration agent evaluated decision rules. "
                            f"action={decision.action}, "
                            f"recommended={decision.recommended_erp_status}, "
                            f"requires_human={decision.requires_human}"
                        )
                    )
                ],
            },
        )
    except Exception as e:
        logger.exception(f"Integration node failed: {e}")
        return _with_agent(
            state,
            "integration",
            {
                "status": "failed",
                "error": str(e),
                "messages": [AIMessage(content=f"Integration node failed: {str(e)}")],
            },
        )


@async_log
@langsmith_trace(name="node_reporting")
async def reporting_node(state: AgentState) -> Dict[str, Any]:
    """Reporting Agent: detailed multi-agent investigation report with post-decision accuracy."""
    try:
        event = state.get("event", {}) or {}
        research = state.get("research_data", {}) or {}
        browser = state.get("browser_evidence", {}) or {}
        integration = state.get("integration_result", {}) or {}
        order = research.get("order", {}) or {}
        exception = research.get("exception", {}) or {}
        decision_policy = integration.get("decision", {}) or {}
        agents = state.get("agents_executed") or []
        plan_lines = state.get("plan") or []

        order_number = event.get("order_number") or order.get("order_number") or "UNKNOWN"
        exception_type = event.get("exception_type") or exception.get("exception_type") or "N/A"
        severity = event.get("severity") or exception.get("severity") or "N/A"
        confidence = state.get("confidence", 0.0)

        human_decision = state.get("human_decision")
        human_notes = state.get("human_notes") or "None"
        approved_by = state.get("approved_by") or "N/A"
        if isinstance(approved_by, (tuple, list)):
            approved_by = approved_by[0] if approved_by else "N/A"
        approved_by = str(approved_by)

        portal_status = browser.get("portal_status") or integration.get("portal_status") or "N/A"
        erp_status_before = (
            integration.get("erp_status_before")
            or order.get("status")
            or "N/A"
        )
        tracking = browser.get("tracking_number") or order.get("tracking_number") or "Not available"
        eta = browser.get("eta") or "Not available"
        exception_description = exception.get("description") or event.get("description") or "N/A"

        policy_reason = decision_policy.get("reason")
        policy_action = decision_policy.get("action", "N/A")
        recommended_erp_status = decision_policy.get("recommended_erp_status")
        requires_human = decision_policy.get("requires_human")
        trust_portal = decision_policy.get("trust_portal")
        mismatch = decision_policy.get("mismatch")

        old_status = integration.get("old_status")
        new_status = integration.get("new_status")
        applied_after_approval = integration.get("applied_after_approval")

        # Original policy reason (investigation-time)
        original_policy_reason = policy_reason or (
            f"ERP status='{erp_status_before}', portal status='{portal_status}'. "
            f"Tracking={tracking}, ETA={eta}."
        )

        # Post-decision root cause / conclusion
        decision_l = str(human_decision or "").lower()
        if decision_l == "approved":
            root_cause = (
                f"Human approved the recommendation. "
                f"ERP status updated from '{old_status}' to '{new_status}'. "
                f"Original policy recommendation was '{recommended_erp_status}'. "
                f"Original policy note: {original_policy_reason}"
            )
            recommendation = (
                f"Approved ERP update applied: '{old_status}' -> '{new_status}' "
                f"(recommended='{recommended_erp_status}', action={policy_action})."
            )
            conclusion = (
                f"Order {order_number}: approved by {approved_by}. "
                f"Final ERP status updated from '{old_status}' to '{new_status}'."
            )
            requires_human_display = False
        elif decision_l == "rejected":
            root_cause = (
                f"Human rejected the recommendation. "
                f"ERP status left unchanged at '{old_status or erp_status_before}'. "
                f"Original policy recommendation was '{recommended_erp_status}'. "
                f"Original policy note: {original_policy_reason}"
            )
            recommendation = (
                f"No ERP update applied due to rejection. "
                f"ERP remains '{old_status or erp_status_before}'."
            )
            conclusion = (
                f"Order {order_number}: rejected by {approved_by}. "
                f"ERP status remains '{old_status or erp_status_before}'."
            )
            requires_human_display = False
        else:
            # Auto-completed path (no HITL decision)
            if old_status and new_status and str(old_status) != str(new_status):
                root_cause = (
                    f"Auto-completed by policy. "
                    f"ERP updated from '{old_status}' to '{new_status}'. "
                    f"Policy note: {original_policy_reason}"
                )
                recommendation = (
                    f"Auto ERP update applied: '{old_status}' -> '{new_status}' "
                    f"(action={policy_action})."
                )
                conclusion = (
                    f"Order {order_number}: auto-completed. "
                    f"ERP status updated from '{old_status}' to '{new_status}'."
                )
            else:
                root_cause = original_policy_reason
                recommendation = (
                    f"No ERP status change applied (action={policy_action}). "
                    f"ERP remains '{old_status or erp_status_before}'."
                )
                conclusion = (
                    f"Order {order_number}: auto-completed. "
                    f"ERP remains '{old_status or erp_status_before}'."
                )
            requires_human_display = bool(requires_human)

        plan_md = "\n".join([f"- {step}" for step in plan_lines]) or "- No plan available"
        agents_md = " -> ".join(agents) if agents else "N/A"

        # Per-agent outcome summary
        planner_outcome = f"Created plan with {len(plan_lines)} step(s)."
        research_outcome = (
            f"ERP order found={order.get('found')}, status='{order.get('status', 'N/A')}', "
            f"customer='{order.get('customer_email', 'N/A')}', amount={order.get('total_amount', 'N/A')} {order.get('currency', '')}."
        )
        browser_outcome = (
            f"Portal status='{portal_status}', tracking='{tracking}', eta='{eta}', "
            f"success={browser.get('success', False)}, source={browser.get('source', 'playwright')}."
        )
        integration_outcome = (
            f"System={integration.get('system', 'N/A')}, success={integration.get('success', False)}, "
            f"old='{old_status}', new='{new_status}', applied_after_approval={applied_after_approval}."
        )
        decision_outcome = (
            f"mismatch={mismatch}, action={policy_action}, recommended='{recommended_erp_status}', "
            f"trust_portal={trust_portal}, confidence={decision_policy.get('confidence', confidence)}."
        )

        report = f"""OpsForge Investigation Report

1) Case Summary
- Thread ID: {state.get('thread_id')}
- Order Number: {order_number}
- Exception Type: {exception_type}
- Severity: {severity}
- Confidence Score: {confidence}
- Human Decision: {human_decision or 'auto'}
- Human Notes: {human_notes}
- Approved By: {approved_by}
- Agents Executed: {agents_md}

2) Root Cause / Final Reason
- {root_cause}
- Original Exception Description: {exception_description}

3) Evidence Details
- ERP Status (before decision): {erp_status_before}
- Portal Status: {portal_status}
- Tracking Number: {tracking}
- ETA: {eta}
- Browser Evidence Source: {browser.get('source', 'playwright')}
- Browser Collection Success: {browser.get('success', False)}
- Customer: {order.get('customer_email', 'N/A')} ({order.get('customer_id', 'N/A')})
- Vendor ID: {order.get('vendor_id', 'N/A')}
- Order Amount: {order.get('total_amount', 'N/A')} {order.get('currency', '')}
- Shipping Address: {order.get('shipping_address', 'N/A')}
- Items: {order.get('items', 'N/A')}

4) Agent Outcomes
- Planner: {planner_outcome}
- Research: {research_outcome}
- Browser: {browser_outcome}
- Decision Policy: {decision_outcome}
- Integration: {integration_outcome}

5) Decision Policy Output
- Mismatch Detected: {mismatch}
- Trust Portal Evidence: {trust_portal}
- Requires Human Approval (at decision time): {requires_human}
- Requires Human Approval (final): {requires_human_display}
- Policy Action: {policy_action}
- Recommended ERP Status: {recommended_erp_status}
- Policy Reason (investigation-time): {original_policy_reason}

6) Integration Action (MuleSoft Mock)
- System: {integration.get('system', 'N/A')}
- Success: {integration.get('success', False)}
- Old Status: {old_status}
- New Status: {new_status}
- Applied After Approval: {applied_after_approval}
- Integration Notes: {integration.get('notes', 'N/A')}

7) Recommendation / Final Action
- {recommendation}

8) Investigation Plan
{plan_md}

9) Final Conclusion
- {conclusion}
"""

        report_structured = {
            "title": "OpsForge Investigation Report",
            "case": {
                "thread_id": state.get("thread_id"),
                "order_number": order_number,
                "exception_type": exception_type,
                "severity": severity,
                "confidence": confidence,
                "human_decision": human_decision or "auto",
                "human_notes": human_notes,
                "approved_by": approved_by,
                "agents_executed": agents,
            },
            "root_cause": root_cause,
            "exception_description": exception_description,
            "evidence": {
                "erp_status_before": erp_status_before,
                "portal_status": portal_status,
                "tracking_number": tracking,
                "eta": eta,
                "browser_source": browser.get("source", "playwright"),
                "browser_success": browser.get("success", False),
                "customer_email": order.get("customer_email"),
                "customer_id": order.get("customer_id"),
                "vendor_id": order.get("vendor_id"),
                "order_amount": order.get("total_amount"),
                "currency": order.get("currency"),
                "shipping_address": order.get("shipping_address"),
                "items": order.get("items"),
            },
            "agent_outcomes": {
                "planner": planner_outcome,
                "research": research_outcome,
                "browser": browser_outcome,
                "decision_policy": decision_outcome,
                "integration": integration_outcome,
            },
            "decision_policy": {
                "mismatch": mismatch,
                "trust_portal": trust_portal,
                "requires_human_at_decision_time": requires_human,
                "requires_human_final": requires_human_display,
                "action": policy_action,
                "recommended_erp_status": recommended_erp_status,
                "reason_investigation_time": original_policy_reason,
                "reason_final": root_cause,
                "confidence": decision_policy.get("confidence", confidence),
            },
            "integration": {
                "system": integration.get("system"),
                "success": integration.get("success"),
                "old_status": old_status,
                "new_status": new_status,
                "notes": integration.get("notes"),
                "applied_after_approval": applied_after_approval,
            },
            "recommendation": recommendation,
            "plan": plan_lines,
            "conclusion": conclusion,
        }

        return _with_agent(
            state,
            "reporting",
            {
                "report": report.strip(),
                "report_structured": report_structured,
                "status": "completed",
                "error": None,
                "messages": [AIMessage(content="Detailed multi-agent final report generated.")],
            },
        )
    except Exception as e:
        logger.exception(f"Reporting node failed: {e}")
        return _with_agent(
            state,
            "reporting",
            {
                "status": "failed",
                "error": str(e),
                "messages": [AIMessage(content=f"Reporting node failed: {str(e)}")],
            },
        )


@async_log
@langsmith_trace(name="node_human_review")
async def human_review_node(state: AgentState) -> Dict[str, Any]:
    """Human-in-the-Loop node."""
    try:
        decision = state.get("human_decision")
        notes = state.get("human_notes")

        if decision:
            return _with_agent(
                state,
                "human_review",
                {
                    "status": "investigating",
                    "error": None,
                    "messages": [
                        AIMessage(
                            content=f"Human decision received: {decision}. Notes: {notes or 'None'}"
                        )
                    ],
                },
            )

        return _with_agent(
            state,
            "human_review",
            {
                "status": "waiting_human",
                "error": None,
                "messages": [AIMessage(content="Waiting for human approval...")],
            },
        )
    except Exception as e:
        logger.exception(f"Human review node failed: {e}")
        return _with_agent(
            state,
            "human_review",
            {
                "status": "failed",
                "error": str(e),
                "messages": [AIMessage(content=f"Human review node failed: {str(e)}")],
            },
        )


@async_log
@langsmith_trace(name="node_notification")
async def notification_node(state: AgentState) -> Dict[str, Any]:
    """Notification Agent: send final autonomous email after investigation completion."""
    try:
        from app.notify import send_final_notification

        mail = await send_final_notification(state)

        notification_result = {
            **(state.get("notification_result") or {}),
            "final_email": mail,
            "sent_at": mail.get("sent_at"),
        }

        return _with_agent(
            state,
            "notification",
            {
                "notification_result": notification_result,
                "status": "completed",
                "error": None,
                "messages": [
                    AIMessage(
                        content=(
                            "Notification Agent: final email "
                            f"status={mail.get('status')} to={mail.get('to')}"
                        )
                    )
                ],
            },
        )
    except Exception as e:
        logger.exception(f"Notification node failed: {e}")
        return _with_agent(
            state,
            "notification",
            {
                "status": "failed",
                "error": str(e),
                "messages": [AIMessage(content=f"Notification node failed: {str(e)}")],
            },
        )