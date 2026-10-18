"""TLS SMTP or HTTPS email providers. Never silently pretend to deliver an email."""
import base64
import http.client
import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr
from uuid import UUID

from email_validator import validate_email
from flask import current_app


class MailConfigurationError(Exception):
    pass


class DeliveryUncertain(Exception):
    """The provider may have accepted a message. Human review precedes retry."""


class DeliveryRejected(Exception):
    pass


def address(value):
    if "\n" in value or "\r" in value:
        raise ValueError("INVALID_EMAIL")
    return validate_email(value, check_deliverability=False).normalized


def deliver(*, to, subject, body, message_key, cc=None, pdf=None):
    cfg = current_app.config
    backend = cfg["EMAIL_BACKEND"]
    if backend not in ("smtp", "sendgrid", "resend") or not cfg["MAIL_FROM"]:
        raise MailConfigurationError("MAIL_NOT_CONFIGURED")
    sender, recipient = address(cfg["MAIL_FROM"]), address(to)
    copy = address(cc) if cc else None
    if copy == recipient:
        copy = None
    if backend == "smtp":
        if not cfg["SMTP_HOST"] or cfg["SMTP_SECURITY"] not in ("starttls", "ssl"):
            raise MailConfigurationError("SMTP_TLS_REQUIRED")
        message = EmailMessage()
        message["From"] = formataddr((cfg["ORGANIZATION_NAME"], sender))
        message["To"] = recipient
        if copy:
            message["Cc"] = copy
        message["Subject"] = subject
        message["Message-ID"] = f"<{message_key}@{sender.split('@')[1]}>"
        message.set_content(body)
        if pdf:
            message.add_attachment(pdf, maintype="application", subtype="pdf", filename="financny-prehlad.pdf")
        context = ssl.create_default_context()
        transport = smtplib.SMTP_SSL if cfg["SMTP_SECURITY"] == "ssl" else smtplib.SMTP
        sending = False
        try:
            with transport(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=30,
                           **({"context": context} if transport is smtplib.SMTP_SSL else {})) as server:
                if cfg["SMTP_SECURITY"] == "starttls":
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                if cfg["SMTP_USERNAME"]:
                    server.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
                sending = True
                refused = server.send_message(message, from_addr=sender, to_addrs=[recipient] + ([copy] if copy else []))
                if refused:
                    # A subset may already have received it; don't automatically resend.
                    raise DeliveryUncertain("SMTP_PARTIAL_RECIPIENTS")
            return str(message["Message-ID"])
        except DeliveryUncertain:
            raise
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
            raise DeliveryRejected(type(exc).__name__) from None
        except (OSError, smtplib.SMTPException) as exc:
            if sending:
                raise DeliveryUncertain(type(exc).__name__) from None
            raise DeliveryRejected(type(exc).__name__) from None
    if backend == "resend":
        return deliver_resend(cfg, sender=sender, recipient=recipient, copy=copy,
                              subject=subject, body=body, message_key=message_key, pdf=pdf)
    if not cfg["SENDGRID_API_KEY"]:
        raise MailConfigurationError("SENDGRID_KEY_REQUIRED")
    personalization = {"to": [{"email": recipient}]}
    if copy:
        personalization["cc"] = [{"email": copy}]
    payload = {
        "personalizations": [personalization],
        "from": {"email": sender, "name": cfg["ORGANIZATION_NAME"]},
        "subject": subject, "content": [{"type": "text/plain", "value": body}],
        "custom_args": {"report_key": message_key},
    }
    if pdf:
        payload["attachments"] = [{"content": base64.b64encode(pdf).decode(),
                                   "filename": "financny-prehlad.pdf", "type": "application/pdf", "disposition": "attachment"}]
    request = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {cfg['SENDGRID_API_KEY']}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 202:
                raise DeliveryUncertain("UNEXPECTED_PROVIDER_STATUS")
            return response.headers.get("X-Message-Id", message_key)[:200]
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            raise DeliveryRejected(f"SENDGRID_HTTP_{exc.code}") from None
        raise DeliveryUncertain(f"SENDGRID_HTTP_{exc.code}") from None
    except (OSError, urllib.error.URLError):
        raise DeliveryUncertain("SENDGRID_CONNECTION_LOST") from None


def deliver_resend(cfg, *, sender, recipient, copy, subject, body, message_key, pdf):
    if not cfg["RESEND_API_KEY"]:
        raise MailConfigurationError("RESEND_KEY_REQUIRED")
    payload = {"from": formataddr((cfg["ORGANIZATION_NAME"], sender)),
               "to": [recipient], "subject": subject, "text": body}
    if copy:
        payload["cc"] = [copy]
    if pdf:
        payload["attachments"] = [{"content": base64.b64encode(pdf).decode("ascii"),
                                   "filename": "financny-prehlad.pdf"}]
    request = urllib.request.Request(
        "https://api.resend.com/emails", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {cfg['RESEND_API_KEY']}",
                 "Content-Type": "application/json", "Idempotency-Key": message_key}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise DeliveryUncertain("RESEND_UNEXPECTED_STATUS")
            # Require the documented acknowledgement; HTTP success alone is insufficient.
            # Do not include provider response bodies in exceptions or persistent logs.
            raw = response.read(65537)
            if len(raw) > 65536:
                raise DeliveryUncertain("RESEND_INVALID_RESPONSE")
            try:
                data = json.loads(raw)
                reference = data.get("id") if isinstance(data, dict) else None
                if not isinstance(reference, str) or len(reference) != 36:
                    raise ValueError
                UUID(reference)
            except (ValueError, UnicodeDecodeError):
                raise DeliveryUncertain("RESEND_INVALID_RESPONSE") from None
            return reference
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise MailConfigurationError(f"RESEND_HTTP_{exc.code}") from None
        # A conflicting key can refer to another in-flight or accepted request.
        if 400 <= exc.code < 500 and exc.code not in (408, 409):
            raise DeliveryRejected(f"RESEND_HTTP_{exc.code}") from None
        raise DeliveryUncertain(f"RESEND_HTTP_{exc.code}") from None
    except (OSError, urllib.error.URLError, http.client.HTTPException):
        raise DeliveryUncertain("RESEND_CONNECTION_LOST") from None
