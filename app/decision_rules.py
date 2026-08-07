from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional


PORTAL_TO_ERP_STATUS = {
    "label created": "processing",
    "in transit": "shipped",
    "out for delivery": "shipped",
    "delivered": "delivered",
    "delayed": "exception",
    "on hold - inventory": "exception",
    "exception - address issue": "exception",
    "error_collecting_data": None,
}


@dataclass
class DecisionResult:
    mismatch: bool
    recommended_erp_status: Optional[str]
    trust_portal: bool
    requires_human: bool
    reason: str
    confidence: float
    action: str


def _norm(v: Optional[str]) -> str:
    return (v or "").strip().lower()


def compute_confidence(
    *,
    erp_found: bool,
    browser_success: bool,
    mismatch: bool,
    portal_status: Optional[str],
) -> float:
    if not browser_success:
        return 0.35
    if not erp_found:
        return 0.58
    portal = _norm(portal_status)
    if portal == "error_collecting_data":
        return 0.40
    if mismatch:
        return 0.92
    return 0.84


def evaluate_mismatch(
    *,
    erp_status: Optional[str],
    portal_status: Optional[str],
    browser_success: bool,
    severity: str,
    exception_type: str,
    erp_found: bool = True,
    confidence: float | None = None,
) -> DecisionResult:
    erp = _norm(erp_status)
    portal = _norm(portal_status)
    severity_n = _norm(severity)
    exception_type_n = _norm(exception_type)

    recommended = PORTAL_TO_ERP_STATUS.get(portal)
    mismatch = bool(erp_found and erp and recommended and erp != recommended)

    if confidence is None:
        confidence = compute_confidence(
            erp_found=erp_found,
            browser_success=browser_success,
            mismatch=mismatch,
            portal_status=portal_status,
        )

    trust_portal = bool(browser_success and recommended is not None)
    requires_human = severity_n in {"high", "critical"} or confidence < 0.75 or not browser_success

    if not browser_success:
        reason = (
            f"Browser evidence collection failed. ERP status remains '{erp_status}'. "
            f"No safe automatic ERP update recommended."
        )
        return DecisionResult(False, None, False, True, reason, confidence, "keep_erp_status")

    if not erp_found:
        reason = (
            f"ERP order not found. Portal status is '{portal_status}'. "
            f"Cannot reconcile system-of-record status."
        )
        return DecisionResult(False, None, trust_portal, True, reason, confidence, "keep_erp_status")

    if not mismatch:
        reason = (
            f"No actionable mismatch under policy. ERP='{erp_status}', portal='{portal_status}'."
        )
        return DecisionResult(False, None, trust_portal, requires_human, reason, confidence, "no_update")

    reason = (
        f"Mismatch confirmed for exception_type='{exception_type_n}'. "
        f"ERP='{erp_status}' is behind portal='{portal_status}'. "
        f"Recommend ERP update to '{recommended}'."
    )
    if requires_human:
        reason += " Human approval required by severity/confidence policy."

    return DecisionResult(
        mismatch=True,
        recommended_erp_status=recommended,
        trust_portal=True,
        requires_human=requires_human,
        reason=reason,
        confidence=confidence,
        action="update_erp_status",
    )


def decision_to_dict(d: DecisionResult) -> Dict[str, Any]:
    return {
        "mismatch": d.mismatch,
        "recommended_erp_status": d.recommended_erp_status,
        "trust_portal": d.trust_portal,
        "requires_human": d.requires_human,
        "reason": d.reason,
        "confidence": d.confidence,
        "action": d.action,
    }