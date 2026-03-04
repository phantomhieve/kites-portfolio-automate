import argparse
import logging
import os
import sys

# Ensure the local embedded `kites_core` can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../kites_core")))

from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .config import AppSettings, RuntimeContext
from .logging_setup import setup_logging
from .scheduler.schedule import start_scheduler
from .portfolio.updater import update_portfolio_once
from .auth.token_rotator import rotate_all_tokens, get_valid_token
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
    sub.add_parser("local-update", help="Invoke local tracker client via factory to update sheets")

    return parser


def main() -> int:
    setup_logging(logging.INFO)
    parser = create_parser()
    args = parser.parse_args()

    settings = AppSettings.load()
    ctx = RuntimeContext(settings=settings)

    if args.command == "run-once":
        success_count, total_count, _, _ = update_portfolio_once(ctx)
        # Non-zero exit if any account failed
        return 0 if success_count == total_count and total_count > 0 else 1
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

    if args.command == "local-update":
        # Dynamically load a factory function to construct the local client
        import importlib
        import sys as _sys
        import os as _os

        factory_spec = _os.getenv("KITES_LOCAL_FACTORY")
        local_path = _os.getenv("KITES_LOCAL_PATH")
        if not factory_spec:
            print("❌ KITES_LOCAL_FACTORY not set (expected 'module:function')")
            return 1
        if local_path and local_path not in _sys.path:
            _sys.path.insert(0, local_path)
        try:
            module_name, func_name = factory_spec.split(":", 1)
            mod = importlib.import_module(module_name)
            factory = getattr(mod, func_name)
            client = factory()
        except Exception as exc:
            print(f"❌ Failed to load factory {factory_spec}: {exc}")
            return 1

        # Iterate accounts and call client's update using our tokens
        successes = []
        failures = []
        base = ctx.settings
        accounts = base.accounts or []
        if not accounts:
            accounts = []
        for acct in accounts:
            try:
                token = get_valid_token(ctx, acct)
                if not token:
                    print(f"⚠️  No token for {acct.name}; skipping")
                    failures.append(acct.name)
                    continue
                # Try common method signatures
                called = False
                for meth, kwargs in [
                    ("update_portfolio", {"token": token, "account": acct.name}),
                    ("update_portfolio", {"token": token}),
                    ("update_with_token", {"token": token, "account": acct.name}),
                ]:
                    if hasattr(client, meth):
                        try:
                            getattr(client, meth)(**kwargs)
                            successes.append(acct.name)
                            called = True
                            break
                        except TypeError:
                            continue
                if not called:
                    print(f"⚠️  Client has no supported update method for {acct.name}; skipping")
                    failures.append(acct.name)
            except Exception as exc:
                print(f"❌ Local update failed for {acct.name}: {exc}")
                failures.append(acct.name)

        print(f"✅ Local update done. Success: {len(successes)}; Failures: {len(failures)}")
        if failures:
            print("Failed:", ", ".join(failures))
        return 0 if successes else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
