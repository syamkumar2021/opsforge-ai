import logging
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Union

import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _as_recipients(to: Union[str, List[str]]) -> List[str]:
    if isinstance(to, list):
        return [x.strip() for x in to if x and x.strip()]
    return [x.strip() for x in str(to).split(",") if x.strip()]


async def send_email(
    subject: str,
    body: str,
    to: Optional[Union[str, List[str]]] = None,
) -> Dict[str, Any]:
    """
    Send a real SMTP email.
    Locally this goes to Mailpit; in production point SMTP_* to real provider.
    """
    recipients = _as_recipients(to or settings.notify_email_to)
    sent_at = datetime.now(timezone.utc).isoformat()

    if not recipients:
        return {
            "status": "failed",
            "error": "No recipients configured",
            "to": [],
            "subject": subject,
            "sent_at": sent_at,
        }

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_tls,
        )
        logger.info("Email sent | to=%s | subject=%s", recipients, subject)
        return {
            "status": "sent",
            "to": recipients,
            "from": settings.smtp_from,
            "subject": subject,
            "sent_at": sent_at,
            "provider": "smtp",
            "smtp_host": settings.smtp_host,
        }
    except Exception as e:
        logger.exception("Email send failed: %s", e)
        return {
            "status": "failed",
            "to": recipients,
            "from": settings.smtp_from,
            "subject": subject,
            "sent_at": sent_at,
            "error": str(e),
            "provider": "smtp",
            "smtp_host": settings.smtp_host,
        }