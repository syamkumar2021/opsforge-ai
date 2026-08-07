from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Shared state for the OpsForge multi-agent graph.
    This state is persisted using PostgreSQL checkpointer.
    """
    thread_id: str
    event: Dict[str, Any]
    plan: List[str]
    research_data: Dict[str, Any]
    browser_evidence: Dict[str, Any]
    integration_result: Dict[str, Any]
    report: str
    report_structured: Dict[str, Any]
    confidence: float
    human_decision: Optional[str]
    human_notes: Optional[str]
    approved_by: Optional[str]
    status: str                    # pending | investigating | waiting_human | completed | failed
    messages: Annotated[list, add_messages]
    error: Optional[str]
    notification_result: Dict[str, Any]
    agents_executed: list
    notification_result: Dict[str, Any]