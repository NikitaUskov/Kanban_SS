"""Small synchronous SMTP adapter used for account emails."""

import smtplib
from email.message import EmailMessage

from app.config import get_settings


class EmailDeliveryError(RuntimeError):
    pass


def send_email(recipient: str, subject: str, text: str) -> bool:
    """Send one UTF-8 text email. Return False when email is intentionally disabled."""

    settings = get_settings()
    if not settings.email_enabled:
        return False
    required = [settings.smtp_host, settings.email_from_address]
    if not all(required):
        raise EmailDeliveryError("SMTP включён, но SMTP_HOST или EMAIL_FROM_ADDRESS не настроены")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.email_from_name} <{settings.email_from_address}>"
    message["To"] = recipient
    message.set_content(text)

    try:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as smtp:
            smtp.ehlo()
            if settings.smtp_use_tls:
                smtp.starttls()
                smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError(str(exc)) from exc
    return True
