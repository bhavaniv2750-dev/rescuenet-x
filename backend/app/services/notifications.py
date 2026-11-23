"""Notification transports with honest delivery status.

Three transports exist:
* DEV_OUTBOX (development only): the message is stored in the database so a developer can read the code. NOTHING is sent to any
  mailbox or phone. Status NOT_DELIVERED_DEV.
* SMTP (configured with SMTP_HOST/SMTP_FROM): the message is handed to the SMTP server. Status ACCEPTED_BY_SMTP means the
  server accepted it; SMTP gives no proof the person received it, so this is never reported as "delivered". A failure is FAILED.
* DISABLED: no provider. Status DISABLED. SMS is always DISABLED until a real SMS provider is integrated.

The message body (which holds the code or link) is stored only by the development outbox and is never logged. Callers must
phrase user-facing text from the returned status, never assume success.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import NotificationOutbox

log = logging.getLogger("rescuenet.notifications")

NOT_DELIVERED_DEV = "NOT_DELIVERED_DEV"
ACCEPTED_BY_SMTP = "ACCEPTED_BY_SMTP"
FAILED = "FAILED"
DISABLED = "DISABLED"

DEV_NOTICE = "DEVELOPMENT OUTBOX: nothing was delivered to any real mailbox or phone."


@dataclass
class Message:
    channel: str            # EMAIL | SMS
    to: str
    subject: str
    body: str
    purpose: str
    user_id: Optional[int] = None


@dataclass
class DeliveryResult:
    transport: str
    status: str
    detail: str = ""


def mask_email(address: str) -> str:
    local, _, domain = (address or "").partition("@")
    return (local[:1] + "***@" + domain) if domain else "***"


def mask_phone(number: str) -> str:
    digits = "".join(c for c in (number or "") if c.isdigit())
    return ("*" * max(0, len(digits) - 3)) + digits[-3:] if digits else "***"


# ------------------------------------------------------------------ transports

class DevOutboxTransport:
    name = "DEV_OUTBOX"

    def send(self, msg: Message) -> DeliveryResult:
        return DeliveryResult(self.name, NOT_DELIVERED_DEV, "stored in the development outbox only")


class SmtpTransport:
    name = "SMTP"

    def send(self, msg: Message) -> DeliveryResult:
        mail = EmailMessage()
        mail["From"], mail["To"], mail["Subject"] = settings.SMTP_FROM, msg.to, msg.subject
        mail.set_content(msg.body)
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_S) as smtp:
                if settings.SMTP_STARTTLS:
                    smtp.starttls(context=ssl.create_default_context())
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.send_message(mail)
            return DeliveryResult(self.name, ACCEPTED_BY_SMTP, "accepted by the SMTP server; inbox delivery is not confirmed")
        except Exception as exc:  # never include the exception text: it can echo addresses or credentials
            log.warning("SMTP send failed: %s", type(exc).__name__)
            return DeliveryResult(self.name, FAILED, f"SMTP error ({type(exc).__name__})")


class DisabledTransport:
    name = "DISABLED"

    def __init__(self, reason: str):
        self.reason = reason

    def send(self, msg: Message) -> DeliveryResult:
        return DeliveryResult(self.name, DISABLED, self.reason)


def email_transport():
    if settings.smtp_configured:
        return SmtpTransport()
    if settings.is_development:
        return DevOutboxTransport()
    return DisabledTransport("no email provider is configured")


def sms_transport():
    # No SMS provider is integrated. Phone verification stays unavailable (and phones stay unverified) until one is.
    return DisabledTransport("no SMS provider is configured")


def capabilities() -> dict:
    e, s = email_transport(), sms_transport()
    return {
        "environment": settings.RESCUENET_ENV,
        "email_delivery": {"transport": e.name, "delivers_to_real_mailboxes": e.name == "SMTP"},
        "sms_delivery": {"transport": s.name, "delivers_to_real_phones": False},
        "phone_verification_available": s.name != "DISABLED",
    }


# ------------------------------------------------------------------ sending

def notify(msg: Message) -> NotificationOutbox:
    """Hand a message to the right transport and record the outcome. Uses its own database session so it can run in a
    background task. The recorded body is kept only for the development outbox."""
    transport = email_transport() if msg.channel == "EMAIL" else sms_transport()
    result = transport.send(msg)
    db: Session = SessionLocal()
    try:
        row = NotificationOutbox(
            user_id=msg.user_id, channel=msg.channel, purpose=msg.purpose,
            recipient_masked=mask_email(msg.to) if msg.channel == "EMAIL" else mask_phone(msg.to),
            transport=result.transport, delivery_status=result.status, detail=result.detail[:200],
            subject=msg.subject if result.transport == "DEV_OUTBOX" else None,
            body=msg.body if result.transport == "DEV_OUTBOX" else None)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def dev_outbox(limit: int = 50) -> list:
    """Messages held by the development outbox (empty outside development)."""
    if not settings.is_development:
        return []
    db = SessionLocal()
    try:
        rows = db.query(NotificationOutbox).filter(NotificationOutbox.transport == "DEV_OUTBOX").order_by(NotificationOutbox.id.desc()).limit(limit).all()
        return [{"id": r.id, "channel": r.channel, "purpose": r.purpose, "to": r.recipient_masked, "subject": r.subject,
                 "body": r.body, "created_at": r.created_at, "delivery_status": r.delivery_status} for r in rows]
    finally:
        db.close()
