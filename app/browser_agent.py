import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from playwright.async_api import (
    Browser,
    Playwright,
    async_playwright,
)

from app.config import get_settings
from app.decorators import async_error_handler, async_log, async_retry, langsmith_trace

logger = logging.getLogger(__name__)
settings = get_settings()


class BrowserAgent:
    """
    Autonomous Browser Agent using Playwright (async).

    Responsibilities:
    - Launch and manage a Chromium browser instance
    - Visit pages and extract shipping / vendor status information
    - Return structured evidence for the multi-agent system

    Note:
    In production you would point this agent to real vendor portals.
    For reliability in demos and tests we use a stable public page
    while still performing real browser automation (page.goto, inner_text, etc.).
    """

    def __init__(self) -> None:
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.headless: bool = settings.playwright_headless

    @async_log
    @async_error_handler()
    @langsmith_trace(name="browser_agent_start")
    async def start(self) -> None:
        """Launch the Playwright browser instance."""
        if self.browser is not None:
            return

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        logger.info("Playwright browser started successfully")

    @async_log
    @async_error_handler()
    @langsmith_trace(name="browser_agent_stop")
    async def stop(self) -> None:
        """Gracefully close browser and Playwright."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            logger.info("Playwright browser closed")

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
            logger.info("Playwright stopped")

    @async_log
    @async_retry(attempts=2, min_wait=1, max_wait=5)
    @async_error_handler()
    @langsmith_trace(name="browser_check_vendor_status", run_type="tool")
    async def check_vendor_status(
        self,
        order_number: str,
        tracking_number: str | None = None,
        exception_type: str | None = None,
    ) -> dict:
        if self.browser is None:
            await self.start()

        context = await self.browser.new_context()
        page = await context.new_page()

        evidence = {
            "order_number": order_number,
            "tracking_number": tracking_number,
            "portal_status": None,
            "eta": None,
            "source": "playwright",
            "success": False,
            "raw_text": "",
        }

        try:
            # Same-container URL
            base = "http://127.0.0.1:8000"
            url = f"{base}/mock/vendor-portal/{order_number}"
            if exception_type:
                url += f"?exception_type={exception_type}"

            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            portal_status = (await page.locator("#portal-status").inner_text()).strip()
            eta = (await page.locator("#eta").inner_text()).strip()
            tracking = (await page.locator("#tracking-number").inner_text()).strip()
            raw = (await page.locator("body").inner_text())[:300]

            evidence.update({
                "portal_status": portal_status,
                "eta": None if eta == "TBD" else eta,
                "tracking_number": tracking,
                "raw_text": raw,
                "success": True,
                "last_update": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            evidence["portal_status"] = "error_collecting_data"
            evidence["raw_text"] = str(e)
            evidence["success"] = False
        finally:
            await context.close()

        return evidence


# Global singleton instance used by the rest of the application
browser_agent = BrowserAgent()