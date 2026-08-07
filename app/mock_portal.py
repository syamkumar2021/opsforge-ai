from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from datetime import date, timedelta

mock_router = APIRouter(prefix="/mock", tags=["Mock Vendor Portal"])


def portal_status_for(order_number: str, exception_type: str | None = None):
    today = date.today()
    et = (exception_type or "").lower()

    if et == "shipping_delay":
        return "Delayed", str(today + timedelta(days=5)), f"TRK-{order_number[-4:]}-DELAY"
    if et == "inventory_shortage":
        return "On Hold - Inventory", "TBD", f"TRK-{order_number[-4:]}-HOLD"
    if et == "address_issue":
        return "Exception - Address Issue", "TBD", f"TRK-{order_number[-4:]}-ADDR"

    if order_number.endswith("1"):
        return "In Transit", str(today + timedelta(days=2)), f"TRK-{order_number[-4:]}-IT"
    if order_number.endswith("2"):
        return "Out for Delivery", str(today), f"TRK-{order_number[-4:]}-OFD"
    if order_number.endswith("3"):
        return "Delivered", str(today - timedelta(days=1)), f"TRK-{order_number[-4:]}-DEL"
    if order_number.endswith("4"):
        return "Exception - Address Issue", "TBD", f"TRK-{order_number[-4:]}-ADDR"
    return "Label Created", str(today + timedelta(days=4)), f"TRK-{order_number[-4:]}-LBL"


@mock_router.get("/vendor-portal/{order_number}", response_class=HTMLResponse)
async def vendor_portal_page(order_number: str, exception_type: str | None = None):
    status, eta, tracking = portal_status_for(order_number, exception_type)
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>Vendor Portal {order_number}</title>
<style>
body{{font-family:Arial,sans-serif;margin:24px;background:#f7f9fc}}
.card{{background:#fff;padding:20px;border-radius:10px;width:560px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.label{{color:#6b7280;font-size:12px}}.value{{font-size:16px;font-weight:600}}
.status{{color:#075985}}
</style></head>
<body><div class='card'>
<h1>Vendor / Carrier Portal</h1>
<div class='label'>Order Number</div><div class='value' id='order-number'>{order_number}</div>
<div class='label'>Shipment Status</div><div class='value status' id='portal-status'>{status}</div>
<div class='label'>ETA</div><div class='value' id='eta'>{eta}</div>
<div class='label'>Tracking Number</div><div class='value' id='tracking-number'>{tracking}</div>
<div class='label'>Exception Type Context</div><div class='value' id='exception-type'>{exception_type or 'n/a'}</div>
<p id='notes'>Controlled mock portal for OpsForge Browser Agent evidence collection.</p>
</div></body></html>"""
    )
    return HTMLResponse(content=html)