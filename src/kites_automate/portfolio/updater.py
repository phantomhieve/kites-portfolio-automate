import logging
from datetime import datetime, timezone
from typing import Optional

from ..config import RuntimeContext, AppSettings, AccountConfig
from ..auth.token_rotator import get_valid_token
from ..notify.emailer import send_email, send_failure_email
from ..kites_adapter import get_adapter
from ..legacy_adapter import run_legacy

logger = logging.getLogger(__name__)


def _update_single(ctx: RuntimeContext, effective_settings: AppSettings, account: Optional[AccountConfig]) -> None:
    local_ctx = RuntimeContext(settings=effective_settings)

    try:
        # Legacy mode: run existing project flow and return
        if effective_settings.legacy and effective_settings.legacy.enabled:
            logger.info("Running legacy project for %s", account.name if account else "default")
            run_legacy(local_ctx)
            return

        token = get_valid_token(local_ctx, account)
        if not token:
            msg = f"No valid token available; aborting portfolio update for {account.name if account else 'default'}"
            logger.error(msg)
            send_failure_email(local_ctx, subject="Kites portfolio update failed", details=msg)
            return

        adapter = get_adapter(local_ctx)
        adapter.update_portfolio(local_ctx, token)

        now_str = datetime.now(timezone.utc).isoformat()
        logger.info("Portfolio updated successfully for %s at %s", account.name if account else "default", now_str)

        email_tpl = """
        <p>Portfolio update completed.</p>
        <p>Account: {{ account }}</p>
        <p>Timestamp (UTC): {{ ts }}</p>
        """
        try:
            send_email(local_ctx, subject="Kites portfolio updated", template_str=email_tpl, context={"ts": now_str, "account": account.name if account else "default"})
        except Exception as exc:
            logger.warning("Failed sending notification email for %s: %s", account.name if account else "default", exc)
    except Exception as exc:
        details = f"Account: {account.name if account else 'default'}\nError: {exc}"
        logger.exception("Update failed for %s", account.name if account else "default")
        send_failure_email(local_ctx, subject="Kites portfolio update failed", details=details)


def update_portfolio_once(ctx: RuntimeContext) -> None:
    base = ctx.settings
    if base.accounts:
        for acct in base.accounts:
            eff = AppSettings.build_settings_for_account(base, acct)
            _update_single(ctx, eff, acct)
    else:
        _update_single(ctx, base, None)
