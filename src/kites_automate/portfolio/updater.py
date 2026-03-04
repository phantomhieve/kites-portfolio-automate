import logging
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from typing import Optional

from ..config import RuntimeContext, AppSettings, AccountConfig
from ..auth.token_rotator import get_valid_token
from ..notify.emailer import send_email, send_failure_email
from ..kites_adapter import get_adapter
from ..legacy_adapter import run_legacy

logger = logging.getLogger(__name__)


def _update_single(ctx: RuntimeContext, effective_settings: AppSettings, account: Optional[AccountConfig]):
    """Returns (success: bool, adapter_result: dict|None)."""
    local_ctx = RuntimeContext(settings=effective_settings)

    try:
        # Legacy mode: run existing project flow and send success notification
        if effective_settings.legacy and effective_settings.legacy.enabled:
            logger.info("Running legacy project for %s", account.name if account else "default")
            run_legacy(local_ctx)
            logger.info("Legacy run completed for %s", account.name if account else "default")
            return True, None

        token = get_valid_token(local_ctx, account)
        if not token:
            msg = f"No valid token available; aborting portfolio update for {account.name if account else 'default'}"
            logger.error(msg)
            return False, None

        adapter = get_adapter(local_ctx)
        result = adapter.update_portfolio(local_ctx, token, account)

        ist_now = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
        logger.info("Portfolio updated successfully for %s at %s IST", account.name if account else "default", ist_now)
        return True, result
    except Exception as exc:
        details = f"Account: {account.name if account else 'default'}\nError: {exc}"
        logger.exception("Update failed for %s", account.name if account else "default")
        send_failure_email(local_ctx, subject="Kites portfolio update failed", details=details)
        return False, None


def update_portfolio_once(ctx: RuntimeContext):
    base = ctx.settings
    success_count = 0
    total_count = 0
    successes = []
    failures = []
    # Collect per-profile summaries so we can write the Summary sheet at the end
    portfolio_summaries = {}
    _last_sheet_manager = None
    _last_spreadsheet = None
    _last_summary_sheet_name = "Summary"

    if base.accounts:
        total_count = len(base.accounts)
        for i, acct in enumerate(base.accounts):
            eff = AppSettings.build_settings_for_account(base, acct)
            try:
                ok, result = _update_single(ctx, eff, acct)
                if ok:
                    success_count += 1
                    successes.append(acct.name)
                    # Accumulate summary data from the adapter result
                    if result and isinstance(result, dict):
                        profile_name = result.get("profile_name", acct.name)
                        if result.get("summary") is not None:
                            portfolio_summaries[profile_name] = result["summary"]
                        if result.get("sheet_manager"):
                            _last_sheet_manager = result["sheet_manager"]
                        if result.get("spreadsheet"):
                            _last_spreadsheet = result["spreadsheet"]
                        if result.get("summary_sheet_name"):
                            _last_summary_sheet_name = result["summary_sheet_name"]
                else:
                    failures.append(acct.name)
            except Exception as exc:
                logger.error("Update failed for %s: %s", acct.name, exc)
                failures.append(acct.name)
            # Delay between accounts to avoid Google Sheets write quota (429)
            if i < total_count - 1:
                import time
                logger.info("Waiting 15 seconds before next account to avoid rate limits...")
                time.sleep(15)

        # Write the Summary sheet once all profiles are done
        if portfolio_summaries and _last_sheet_manager and _last_spreadsheet:
            try:
                import time
                import importlib
                logger.info("Waiting 5 seconds before writing Summary sheet...")
                time.sleep(5)
                logger.info("Writing Summary sheet with %d profile(s)...", len(portfolio_summaries))
                # Import SummaryManager from kites_core
                summary_mod = importlib.import_module("kites.sheets")
                SummaryManager = getattr(summary_mod, "SummaryManager")
                summary_manager = SummaryManager(_last_sheet_manager)
                summary_ws = _last_sheet_manager.get_or_create_worksheet(_last_spreadsheet, _last_summary_sheet_name)
                overall = summary_manager.update_summary_sheet(summary_ws, portfolio_summaries, force_formatting=False)
                if overall:
                    logger.info("Summary sheet updated. Total value: %s", getattr(overall, "total_current_value", "N/A"))
                else:
                    logger.info("Summary sheet updated.")
            except Exception as exc:
                logger.warning("Summary sheet update failed: %s", exc)
    else:
        total_count = 1
        try:
            ok, _ = _update_single(ctx, base, None)
            if ok:
                success_count += 1
                successes.append("default")
            else:
                failures.append("default")
        except Exception as exc:
            logger.error("Update failed: %s", exc)
            failures.append("default")

    # Send single summary email after all updates (always, if at least one attempted)
    if total_count > 0:
        ist_now = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
        email_tpl = """
        <h2>📊 Portfolio Update Summary</h2>
        <p><strong>Completed:</strong> {{ success_count }}/{{ total_count }} accounts</p>
        <p><strong>Timestamp (IST):</strong> {{ ts }}</p>
        {% if successes %}
        <p><strong>✅ Success:</strong></p>
        <ul>
        {% for name in successes %}
          <li>{{ name }}</li>
        {% endfor %}
        </ul>
        {% endif %}
        {% if failures %}
        <p><strong>❌ Failed:</strong></p>
        <ul>
        {% for name in failures %}
          <li>{{ name }}</li>
        {% endfor %}
        </ul>
        {% endif %}
        <p>Check your Google Sheets for the latest data.</p>
        """
        try:
            send_email(
                ctx,
                subject="Kites Portfolio Update Summary",
                template_str=email_tpl,
                context={
                    "ts": ist_now,
                    "success_count": str(success_count),
                    "total_count": str(total_count),
                    "successes": successes,
                    "failures": failures,
                },
            )
            logger.info("Summary notification sent: %d/%d accounts successful", success_count, total_count)
        except Exception as exc:
            logger.warning("Failed sending summary email: %s", exc)
    # Return counts so callers can make decisions on exit codes / messages
    return success_count, total_count, successes, failures
