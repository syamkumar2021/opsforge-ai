"""
MuleSoft Integration Layer for OpsForge AI
------------------------------------------
Current mode : MOCK (using PostgreSQL as backend)
Future mode  : Real MuleSoft Anypoint Platform + OAuth 2.0

This file is intentionally written so that switching from mock to real
MuleSoft requires only uncommenting the real implementation and providing
credentials in .env.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select

from app.db import get_db_context
from app.decorators import async_error_handler, async_log, langsmith_trace
from app.models import IntegrationLog, Order, OrderStatus

logger = logging.getLogger(__name__)


# =====================================================================
# MOCK IMPLEMENTATION (Currently Active)
# =====================================================================

@async_log
@async_error_handler()
@langsmith_trace(name="mulesoft_update_order_status", run_type="tool")
async def update_order_in_erp(
    order_number: str,
    new_status: str,
    notes: str = "",
    extra_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    MOCK: Simulates calling a MuleSoft API that updates the Order in ERP.
    In real life this would be a MuleSoft HTTP Request / SAP connector / etc.

    Also writes an audit record into the IntegrationLog table.
    """
    extra_data = extra_data or {}
    thread_id = extra_data.get("thread_id", "unknown")

    async with get_db_context() as db:
        result = await db.execute(select(Order).where(Order.order_number == order_number))
        order = result.scalar_one_or_none()

        if not order:
            # Log the failed attempt
            log = IntegrationLog(
                thread_id=thread_id,
                system_name="mulesoft_mock",
                action="update_order_status",
                request_payload={
                    "order_number": order_number,
                    "new_status": new_status,
                    "notes": notes,
                },
                response_payload={"error": f"Order {order_number} not found"},
                status_code=404,
                success=False,
            )
            db.add(log)
            await db.flush()

            return {
                "success": False,
                "system": "mulesoft_mock",
                "error": f"Order {order_number} not found",
            }

        old_status = order.status.value

        try:
            order.status = OrderStatus(new_status)
        except ValueError:
            log = IntegrationLog(
                thread_id=thread_id,
                system_name="mulesoft_mock",
                action="update_order_status",
                request_payload={
                    "order_number": order_number,
                    "new_status": new_status,
                    "notes": notes,
                },
                response_payload={"error": f"Invalid status: {new_status}"},
                status_code=400,
                success=False,
            )
            db.add(log)
            await db.flush()

            return {
                "success": False,
                "system": "mulesoft_mock",
                "error": f"Invalid status: {new_status}",
            }

        if notes:
            order.notes = (order.notes or "") + f"\n[MuleSoft Mock] {notes}"

        order.updated_at = datetime.now(timezone.utc)
        await db.flush()

        # ----- Audit Log (Success) -----
        log = IntegrationLog(
            thread_id=thread_id,
            system_name="mulesoft_mock",
            action="update_order_status",
            request_payload={
                "order_number": order_number,
                "new_status": new_status,
                "notes": notes,
            },
            response_payload={
                "old_status": old_status,
                "new_status": order.status.value,
                "updated_at": order.updated_at.isoformat(),
            },
            status_code=200,
            success=True,
        )
        db.add(log)
        await db.flush()

        return {
            "success": True,
            "system": "mulesoft_mock",
            "order_number": order_number,
            "old_status": old_status,
            "new_status": order.status.value,
            "notes": notes,
            "updated_at": order.updated_at.isoformat(),
            "extra_data": extra_data,
        }


@async_log
@async_error_handler()
@langsmith_trace(name="mulesoft_get_order", run_type="tool")
async def get_order_from_erp(order_number: str) -> Dict[str, Any]:
    """MOCK: Simulates retrieving order details via MuleSoft."""
    async with get_db_context() as db:
        result = await db.execute(select(Order).where(Order.order_number == order_number))
        order = result.scalar_one_or_none()

        if not order:
            return {
                "success": False,
                "system": "mulesoft_mock",
                "error": f"Order {order_number} not found",
            }

        return {
            "success": True,
            "system": "mulesoft_mock",
            "order_number": order.order_number,
            "status": order.status.value,
            "customer_id": order.customer_id,
            "total_amount": float(order.total_amount),
            "tracking_number": order.tracking_number,
            "vendor_id": order.vendor_id,
        }


# =====================================================================
# REAL MULESOFT IMPLEMENTATION (COMMENTED – Ready for future use)
# =====================================================================
#
# import httpx
# from app.config import get_settings
#
# settings = get_settings()
#
# async def _get_mulesoft_token() -> str:
#     """
#     Real OAuth 2.0 Client Credentials flow for MuleSoft Anypoint Platform.
#     """
#     async with httpx.AsyncClient() as client:
#         response = await client.post(
#             settings.mulesoft_token_url,
#             data={
#                 "grant_type": "client_credentials",
#                 "client_id": settings.mulesoft_client_id,
#                 "client_secret": settings.mulesoft_client_secret,
#             },
#             headers={"Content-Type": "application/x-www-form-urlencoded"},
#         )
#         response.raise_for_status()
#         return response.json()["access_token"]
#
#
# async def update_order_in_erp_real(
#     order_number: str,
#     new_status: str,
#     notes: str = "",
#     extra_data: Optional[Dict[str, Any]] = None,
# ) -> Dict[str, Any]:
#     """
#     REAL implementation using MuleSoft Anypoint Platform.
#     Replace the mock function above with this when credentials are available.
#     """
#     token = await _get_mulesoft_token()
#
#     payload = {
#         "orderNumber": order_number,
#         "status": new_status,
#         "notes": notes,
#         "additionalData": extra_data or {},
#     }
#
#     async with httpx.AsyncClient() as client:
#         response = await client.patch(
#             f"{settings.mulesoft_base_url}/api/orders/{order_number}",
#             json=payload,
#             headers={
#                 "Authorization": f"Bearer {token}",
#                 "Content-Type": "application/json",
#             },
#             timeout=30.0,
#         )
#         response.raise_for_status()
#         return {
#             "success": True,
#             "system": "mulesoft_anypoint",
#             "status_code": response.status_code,
#             "response": response.json(),
#         }