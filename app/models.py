import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Use enum values (e.g. 'pending') instead of names (e.g. 'PENDING') in PostgreSQL."""
    return [e.value for e in enum_cls]


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    EXCEPTION = "exception"


class ExceptionType(str, enum.Enum):
    INVENTORY_SHORTAGE = "inventory_shortage"
    PAYMENT_FAILURE = "payment_failure"
    SHIPPING_DELAY = "shipping_delay"
    VENDOR_STATUS_MISMATCH = "vendor_status_mismatch"
    ADDRESS_ISSUE = "address_issue"
    OTHER = "other"


class ExceptionSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExceptionStatus(str, enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    WAITING_HUMAN = "waiting_human"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    is_superuser: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="orderstatus", values_callable=enum_values),
        default=OrderStatus.PENDING,
        index=True,
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    shipping_address: Mapped[dict] = mapped_column(JSONB, nullable=False)
    items: Mapped[list] = mapped_column(JSONB, nullable=False)
    vendor_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    exceptions: Mapped[list["OrderException"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderException(Base):
    __tablename__ = "order_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exception_type: Mapped[ExceptionType] = mapped_column(
        Enum(ExceptionType, name="exceptiontype", values_callable=enum_values),
        nullable=False,
        index=True,
    )
    severity: Mapped[ExceptionSeverity] = mapped_column(
        Enum(ExceptionSeverity, name="exceptionseverity", values_callable=enum_values),
        default=ExceptionSeverity.MEDIUM,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ExceptionStatus] = mapped_column(
        Enum(ExceptionStatus, name="exceptionstatus", values_callable=enum_values),
        default=ExceptionStatus.OPEN,
        index=True,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)

    order: Mapped["Order"] = relationship(back_populates="exceptions")


class VendorStatus(Base):
    __tablename__ = "vendor_status"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    portal_status: Mapped[str] = mapped_column(String(100), nullable=False)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100))
    eta: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_evidence: Mapped[Optional[dict]] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(50), default="playwright")


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    __table_args__ = (Index("ix_agent_executions_thread_id", "thread_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    event_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, name="executionstatus", values_callable=enum_values),
        default=ExecutionStatus.PENDING,
        index=True,
    )
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    plan: Mapped[Optional[list]] = mapped_column(JSONB)
    research_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    browser_evidence: Mapped[Optional[dict]] = mapped_column(JSONB)
    integration_result: Mapped[Optional[dict]] = mapped_column(JSONB)
    report: Mapped[Optional[str]] = mapped_column(Text)
    report_structured: Mapped[Optional[dict]] = mapped_column(JSONB)
    human_decision: Mapped[Optional[str]] = mapped_column(String(50))
    human_notes: Mapped[Optional[str]] = mapped_column(Text)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    agents_executed: Mapped[Optional[list]] = mapped_column(JSONB)
    notification_result: Mapped[Optional[dict]] = mapped_column(JSONB)


class IntegrationLog(Base):
    __tablename__ = "integration_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    system_name: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    request_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    response_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    status_code: Mapped[Optional[int]] = mapped_column()
    success: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())