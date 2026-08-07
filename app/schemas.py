from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
import re

# ======================
# Auth
# ======================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)

    @field_validator("email")
    @classmethod
    def validate_company_email(cls, v: str) -> str:
        email = v.strip().lower()

        # Must be company domain
        if not email.endswith("@opsforge.ai"):
            raise ValueError("Email must use company domain '@opsforge.ai'")

        local_part = email.split("@", 1)[0]

        # Prefix length limits (professional)
        if len(local_part) < 3:
            raise ValueError("Email prefix must be at least 3 characters")
        if len(local_part) > 30:
            raise ValueError("Email prefix must be at most 30 characters")

        # Allowed: letters, numbers, dot, underscore, hyphen
        # No consecutive dots, cannot start/end with dot/hyphen/underscore
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?", local_part):
            raise ValueError(
                "Email prefix may contain letters, numbers, dot, underscore, hyphen only"
            )
        if ".." in local_part:
            raise ValueError("Email prefix cannot contain consecutive dots")

        return email

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain at least one special character")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        name = " ".join(v.split())
        if len(name) < 2:
            raise ValueError("Full name is too short")
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", name):
            raise ValueError("Full name contains invalid characters")
        return name


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime

class PromoteUserRequest(BaseModel):
    email: EmailStr
    is_superuser: bool = True

# ======================
# Order & Exception
# ======================
class OrderCreate(BaseModel):
    order_number: str = Field(..., min_length=5, max_length=50)
    customer_id: str
    customer_email: EmailStr
    total_amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    shipping_address: dict
    items: List[dict]
    vendor_id: Optional[str] = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_number: str
    customer_id: str
    customer_email: EmailStr
    status: str
    total_amount: Decimal
    currency: str
    vendor_id: Optional[str]
    tracking_number: Optional[str]
    created_at: datetime


class ExceptionCreate(BaseModel):
    order_id: UUID
    exception_type: str
    severity: str = "medium"
    description: str = Field(..., min_length=10)


class ExceptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    exception_type: str
    severity: str
    description: str
    status: str
    detected_at: datetime


# ======================
# Agent Execution
# ======================
class SimulateEventRequest(BaseModel):
    order_number: str = Field(..., min_length=3, max_length=50)
    exception_type: str = Field(
        ...,
        pattern="^(inventory_shortage|payment_failure|shipping_delay|vendor_status_mismatch|address_issue|other)$",
    )
    severity: str = Field(
        default="medium",
        pattern="^(low|medium|high|critical)$",
    )
    description: str = Field(..., min_length=10, max_length=1000)

    @field_validator("order_number")
    @classmethod
    def order_number_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("order_number cannot be empty")
        return v

    @field_validator("description")
    @classmethod
    def description_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("description cannot be empty")
        if len(v) < 10:
            raise ValueError("description must be at least 10 characters")
        return v


class HumanDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected|modified)$")
    notes: Optional[str] = Field(None, max_length=2000)


class AgentExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: str
    status: str
    confidence: Optional[float] = None
    plan: Optional[List[Any]] = None
    report: Optional[str] = None
    report_structured: Optional[Dict[str, Any]] = None
    human_decision: Optional[str] = None
    human_notes: Optional[str] = None
    approved_by: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    agents_executed: Optional[List[str]] = None
    notification_result: Optional[Dict[str, Any]] = None

    # CRITICAL: visible before human approval
    event_payload: Optional[Dict[str, Any]] = None
    research_data: Optional[Dict[str, Any]] = None
    browser_evidence: Optional[Dict[str, Any]] = None
    integration_result: Optional[Dict[str, Any]] = None


class AgentExecutionDetail(AgentExecutionResponse):
    """
    Same fields as AgentExecutionResponse.
    Kept for compatibility if any route uses Detail alias.
    """
    event_payload: Optional[Dict[str, Any]] = None
    research_data: Optional[Dict[str, Any]] = None
    browser_evidence: Optional[Dict[str, Any]] = None
    integration_result: Optional[Dict[str, Any]] = None


class ErpOrderIn(BaseModel):
    order_number: str = Field(min_length=3, max_length=50)
    customer_id: str
    customer_email: str
    status: str = Field(description="pending, confirmed, processing, shipped, delivered, cancelled, exception")
    total_amount: float
    currency: str = "USD"
    vendor_id: Optional[str] = None
    tracking_number: Optional[str] = None
    shipping_address: dict
    items: list
    notes: Optional[str] = None
    # optional linked exception for test scenarios
    exception_type: Optional[str] = None
    exception_severity: Optional[str] = None
    exception_description: Optional[str] = None


class ErpOrderFeedRequest(BaseModel):
    orders: List[ErpOrderIn] = Field(min_length=1, max_length=100)