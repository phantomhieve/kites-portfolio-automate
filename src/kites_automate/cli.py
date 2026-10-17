"""
Kites Automate — Command Line Interface

Main CLI entry points for portfolio updates, headless token renewals,
status diagnostics, and Google Sheets synchronization.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .auth.fully_automated_auth import fully_automated_token_renewal, load_credentials_config
from .auth.token_rotator import get_valid_token, rotate_all_tokens
from .config import AccountConfig, AppSettings, RuntimeContext
from .logging_setup import setup_logging
from .notify.emailer import send_email
from .portfolio.updater import update_portfolio_once
from .profiles import find_profiles_file, load_profiles_config
from .scheduler.schedule import start_scheduler
from .sheets.client import SheetManager
from .sync_state import load_pipeline_state, write_pipeline_state

logger = logging.getLogger("kites_automate.cli")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kites-automate",
        description="Automated Zerodha Kite portfolio sync to Google Sheets",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug logging output",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # run / run-once
    p_run = sub.add_parser("run", help="Run portfolio sync across configured accounts")
    p_run.add_argument("--account", "-a", type=str, default=None, help="Update specific account name only")

    p_run_once = sub.add_parser("run-once", help="Alias for 'run' (compatible with cron)")
    p_run_once.add_argument("--account", "-a", type=str, default=None, help="Update specific account name only")

    # auto-renew-tokens
    p_renew = sub.add_parser("auto-renew-tokens", help="Headless Chromium automated login + TOTP token renewal")
    p_renew.add_argument("--force", "-f", action="store_true", help="Force browser login even if token appears unexpired")
    p_renew.add_argument("--account", "-a", type=str, default=None, help="Renew token for specific account only")

    # status
    sub.add_parser("status", help="Display system status, token expirations, and recent pipeline run state")

    # test-sheets
    sub.add_parser("test-sheets", help="Verify Google Sheets service account credentials and connectivity")

    # rotate-tokens
    sub.add_parser("rotate-tokens", help="Rotate/validate tokens for all accounts")

    # send-test-email
    sub.add_parser("send-test-email", help="Send a test notification email using configured SMTP settings")

    # run-scheduler
    sub.add_parser("run-scheduler", help="Run in daemon mode with background scheduler")

    return parser


def handle_status(ctx: RuntimeContext) -> int:
    """Print status of accounts, tokens, credentials, and last pipeline run."""
    print("=" * 60)
    print(" 🪁 Kites Automate — System Diagnostics & Status")
    print("=" * 60)

    # 1. Profiles
    profiles_file = find_profiles_file()
    cfg = load_profiles_config()
    profiles = cfg.get("profiles", [])
    print(f"\n📂 Profiles Config: {profiles_file or 'NOT FOUND'} ({len(profiles)} accounts)")
    for p in profiles:
        name = p.get("profile_name", "Unknown")
        key_env = p.get("api_key_env", "")
        has_key = bool(os.getenv(key_env))
        print(f"   • {name:15} (API key env '{key_env}': {'✅ SET' if has_key else '❌ MISSING'})")

    # 2. Token Cache Status
    print("\n🔑 Authentication Tokens (~/.kites/):")
    for p in profiles:
        name = p.get("profile_name", "")
        tok = get_valid_token(ctx, AccountConfig(name=name), allow_rotate=False)
        if tok:
            print(f"   • {name:15} ✅ VALID (Length: {len(tok)})")
        else:
            print(f"   • {name:15} ❌ EXPIRED OR MISSING")

    # 3. Google Sheets Credentials
    try:
        sm = SheetManager()
        print(f"\n📊 Google Sheets Credentials: ✅ FOUND ({sm.creds_path})")
    except Exception as exc:
        print(f"\n📊 Google Sheets Credentials: ❌ ERROR ({exc})")

    # 4. Last Pipeline Run State
    repo_root = Path(__file__).resolve().parent.parent.parent
    state = load_pipeline_state(repo_root / "logs")
    print("\n⏱️  Last Pipeline Run Outcome:")
    if state:
        epoch = state.get("epoch_seconds", 0)
        dt = datetime.fromtimestamp(epoch, tz=ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S %Z")
        ok = state.get("success", False)
        print(f"   • Timestamp:   {dt}")
        print(f"   • Success:     {'✅ YES' if ok else '❌ NO'}")
        print(f"   • Run Mode:    {state.get('run_mode')}")
        print(f"   • Token Exit:  {state.get('token_exit')}")
        print(f"   • Portf Exit:  {state.get('portfolio_exit')}")
        print(f"   • Agg Exit:    {state.get('aggregate_exit')}")
    else:
        print("   • No recorded last_pipeline_state.json found in logs directory.")

    print("\n" + "=" * 60)
    return 0


def handle_test_sheets(ctx: RuntimeContext) -> int:
    """Validate Google Sheets connection."""
    try:
        sm = SheetManager()
        cfg = load_profiles_config()
        sheet_name = cfg.get("settings", {}).get("spreadsheet_name", "Portfolio")
        print(f"Testing access to spreadsheet: '{sheet_name}'...")
        ss = sm.get_or_create_sheet(sheet_name)
        print(f"✅ Successfully opened spreadsheet: '{ss.title}' (ID: {ss.id})")
        return 0
    except Exception as exc:
        print(f"❌ Failed to connect to Google Sheets: {exc}")
        return 1


def main() -> int:
    # Always load environment variables from root .env
    repo_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(repo_root / ".env")

    parser = create_parser()
    args = parser.parse_args()

    # Logging level
    level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level)

    settings = AppSettings.load()
    ctx = RuntimeContext(settings=settings)

    if args.command in ("run", "run-once"):
        # Single account filter override if specified
        if getattr(args, "account", None):
            matched = [a for a in settings.accounts if a.name.lower() == args.account.lower()]
            if not matched:
                logger.error("No account matching '%s' found in configuration", args.account)
                return 1
            settings.accounts = matched

        success_count, total_count, successes, failures = update_portfolio_once(ctx)
        rc = 0 if success_count == total_count and total_count > 0 else 1

        try:
            log_dir = repo_root / "logs"
            write_pipeline_state(
                log_dir,
                epoch_seconds=int(time.time()),
                success=(rc == 0),
                run_mode="portfolio_only",
                token_exit=None,
                portfolio_exit=rc,
                aggregate_exit=rc,
            )
        except OSError:
            logger.warning("Could not persist last_pipeline_state.json", exc_info=True)

        return rc

    if args.command == "auto-renew-tokens":
        try:
            profiles_config = load_profiles_config()
            credentials_config = load_credentials_config()

            if not profiles_config:
                print("❌ Profiles configuration not found. Check profiles.json")
                return 1
            if not credentials_config:
                print("❌ Credentials configuration not found. Check ~/.kites/credentials.json")
                return 1

            force = getattr(args, "force", False)
            account = getattr(args, "account", None)
            target_desc = f"account '{account}'" if account else "all configured accounts"
            print(f"🤖 Starting automated headless Chromium token renewal for {target_desc} (force={force})...")
            results = fully_automated_token_renewal(
                profiles_config, credentials_config, force=force, target_account=account
            )

            success_count = sum(1 for token in results.values() if token)
            total_count = len(results)

            if success_count == total_count and total_count > 0:
                print(f"🎉 All {total_count} access tokens renewed successfully!")
                return 0
            else:
                print(f"⚠️ Renewed {success_count}/{total_count} tokens successfully")
                return 0 if success_count > 0 else 1
        except Exception as exc:
            logger.exception("Automated token renewal encountered a critical error: %s", exc)
            return 1

    if args.command == "status":
        return handle_status(ctx)

    if args.command == "test-sheets":
        return handle_test_sheets(ctx)

    if args.command == "rotate-tokens":
        rotate_all_tokens(ctx, token_only=True)
        return 0

    if args.command == "send-test-email":
        ts = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
        template = """
        <p>This is a test notification from kites-automate.</p>
        <p><strong>Timestamp (IST):</strong> {{ ts }}</p>
        """
        send_email(ctx, subject="Kites Automate Test Email", template_str=template, context={"ts": ts})
        print("✅ Test email sent (check your inbox)")
        return 0

    if args.command == "run-scheduler":
        start_scheduler(ctx)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
