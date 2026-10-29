"""Correo saliente por SMTP (Gmail/Workspace, Zoho, Brevo, SendGrid, Amazon SES, Mailgun...)."""
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage

from . import config

log = logging.getLogger("mesaya.mail")


def configured() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_FROM)


def _deliver(to: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = config.SMTP_FROM, to, subject
    msg.set_content(body)
    try:
        if config.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ssl.create_default_context(), timeout=20) as s:
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
    except Exception as e:  # nunca romper la petición del usuario por un fallo de correo
        log.error("No se pudo enviar correo a %s: %s", to, type(e).__name__)


def send(to: str, subject: str, body: str) -> bool:
    """Envía en segundo plano. Devuelve False si no hay SMTP configurado."""
    if not configured():
        return False
    threading.Thread(target=_deliver, args=(to, subject, body), daemon=True).start()
    return True
