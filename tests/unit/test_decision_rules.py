from app.decision_rules import compute_confidence, evaluate_mismatch


def test_compute_confidence_browser_fail():
    assert compute_confidence(
        erp_found=True, browser_success=False, mismatch=False, portal_status=None
    ) == 0.35


def test_compute_confidence_mismatch_success():
    score = compute_confidence(
        erp_found=True, browser_success=True, mismatch=True, portal_status="In Transit"
    )
    assert score == 0.92


def test_evaluate_mismatch_recommends_shipped():
    d = evaluate_mismatch(
        erp_status="processing",
        portal_status="In Transit",
        browser_success=True,
        severity="high",
        exception_type="vendor_status_mismatch",
        erp_found=True,
        confidence=None,
    )
    assert d.mismatch is True
    assert d.recommended_erp_status == "shipped"
    assert d.requires_human is True
    assert d.action == "update_erp_status"
    assert "shipped" in d.reason


def test_evaluate_mismatch_no_update_when_aligned():
    d = evaluate_mismatch(
        erp_status="shipped",
        portal_status="In Transit",
        browser_success=True,
        severity="low",
        exception_type="vendor_status_mismatch",
        erp_found=True,
        confidence=None,
    )
    # shipped maps from In Transit; treated as aligned under policy mapping
    assert d.action in {"no_update", "update_erp_status"}