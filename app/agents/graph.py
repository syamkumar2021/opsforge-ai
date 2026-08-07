from typing import Literal, Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agents.nodes import (
    browser_node,
    human_review_node,
    integration_node,
    notification_node,
    planner_node,
    reporting_node,
    research_node,
)
from app.agents.state import AgentState
from app.config import get_settings
from app.decorators import async_log, langsmith_trace

settings = get_settings()

# Module-level cache so we build the graph only once
_graph = None


def get_psycopg_conninfo() -> str:
    """
    Convert SQLAlchemy asyncpg URL to a plain psycopg connection string.
    Example:
        postgresql+asyncpg://user:pass@host:5432/db
        → postgresql://user:pass@host:5432/db
    """
    url = settings.database_url
    return url.replace("postgresql+asyncpg://", "postgresql://")


def should_continue_after_planner(state: AgentState) -> Literal["research", "browser", "end"]:
    plan = state.get("plan", []) or []
    plan_str = " ".join([str(p).lower() for p in plan]) if isinstance(plan, list) else str(plan).lower()

    # Always continue investigation for real exception events
    event = state.get("event") or {}
    if event.get("order_number"):
        # Prefer research first whenever an order-linked exception exists
        if any(k in plan_str for k in ["browser", "vendor", "portal", "carrier", "shipping", "tracking"]):
            # still research first for ERP context
            return "research"
        return "research"

    if "research" in plan_str:
        return "research"
    if any(k in plan_str for k in ["browser", "vendor", "portal", "carrier"]):
        return "browser"
    return "end"


def should_go_to_human(state: AgentState) -> Literal["human_review", "reporting"]:
    """
    Decide whether Human-in-the-Loop is required.
    Low confidence or high/critical severity → go to human review.
    """
    confidence = state.get("confidence", 1.0)
    severity = state.get("event", {}).get("severity", "medium")

    if confidence < 0.75 or severity in ("high", "critical"):
        return "human_review"
    return "reporting"


@async_log
@langsmith_trace(name="build_opsforge_graph")
async def build_graph():
    """
    Build and compile the OpsForge multi-agent graph
    with PostgreSQL checkpointer (psycopg) and Human-in-the-Loop support.
    """
    workflow = StateGraph(AgentState)

    # -------------------- Nodes --------------------
    workflow.add_node("planner", planner_node)
    workflow.add_node("research", research_node)
    workflow.add_node("browser", browser_node)
    workflow.add_node("integration", integration_node)
    workflow.add_node("reporting", reporting_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("notification", notification_node)

    # -------------------- Edges --------------------
    workflow.add_edge(START, "planner")

    workflow.add_conditional_edges(
        "planner",
        should_continue_after_planner,
        {
            "research": "research",
            "browser": "browser",
            "end": END,
        },
    )

    workflow.add_edge("research", "browser")
    workflow.add_edge("browser", "integration")

    workflow.add_conditional_edges(
        "integration",
        should_go_to_human,
        {
            "human_review": "human_review",
            "reporting": "reporting",
        },
    )

    workflow.add_edge("human_review", "reporting")
    workflow.add_edge("reporting", "notification")
    workflow.add_edge("notification", END)

    # -------------------- Checkpointer (FIXED) --------------------
    # autocommit=True is REQUIRED because checkpointer.setup()
    # runs CREATE INDEX CONCURRENTLY, which cannot run inside a transaction.
    conninfo = get_psycopg_conninfo()

    pool = AsyncConnectionPool(
        conninfo=conninfo,
        min_size=1,
        max_size=10,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        open=False,
    )
    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()  # creates checkpoint tables if they do not exist

    # -------------------- Compile --------------------
    graph = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],  # Human-in-the-Loop
    )

    return graph


async def get_graph():
    """
    Return a singleton compiled graph.
    Builds it only once (on first call) and reuses it afterwards.
    """
    global _graph
    if _graph is None:
        _graph = await build_graph()
    return _graph