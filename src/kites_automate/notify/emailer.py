import logging
import smtplib
from email.mime.text import MIMEText
from typing import Dict

from jinja2 import Template

from ..config import RuntimeContext

logger = logging.getLogger(__name__)


def is_email_configured(ctx: RuntimeContext) -> bool:
    """True only when SMTP and addresses are present (values may still be invalid)."""
    cfg = ctx.settings.email
    return bool(cfg.smtp_host and cfg.email_from and cfg.email_to)


def send_email(ctx: RuntimeContext, subject: str, template_str: str, context: Dict[str, str]) -> None:
    email_cfg = ctx.settings.email

    # Basic validation to provide clear guidance instead of connection refused
    if not email_cfg.smtp_host:
        raise ValueError(
            "SMTP host is not configured. Set SMTP_HOST in environment or update config/defaults.yaml."
        )
    if not email_cfg.email_from:
        raise ValueError("EMAIL_FROM is not configured. Set EMAIL_FROM in environment or config.")
    if not email_cfg.email_to:
        raise ValueError("EMAIL_TO is not configured. Set EMAIL_TO in environment or config.")

    body = Template(template_str).render(**context)
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = email_cfg.email_from
    msg["To"] = email_cfg.email_to

    # Choose SSL if using the typical SMTPS port 465; otherwise use STARTTLS when enabled
    use_ssl = (email_cfg.smtp_port == 465) and email_cfg.use_tls

    if use_ssl:
        server = smtplib.SMTP_SSL(host=email_cfg.smtp_host, port=email_cfg.smtp_port, timeout=15)
        try:
            if email_cfg.smtp_username and email_cfg.smtp_password:
                server.login(email_cfg.smtp_username, email_cfg.smtp_password)
            server.sendmail(email_cfg.email_from, [email_cfg.email_to], msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:
                pass
    else:
        server = smtplib.SMTP(host=email_cfg.smtp_host, port=email_cfg.smtp_port, timeout=15)
        try:
            server.ehlo()
            if email_cfg.use_tls:
                try:
                    server.starttls()
                    server.ehlo()
                except smtplib.SMTPException as exc:
                    logger.warning("STARTTLS failed: %s. Proceeding without TLS per configuration.", exc)
            if email_cfg.smtp_username and email_cfg.smtp_password:
                server.login(email_cfg.smtp_username, email_cfg.smtp_password)
            server.sendmail(email_cfg.email_from, [email_cfg.email_to], msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:
                pass

    logger.info("Email sent to %s", email_cfg.email_to)


def send_failure_email(ctx: RuntimeContext, subject: str, details: str) -> None:
    tmpl = """
    <p><strong>Failure detected</strong></p>
    <pre style="white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;">{{ details }}</pre>
    """
    try:
        send_email(ctx, subject=subject, template_str=tmpl, context={"details": details})
    except Exception as exc:
        logger.warning("Failed to send failure email: %s", exc)
