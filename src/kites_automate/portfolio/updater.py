"""
Portfolio Update Orchestrator

Iterates through configured accounts, loads authentication tokens,
fetches holdings via UnifiedKitesAdapter, updates individual account worksheets,
and compiles the consolidated Summary sheet.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from ..auth.token_rotator import get_valid_token
from ..config import AccountConfig, AppSettings, RuntimeContext
from ..kites_adapter import get_adapter
from ..notify.emailer import is_email_configured, send_email, send_failure_email
from ..sheets import PortfolioSummary, SummaryManager

logger = logging.getLogger(__name__)


def _update_single(
    ctx: RuntimeContext,
    effective_settings: AppSettings,
    account: Optional[AccountConfig],
    force_formatting: bool = False,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Execute update for a single account. Returns (success, adapter_result)."""
    local_ctx = RuntimeContext(settings=effective_settings)
    account_name = account.name if account else "default"

    try:
        token = get_valid_token(local_ctx, account)
        if not token:
            logger.error("No valid access token available for account '%s'", account_name)
            return False, None

        adapter = get_adapter(local_ctx)
        result = adapter.update_portfolio(local_ctx, token, account, force_formatting=force_formatting)

        ist_now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S %Z")
        logger.info("Successfully completed portfolio update for '%s' at %s", account_name, ist_now)
        return True, result
    except Exception as exc:
        details = f"Account: {account_name}\nError: {exc}"
        logger.exception("Portfolio update failed for '%s'", account_name)
        send_failure_email(local_ctx, subject="Kites portfolio update failed", details=details)
        return False, None


def update_portfolio_once(ctx: RuntimeContext, force_formatting: bool = False) -> Tuple[int, int, List[str], List[str]]:
    """
    Run portfolio update across all configured accounts, then update the Summary sheet.
    Returns: (success_count, total_count, successful_names, failed_names)
    """
    base = ctx.settings
    success_count = 0
    total_count = 0
    successes: List[str] = []
    failures: List[str] = []

    portfolio_summaries: Dict[str, PortfolioSummary] = {}
    last_sheet_manager = None
    last_spreadsheet = None
    last_summary_sheet_name = "Summary"

    accounts_to_run = base.accounts if base.accounts else [None]  # type: ignore[list-item]
    total_count = len(accounts_to_run)

    for i, acct in enumerate(accounts_to_run):
        account_name = acct.name if acct else "default"
        logger.info("========================================")
        logger.info("Processing account %d/%d: '%s'", i + 1, total_count, account_name)
        logger.info("========================================")

        eff = AppSettings.build_settings_for_account(base, acct) if acct else base
        try:
            ok, result = _update_single(ctx, eff, acct, force_formatting=force_formatting)
            if ok and result:
                success_count += 1
                successes.append(account_name)
                profile_name = result.get("profile_name", account_name)
                summary_obj = result.get("summary")
                if isinstance(summary_obj, PortfolioSummary):
                    portfolio_summaries[profile_name] = summary_obj
                if result.get("sheet_manager"):
                    last_sheet_manager = result["sheet_manager"]
                if result.get("spreadsheet"):
                    last_spreadsheet = result["spreadsheet"]
                if result.get("summary_sheet_name"):
                    last_summary_sheet_name = result["summary_sheet_name"]
            else:
                failures.append(account_name)
        except Exception as exc:
            logger.error("Unexpected error for account '%s': %s", account_name, exc)
            failures.append(account_name)

        # Quota delay between accounts to avoid hitting Google Sheets rate limits
        if i < total_count - 1:
            logger.info("Waiting 10s before processing next account to respect API quotas...")
            time.sleep(10)

    # Update Summary Sheet across all portfolios
    if portfolio_summaries and last_sheet_manager and last_spreadsheet:
        try:
            logger.info("----------------------------------------")
            logger.info("Generating consolidated Summary sheet with %d accounts...", len(portfolio_summaries))
            time.sleep(3)
            summary_mgr = SummaryManager(last_sheet_manager)
            summary_ws = last_sheet_manager.get_or_create_worksheet(last_spreadsheet, last_summary_sheet_name)
            overall = summary_mgr.update_summary_sheet(summary_ws, portfolio_summaries, force_formatting=force_formatting)
            if overall:
                logger.info(
                    "Summary sheet updated successfully! Total Portfolio Value: ₹%.2f, Total P&L: ₹%.2f (%.2f%%)",
                    overall.total_current_value,
                    overall.total_pnl,
                    overall.overall_return_percentage,
                )
        except Exception as exc:
            logger.warning("Consolidated summary sheet update encountered an error: %s", exc)

    # Send optional email notification
    if total_count > 0 and is_email_configured(ctx):
        ist_now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S %Z")
        email_tpl = """
        <h2>📊 Portfolio Update Summary</h2>
        <p><strong>Completed:</strong> {{ success_count }}/{{ total_count }} accounts</p>
        <p><strong>Timestamp (IST):</strong> {{ ts }}</p>
        {% if successes %}
        <p><strong>✅ Successful Accounts:</strong></p>
        <ul>
        {% for name in successes %}
          <li>{{ name }}</li>
        {% endfor %}
        </ul>
        {% endif %}
        {% if failures %}
        <p><strong>❌ Failed Accounts:</strong></p>
        <ul>
        {% for name in failures %}
          <li>{{ name }}</li>
        {% endfor %}
        </ul>
        {% endif %}
        <p>Check your Google Sheets for live portfolio balances.</p>
        """
        try:
            send_email(
                ctx,
                subject=f"Kites Portfolio Update: {success_count}/{total_count} Accounts Succeeded",
                template_str=email_tpl,
                context={
                    "ts": ist_now,
                    "success_count": str(success_count),
                    "total_count": str(total_count),
                    "successes": successes,
                    "failures": failures,
                },
            )
            logger.info("Summary notification email sent successfully.")
        except Exception as exc:
            logger.warning("Could not dispatch summary email: %s", exc)
    elif total_count > 0:
        logger.debug("SMTP not configured; skipping email notification.")

    return success_count, total_count, successes, failures
