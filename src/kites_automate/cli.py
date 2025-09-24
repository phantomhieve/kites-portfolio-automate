import argparse
import logging
import os
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .config import AppSettings, RuntimeContext
from .logging_setup import setup_logging
from .scheduler.schedule import start_scheduler
from .portfolio.updater import update_portfolio_once
from .auth.token_rotator import rotate_all_tokens
from .auth.fully_automated_auth import fully_automated_token_renewal, load_credentials_config
from .notify.emailer import send_email


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kites-automate", description="Kites automation service")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run-once", help="Run one portfolio update now")
    sub.add_parser("run-scheduler", help="Start scheduler for monthly updates")
    sub.add_parser("rotate-tokens", help="Rotate/refresh tokens now (all accounts or legacy)")
    sub.add_parser("auto-renew-tokens", help="Fully automated token renewal with browser automation")
    sub.add_parser("send-test-email", help="Send a test email using configured SMTP settings")

    return parser


def main() -> int:
    setup_logging(logging.INFO)
    parser = create_parser()
    args = parser.parse_args()

    settings = AppSettings.load()
    ctx = RuntimeContext(settings=settings)

    if args.command == "run-once":
        update_portfolio_once(ctx)
        return 0
    if args.command == "run-scheduler":
        start_scheduler(ctx)
        return 0
    if args.command == "rotate-tokens":
        rotate_all_tokens(ctx, token_only=True)
        return 0
    if args.command == "auto-renew-tokens":
        # Load profiles config for automated renewal
        try:
            import json
            profiles_path = os.path.join(ctx.settings.legacy.project_path or ".", "profiles.json")
            if os.path.exists(profiles_path):
                with open(profiles_path, 'r') as f:
                    profiles_config = json.load(f)
                credentials_config = load_credentials_config()
                if not credentials_config:
                    print("❌ Credentials config not found. Create ~/.kites/credentials.json")
                    return 1
                
                print("🤖 Starting fully automated token renewal...")
                print("⚠️  This will use browser automation and stored credentials")
                
                results = fully_automated_token_renewal(profiles_config, credentials_config)
                
                success_count = sum(1 for token in results.values() if token)
                total_count = len(results)
                
                if success_count == total_count:
                    print(f"🎉 All {total_count} tokens renewed automatically!")
                else:
                    print(f"⚠️ Renewed {success_count}/{total_count} tokens automatically")
                
                return 0 if success_count > 0 else 1
            else:
                print(f"❌ Profiles config not found: {profiles_path}")
                return 1
        except Exception as exc:
            print(f"❌ Automated renewal failed: {exc}")
            return 1
    if args.command == "send-test-email":
        ts = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
        template = """
        <p>This is a test email from kites-automate.</p>
        <p>Timestamp (IST): {{ ts }}</p>
        """
        send_email(ctx, subject="Kites Automate Test Email", template_str=template, context={"ts": ts})
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
