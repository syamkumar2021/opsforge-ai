import logging
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import get_graph
from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_active_user,
    get_password_hash,
    get_user_by_email,
)
from app.db import get_db
from app.decorators import async_log, langsmith_trace
from app.execution_handler import resume_graph_after_human
from app.kafka_client import kafka_client
from app.models import (
    AgentExecution,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ExecutionStatus,
    Order,
    OrderException,
    OrderStatus,
    User,
    IntegrationLog,
    VendorStatus,
)
from app.schemas import (
    AgentExecutionResponse,
    ErpOrderFeedRequest,
    HumanDecisionRequest,
    SimulateEventRequest,
    Token,
    UserCreate,
    UserResponse,
    PromoteUserRequest,
)


logger = logging.getLogger(__name__)
router = APIRouter()

ACTIVE_EXECUTION_STATUSES = {
    ExecutionStatus.PENDING,
    ExecutionStatus.RUNNING,
    ExecutionStatus.WAITING_HUMAN,
}


async def find_active_execution_for_order(
    db: AsyncSession,
    order_number: str,
) -> AgentExecution | None:
    """Find an active investigation for the same order_number."""
    result = await db.execute(
        select(AgentExecution)
        .where(AgentExecution.status.in_(ACTIVE_EXECUTION_STATUSES))
        .order_by(AgentExecution.started_at.desc())
    )
    rows = result.scalars().all()
    target = order_number.strip().upper()
    for row in rows:
        payload = row.event_payload or {}
        if str(payload.get("order_number", "")).strip().upper() == target:
            return row
    return None


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------
@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Auth"])
@async_log
async def register_user(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    existing = await get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/users", tags=["Auth"])
@async_log
async def list_users(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    email: Optional[str] = Query(default=None, description="Filter by email (exact or partial)"),
    limit: int = Query(default=50, ge=1, le=200),
):
    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    if email:
        stmt = stmt.where(User.email.ilike(f"%{email.strip()}%"))

    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "created_at": u.created_at,
            "is_current_user": u.email == current_user.email,  # highlight
        }
        for u in users
    ]


@router.post("/auth/token", response_model=Token, tags=["Auth"])
@async_log
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse, tags=["Auth"])
@async_log
async def me(current_user: Annotated[User, Depends(get_current_active_user)]):
    return current_user

@router.post("/users/promote", tags=["Auth"])
@async_log
async def promote_user(
    payload: PromoteUserRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required")

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_superuser = payload.is_superuser
    await db.flush()
    await db.refresh(user)

    return {
        "email": user.email,
        "is_superuser": user.is_superuser,
        "updated_by": current_user.email,
    }

# ------------------------------------------------------------------
# ERP data feed (replaces manual seed for testing)
# ------------------------------------------------------------------
@router.post("/erp/orders", status_code=status.HTTP_201_CREATED, tags=["ERP Orders"])
@async_log
async def feed_erp_orders(
    payload: ErpOrderFeedRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Feed one or many ERP orders (and optional exceptions) into PostgreSQL.
    Body always uses {"orders": [ ... ]}; send 1 item for single record.
    """
    created = []
    skipped = []

    for item in payload.orders:
        existing = await db.execute(
            select(Order).where(Order.order_number == item.order_number)
        )
        if existing.scalar_one_or_none():
            skipped.append(
                {"order_number": item.order_number, "reason": "already exists"}
            )
            continue

        try:
            order_status = OrderStatus(item.status.lower())
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid order status '{item.status}' for {item.order_number}. "
                    f"Allowed: {[s.value for s in OrderStatus]}"
                ),
            )

        order = Order(
            order_number=item.order_number,
            customer_id=item.customer_id,
            customer_email=item.customer_email,
            status=order_status,
            total_amount=item.total_amount,
            currency=item.currency,
            vendor_id=item.vendor_id,
            tracking_number=item.tracking_number,
            shipping_address=item.shipping_address,
            items=item.items,
            notes=item.notes,
        )
        db.add(order)
        await db.flush()

        if item.exception_type:
            try:
                et = ExceptionType(item.exception_type.lower())
                sev = ExceptionSeverity((item.exception_severity or "medium").lower())
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Invalid exception_type/severity for {item.order_number}. "
                        f"exception_type allowed: {[e.value for e in ExceptionType]}; "
                        f"severity allowed: {[s.value for s in ExceptionSeverity]}"
                    ),
                )

            db.add(
                OrderException(
                    order_id=order.id,
                    exception_type=et,
                    severity=sev,
                    description=item.exception_description or "Seeded exception",
                    status=ExceptionStatus.OPEN,
                )
            )

        created.append(item.order_number)

    await db.commit()
    return {
        "created": created,
        "skipped": skipped,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "fed_by": current_user.email,
    }


@router.get("/erp/orders", tags=["ERP Orders"])
@async_log
async def list_erp_orders(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    order_number: Optional[str] = Query(default=None, description="Filter by exact order_number"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by order status"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    List fed ERP orders.
    Examples:
      GET /api/v1/erp/orders
      GET /api/v1/erp/orders?order_number=ORD-10001
      GET /api/v1/erp/orders?status=processing
    """
    stmt = select(Order).order_by(Order.created_at.desc()).limit(limit)

    if order_number:
        stmt = stmt.where(Order.order_number == order_number.strip())

    if status_filter:
        try:
            st = OrderStatus(status_filter.strip().lower())
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status_filter}'. Allowed: {[s.value for s in OrderStatus]}",
            )
        stmt = stmt.where(Order.status == st)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "id": str(r.id),
            "order_number": r.order_number,
            "customer_id": r.customer_id,
            "customer_email": r.customer_email,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "total_amount": float(r.total_amount) if r.total_amount is not None else None,
            "currency": r.currency,
            "vendor_id": r.vendor_id,
            "tracking_number": r.tracking_number,
            "shipping_address": r.shipping_address,
            "items": r.items,
            "notes": r.notes,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.post("/erp/orders/reset", tags=["ERP Orders"])
@async_log
async def reset_erp_orders(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Superuser required to reset ERP orders",
        )
    
    """
    Reset ERP master data so the same 10 demo orders can be fed again.
    Deletes dependent rows first (exceptions/vendor_status), then orders.
    Does NOT delete users or agent_executions.
    """
    # Child tables first (FK safety)
    ex = await db.execute(delete(OrderException))
    vs = await db.execute(delete(VendorStatus))
    od = await db.execute(delete(Order))
    await db.commit()

    return {
        "message": "ERP orders reset successfully",
        "deleted_order_exceptions": ex.rowcount or 0,
        "deleted_vendor_status": vs.rowcount or 0,
        "deleted_orders": od.rowcount or 0,
        "agent_executions_preserved": True,
        "reset_by": current_user.email,
    }

@router.post("/events/simulate", response_model=AgentExecutionResponse, tags=["Events"])
@async_log
@langsmith_trace(name="simulate_exception_event")
async def simulate_exception_event(
    payload: SimulateEventRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create an exception event, persist execution record, and publish to Kafka.
    Blocks duplicate active investigations for the same order_number.
    """
    active = await find_active_execution_for_order(db, payload.order_number)
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Active investigation already exists for this order_number",
                "order_number": payload.order_number,
                "existing_thread_id": active.thread_id,
                "existing_status": active.status.value
                if hasattr(active.status, "value")
                else str(active.status),
                "hint": "Complete/fail the existing case, or approve/reject if waiting_human",
            },
        )

    thread_id = str(uuid4())

    event_payload = {
        "thread_id": thread_id,
        "order_number": payload.order_number,
        "exception_type": payload.exception_type,
        "severity": payload.severity,
        "description": payload.description,
        "triggered_by": current_user.email,
        "source": "api_simulate",
    }

    # Create as RUNNING so UI lifecycle can start immediately
    execution = AgentExecution(
        thread_id=thread_id,
        event_payload=event_payload,
        status=ExecutionStatus.RUNNING,
    )
    db.add(execution)
    await db.flush()
    await db.commit()
    await db.refresh(execution)

    # Publish after commit so consumer always finds the row
    await kafka_client.publish_exception_event(event_payload)

    await db.refresh(execution)
    return execution


@router.get("/executions", response_model=list[AgentExecutionResponse], tags=["Executions"])
@async_log
async def list_executions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status: pending, running, waiting_human, completed, failed",
    ),
    human_decision: Optional[str] = Query(
        default=None,
        description="Filter by decision: approved, rejected, modified",
    ),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    List executions with optional filters.
    Examples:
      /api/v1/executions?status=waiting_human
      /api/v1/executions?human_decision=approved
    """
    stmt = select(AgentExecution).order_by(AgentExecution.started_at.desc()).limit(limit)

    if status_filter:
        normalized = status_filter.strip().lower()
        try:
            status_enum = ExecutionStatus(normalized)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid status '{status_filter}'. "
                    "Allowed: pending, running, waiting_human, completed, failed"
                ),
            )
        stmt = stmt.where(AgentExecution.status == status_enum)

    if human_decision:
        decision = human_decision.strip().lower()
        if decision not in {"approved", "rejected", "modified"}:
            raise HTTPException(
                status_code=422,
                detail="Invalid human_decision. Allowed: approved, rejected, modified",
            )
        stmt = stmt.where(AgentExecution.human_decision == decision)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/executions/{thread_id}", response_model=AgentExecutionResponse, tags=["Executions"])
@async_log
async def get_execution(
    thread_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(AgentExecution).where(AgentExecution.thread_id == thread_id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.post("/executions/{thread_id}/approve", response_model=AgentExecutionResponse, tags=["Executions"])
@async_log
async def human_decision(
    thread_id: str,
    decision: HumanDecisionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Human-in-the-Loop endpoint.
    Resumes LangGraph when DB status is waiting_human OR graph still has pending nodes.
    """
    result = await db.execute(
        select(AgentExecution).where(AgentExecution.thread_id == thread_id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await graph.aget_state(config)
    has_pending_nodes = bool(getattr(snapshot, "next", None))

    if execution.status != ExecutionStatus.WAITING_HUMAN and not has_pending_nodes:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Execution is not waiting for human decision. "
                f"Current status: {execution.status}"
            ),
        )

    execution.approved_by = current_user.email
    execution.human_decision = decision.decision
    execution.human_notes = decision.notes
    # execution.status = ExecutionStatus.RUNNING
    await db.commit()

    try:
        await resume_graph_after_human(
            thread_id=thread_id,
            decision=decision.decision,
            notes=decision.notes or "",
            approved_by=current_user.email,
        )
    except Exception as e:
        logger.exception(f"Failed to resume graph for thread_id={thread_id}")
        result = await db.execute(
            select(AgentExecution).where(AgentExecution.thread_id == thread_id)
        )
        execution = result.scalar_one_or_none()
        if execution:
            execution.status = ExecutionStatus.FAILED
            execution.error = str(e)
            await db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resume execution: {str(e)}",
        )

    result = await db.execute(
        select(AgentExecution).where(AgentExecution.thread_id == thread_id)
    )
    execution = result.scalar_one()
    return execution


@router.post("/admin/reset-investigations", tags=["Admin"])
@async_log
async def reset_investigations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    order_number: Optional[str] = Query(
        default=None,
        description="Optional: reset only this order_number. If omitted, reset all investigations.",
    ),
):

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Superuser required to reset ERP orders",
        )
    
    """
    Reset investigation/test runs so the same exception events can be re-tested.
    Does NOT delete ERP orders or order_exceptions created via /erp/orders.
    """
    deleted_executions = 0
    deleted_vendor_status = 0
    deleted_integration_logs = 0

    if order_number:
        # Delete executions only for this order_number (from event_payload)
        result = await db.execute(select(AgentExecution))
        rows = result.scalars().all()
        target = order_number.strip().upper()
        to_delete_ids = []
        thread_ids = []
        for row in rows:
            payload = row.event_payload or {}
            if str(payload.get("order_number", "")).strip().upper() == target:
                to_delete_ids.append(row.id)
                thread_ids.append(row.thread_id)

        if to_delete_ids:
            await db.execute(
                delete(AgentExecution).where(AgentExecution.id.in_(to_delete_ids))
            )
            deleted_executions = len(to_delete_ids)

        if thread_ids:
            await db.execute(
                delete(IntegrationLog).where(IntegrationLog.thread_id.in_(thread_ids))
            )
            deleted_integration_logs = len(thread_ids)

        # vendor_status is by order_id; clean via order_number join
        order_result = await db.execute(
            select(Order).where(Order.order_number == order_number)
        )
        order = order_result.scalar_one_or_none()
        if order:
            vs = await db.execute(
                delete(VendorStatus).where(VendorStatus.order_id == order.id)
            )
            deleted_vendor_status = vs.rowcount or 0

    else:
        # Full investigation reset
        exec_result = await db.execute(delete(AgentExecution))
        deleted_executions = exec_result.rowcount or 0

        il_result = await db.execute(delete(IntegrationLog))
        deleted_integration_logs = il_result.rowcount or 0

        vs_result = await db.execute(delete(VendorStatus))
        deleted_vendor_status = vs_result.rowcount or 0

    await db.commit()

    return {
        "message": "Investigation state reset successfully",
        "scope": order_number or "ALL",
        "deleted_executions": deleted_executions,
        "deleted_integration_logs": deleted_integration_logs,
        "deleted_vendor_status": deleted_vendor_status,
        "erp_orders_preserved": True,
        "reset_by": current_user.email,
    }