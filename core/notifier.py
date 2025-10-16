import logging
from plyer import notification
import smtplib
from email.mime.text import MIMEText
from config.settings import settings

logger = logging.getLogger(__name__)

class Notifier:
    def desktop(self, title: str, message: str):
        if not settings.DESKTOP_NOTIFICATIONS:
            return
        try:
            notification.notify(title=title, message=message, timeout=5)
        except Exception as e:
            logger.warning(f"Desktop notification failed: {e}")

    def email(self, subject: str, body: str, to_addr: str | None = None):
        if not settings.EMAIL_ENABLED:
            return
        to_addr = to_addr or settings.EMAIL_TO
        if not to_addr:
            logger.warning("Email notify enabled but no recipient configured.")
            return
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = settings.SMTP_USER
            msg["To"] = to_addr

            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
                server.starttls()
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASS)
                server.send_message(msg)
        except Exception as e:
            logger.warning(f"Email notification failed: {e}")