import argparse
import logging
from datetime import datetime, timezone

from .config import AppSettings, RuntimeContext
from .logging_setup import setup_logging
from .scheduler.schedule import start_scheduler
from .portfolio.updater import update_portfolio_once
from .auth.token_rotator import rotate_all_tokens
from .notify.emailer import send_email


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kites-automate", description="Kites automation service")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run-once", help="Run one portfolio update now")
    sub.add_parser("run-scheduler", help="Start scheduler for monthly updates")
    sub.add_parser("rotate-tokens", help="Rotate/refresh tokens now (all accounts or legacy)")
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
    if args.command == "send-test-email":
        ts = datetime.now(timezone.utc).isoformat()
        template = """
        <p>This is a test email from kites-automate.</p>
        <p>Timestamp (UTC): {{ ts }}</p>
        """
        send_email(ctx, subject="Kites Automate Test Email", template_str=template, context={"ts": ts})
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
