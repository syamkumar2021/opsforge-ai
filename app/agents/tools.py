import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import get_db_context
from app.decorators import async_error_handler, async_log, langsmith_trace
from app.models import (
    ExceptionStatus,
    Order,
    OrderException,
    OrderStatus,
    VendorStatus,
)

logger = logging.getLogger(__name__)


@tool
@async_log
@async_error_handler()
@langsmith_trace(name="tool_get_order_details", run_type="tool")
async def get_order_details(order_number: str) -> Dict[str, Any]:
    """
    Fetch full order details from PostgreSQL (real persistent data).
    """
    async with get_db_context() as db:
        result = await db.execute(
            select(Order)
            .where(Order.order_number == order_number)
            .options(selectinload(Order.exceptions))
        )
        order = result.scalar_one_or_none()

        if not order:
            return {
                "found": False,
                "order_number": order_number,
                "error": f"Order {order_number} not found in database",
            }

        return {
            "found": True,
            "id": str(order.id),
            "order_number": order.order_number,
            "customer_id": order.customer_id,
            "customer_email": order.customer_email,
            "status": order.status.value,
            "total_amount": float(order.total_amount),
            "currency": order.currency,
            "shipping_address": order.shipping_address,
            "items": order.items,
            "vendor_id": order.vendor_id,
            "tracking_number": order.tracking_number,
            "notes": order.notes,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        }


@tool
@async_log
@async_error_handler()
@langsmith_trace(name="tool_get_exception_context", run_type="tool")
async def get_exception_context(order_number: str) -> Dict[str, Any]:
    """
    Retrieve the latest open exception for an order from PostgreSQL.
    """
    async with get_db_context() as db:
        # First find the order
        order_result = await db.execute(
            select(Order).where(Order.order_number == order_number)
        )
        order = order_result.scalar_one_or_none()

        if not order:
            return {
                "found": False,
                "order_number": order_number,
                "error": f"Order {order_number} not found",
            }

        # Get the latest open / investigating exception
        exc_result = await db.execute(
            select(OrderException)
            .where(
                OrderException.order_id == order.id,
                OrderException.status.in_([
                    ExceptionStatus.OPEN,
                    ExceptionStatus.INVESTIGATING,
                    ExceptionStatus.WAITING_HUMAN,
                ]),
            )
            .order_by(OrderException.detected_at.desc())
            .limit(1)
        )
        exception = exc_result.scalar_one_or_none()

        if not exception:
            return {
                "found": False,
                "order_number": order_number,
                "message": "No open exception found for this order",
            }

        return {
            "found": True,
            "exception_id": str(exception.id),
            "order_id": str(exception.order_id),
            "order_number": order_number,
            "exception_type": exception.exception_type.value,
            "severity": exception.severity.value,
            "description": exception.description,
            "status": exception.status.value,
            "detected_at": exception.detected_at.isoformat() if exception.detected_at else None,
            "resolution_notes": exception.resolution_notes,
        }


@tool
@async_log
@async_error_handler()
@langsmith_trace(name="tool_update_order_status", run_type="tool")
async def update_order_status(
    order_number: str,
    new_status: str,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Update order status in PostgreSQL (acts as MuleSoft → ERP mock).
    Also logs the change.
    """
    async with get_db_context() as db:
        result = await db.execute(
            select(Order).where(Order.order_number == order_number)
        )
        order = result.scalar_one_or_none()

        if not order:
            return {
                "success": False,
                "order_number": order_number,
                "error": f"Order {order_number} not found",
            }

        old_status = order.status.value

        try:
            order.status = OrderStatus(new_status)
        except ValueError:
            return {
                "success": False,
                "order_number": order_number,
                "error": f"Invalid status value: {new_status}",
            }

        if notes:
            order.notes = (order.notes or "") + f"\n[Auto] {notes}"

        order.updated_at = datetime.now(timezone.utc)

        await db.flush()

        return {
            "success": True,
            "order_number": order_number,
            "old_status": old_status,
            "new_status": order.status.value,
            "notes": notes,
            "system": "postgresql_erp_mock",
            "updated_at": order.updated_at.isoformat(),
        }


@tool
@async_log
@async_error_handler()
@langsmith_trace(name="tool_save_vendor_status", run_type="tool")
async def save_vendor_status(
    order_number: str,
    portal_status: str,
    tracking_number: Optional[str] = None,
    eta: Optional[str] = None,
    raw_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Persist the evidence collected by the Browser Agent into PostgreSQL.
    """
    async with get_db_context() as db:
        order_result = await db.execute(
            select(Order).where(Order.order_number == order_number)
        )
        order = order_result.scalar_one_or_none()

        if not order:
            return {
                "success": False,
                "error": f"Order {order_number} not found",
            }

        vendor_status = VendorStatus(
            order_id=order.id,
            vendor_id=order.vendor_id or "UNKNOWN",
            portal_status=portal_status,
            tracking_number=tracking_number,
            last_checked=datetime.now(timezone.utc),
            raw_evidence=raw_evidence or {},
            source="playwright",
        )

        # Optionally update tracking number on the order itself
        if tracking_number and not order.tracking_number:
            order.tracking_number = tracking_number

        db.add(vendor_status)
        await db.flush()

        return {
            "success": True,
            "vendor_status_id": str(vendor_status.id),
            "order_number": order_number,
            "portal_status": portal_status,
            "tracking_number": tracking_number,
        }