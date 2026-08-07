import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from langchain_core.messages import HumanMessage
from sqlalchemy import select

from app.agents.graph import get_graph
from app.agents.state import AgentState
from app.config import get_settings
from app.db import get_db_context
from app.decorators import async_error_handler, async_log, langsmith_trace
from app.models import AgentExecution, ExecutionStatus

logger = logging.getLogger(__name__)
settings = get_settings()

STATUS_MAP = {
    "pending": ExecutionStatus.PENDING,
    "running": ExecutionStatus.RUNNING,
    "investigating": ExecutionStatus.RUNNING,
    "waiting_human": ExecutionStatus.WAITING_HUMAN,
    "completed": ExecutionStatus.COMPLETED,
    "failed": ExecutionStatus.FAILED,
}


def _map_status(raw_status: Optional[str]) -> ExecutionStatus:
    if not raw_status:
        return ExecutionStatus.COMPLETED
    return STATUS_MAP.get(str(raw_status).lower(), ExecutionStatus.FAILED)


def _safe_confidence(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _policy_reason(final_state: Dict[str, Any] | None) -> str:
    integ = (final_state or {}).get("integration_result") or {}
    decision = integ.get("decision") or {}
    return decision.get("reason") or "Investigation pending human approval"


@async_log
@async_error_handler()
@langsmith_trace(name="handle_exception_event")
async def handle_exception_event(event: Dict[str, Any]) -> None:
    """
    Main handler called by Kafka consumer.
    Starts a new LangGraph execution for the incoming exception event.
    """
    thread_id = event.get("thread_id") or str(uuid4())
    logger.info(f"Starting LangGraph execution | thread_id={thread_id}")

    graph = await get_graph()

    initial_state: AgentState = {
        "thread_id": thread_id,
        "event": event,
        "plan": [],
        "research_data": {},
        "browser_evidence": {},
        "integration_result": {},
        "report": "",
        "report_structured": {},
        "confidence": 0.0,
        "human_decision": None,
        "human_notes": None,
        "status": "running",  # graph state starts as running
        "messages": [HumanMessage(content=f"New exception event received: {event}")],
        "error": None,
        "agents_executed": [],
        "notification_result": {},
    }

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # -------------------------------------------------
        # CRITICAL: mark RUNNING in DB BEFORE graph starts
        # so UI lifecycle can move pending -> running early
        # -------------------------------------------------
        async with get_db_context() as db:
            result = await db.execute(
                select(AgentExecution).where(AgentExecution.thread_id == thread_id)
            )
            execution = result.scalar_one_or_none()
            if execution:
                execution.status = ExecutionStatus.RUNNING
                execution.error = None
                await db.commit()
                logger.info(f"Execution marked RUNNING | thread_id={thread_id}")
            else:
                logger.warning(
                    f"No AgentExecution row found before graph run | thread_id={thread_id}"
                )

        # Run graph (may interrupt at human_review)
        final_state = await graph.ainvoke(initial_state, config=config)

        snapshot = await graph.aget_state(config)
        is_interrupted = bool(getattr(snapshot, "next", None))

        async with get_db_context() as db:
            result = await db.execute(
                select(AgentExecution).where(AgentExecution.thread_id == thread_id)
            )
            execution = result.scalar_one_or_none()
            if not execution:
                logger.error(
                    f"AgentExecution missing after graph run | thread_id={thread_id}"
                )
                return

            # Persist evidence (visible before/at human approval)
            execution.plan = final_state.get("plan")
            execution.research_data = final_state.get("research_data")
            execution.browser_evidence = final_state.get("browser_evidence")
            execution.integration_result = final_state.get("integration_result")
            execution.report = final_state.get("report")
            execution.report_structured = final_state.get("report_structured")
            execution.confidence = _safe_confidence(final_state.get("confidence"))
            execution.error = final_state.get("error")
            execution.agents_executed = final_state.get("agents_executed")
            execution.notification_result = final_state.get("notification_result") or {}

            if is_interrupted:
                execution.status = ExecutionStatus.WAITING_HUMAN

                from app.notify import send_hitl_alert

                hitl_mail = await send_hitl_alert(final_state)
                execution.notification_result = {
                    **(execution.notification_result or {}),
                    "hitl_alert": hitl_mail,
                }
            else:
                if final_state.get("error"):
                    execution.status = ExecutionStatus.FAILED
                    execution.error = str(final_state.get("error"))
                else:
                    execution.status = ExecutionStatus.COMPLETED
                    execution.completed_at = datetime.now(timezone.utc)
                    if not execution.report:
                        decision = (
                            (final_state.get("integration_result") or {}).get("decision")
                            or {}
                        )
                        execution.report = (
                            decision.get("reason") or "Investigation completed."
                        )

            await db.commit()

        logger.info(
            f"LangGraph execution finished | thread_id={thread_id} | "
            f"db_status={'waiting_human' if is_interrupted else 'completed/failed'} | "
            f"next={getattr(snapshot, 'next', None)}"
        )

    except Exception as e:
        logger.exception(f"LangGraph execution failed | thread_id={thread_id}")
        async with get_db_context() as db:
            result = await db.execute(
                select(AgentExecution).where(AgentExecution.thread_id == thread_id)
            )
            execution = result.scalar_one_or_none()
            if execution:
                execution.status = ExecutionStatus.FAILED
                execution.error = str(e)
                await db.commit()
        raise



@async_log
@async_error_handler()
@langsmith_trace(name="resume_graph_after_human")
async def resume_graph_after_human(
    thread_id: str,
    decision: str,
    notes: str = "",
    approved_by: str | None = None,
) -> Dict[str, Any]:
    """
    Resume graph after human approval/rejection.
    Apply ERP update BEFORE resume when approved, so reporting/email see final statuses.
    """
    from datetime import datetime, timezone

    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # Load current execution for recommended status + event
    async with get_db_context() as db:
        result = await db.execute(
            select(AgentExecution).where(AgentExecution.thread_id == thread_id)
        )
        execution_row = result.scalar_one_or_none()
        if not execution_row:
            raise ValueError(f"Execution not found for thread_id={thread_id}")

        integ = dict(execution_row.integration_result or {})
        pol = dict(integ.get("decision") or {})
        recommended = pol.get("recommended_erp_status")
        order_number = (execution_row.event_payload or {}).get("order_number")
        event_payload = dict(execution_row.event_payload or {})

        # Persist human decision on row early
        execution_row.human_decision = decision
        execution_row.human_notes = notes
        if approved_by:
            execution_row.approved_by = approved_by
        await db.commit()

    decision_l = str(decision or "").lower()
    updated_integ = dict(integ)

    # ---- Apply ERP BEFORE graph resume ----
    if decision_l == "approved" and order_number and recommended:
        from app.mulesoft import update_order_in_erp

        upd = await update_order_in_erp(
            order_number=order_number,
            new_status=str(recommended),
            notes=f"Human approved by {approved_by or 'user'}. Applied recommended ERP status '{recommended}'.",
            extra_data={
                "thread_id": thread_id,
                "human_decision": decision,
                "approved_by": approved_by,
                "applied_after_approval": True,
            },
        )
        updated_integ = {
            **integ,
            **upd,
            "decision": {
                **pol,
                "requires_human": False,
                "reason": (
                    f"Human approved. ERP status updated from "
                    f"'{upd.get('old_status')}' to '{upd.get('new_status')}'."
                ),
            },
            "applied_after_approval": True,
            "erp_status_before": integ.get("erp_status_before") or integ.get("old_status"),
            "portal_status": integ.get("portal_status"),
        }

    elif decision_l == "rejected":
        old_status = integ.get("old_status") or integ.get("erp_status_before")
        updated_integ = {
            **integ,
            "old_status": old_status,
            "new_status": old_status,
            "applied_after_approval": False,
            "notes": f"Human rejected. ERP left unchanged at '{old_status}'.",
            "decision": {
                **pol,
                "requires_human": False,
                "reason": f"Human rejected. ERP status left unchanged at '{old_status}'.",
            },
        }

    # Push decision + final integration into graph state BEFORE resume
    await graph.aupdate_state(
        config,
        {
            "human_decision": decision,
            "human_notes": notes,
            "approved_by": approved_by,
            "integration_result": updated_integ,
            "event": event_payload,
            "status": "investigating",
        },
    )

    # Resume graph (reporting + notification should now see shipped/etc.)
    final_state = await graph.ainvoke(None, config=config) or {}

    # Prefer updated integration if graph didn't overwrite it badly
    if updated_integ:
        final_integ = dict(final_state.get("integration_result") or {})
        final_state["integration_result"] = {
            **final_integ,
            **updated_integ,
            "decision": updated_integ.get("decision") or final_integ.get("decision"),
        }

    # Persist final execution
    async with get_db_context() as db:
        result = await db.execute(
            select(AgentExecution).where(AgentExecution.thread_id == thread_id)
        )
        execution = result.scalar_one_or_none()
        if execution:
            execution.human_decision = decision
            execution.human_notes = notes
            if approved_by:
                execution.approved_by = approved_by

            execution.plan = final_state.get("plan") if final_state else execution.plan
            execution.research_data = final_state.get("research_data") if final_state else execution.research_data
            execution.browser_evidence = final_state.get("browser_evidence") if final_state else execution.browser_evidence
            execution.integration_result = final_state.get("integration_result") if final_state else updated_integ
            execution.report = final_state.get("report") if final_state else execution.report
            execution.report_structured = final_state.get("report_structured") if final_state else execution.report_structured
            execution.confidence = _safe_confidence(
                final_state.get("confidence") if final_state else execution.confidence
            )
            execution.error = final_state.get("error") if final_state else execution.error
            execution.agents_executed = final_state.get("agents_executed") if final_state else execution.agents_executed
            execution.notification_result = final_state.get("notification_result") if final_state else execution.notification_result

            if final_state.get("error"):
                execution.status = ExecutionStatus.FAILED
            else:
                execution.status = ExecutionStatus.COMPLETED
                execution.completed_at = datetime.now(timezone.utc)

            await db.commit()
            await db.refresh(execution)

    logger.info(
        f"Graph resumed & committed | thread_id={thread_id} | decision={decision} | "
        f"erp={((final_state.get('integration_result') or {}).get('old_status'))}->"
        f"{((final_state.get('integration_result') or {}).get('new_status'))}"
    )
    return final_state