import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from ..config import RuntimeContext, AppSettings, AccountConfig
from ..kites_adapter import get_adapter
from ..legacy_adapter import run_legacy
from ..notify.emailer import send_failure_email

logger = logging.getLogger(__name__)


@dataclass
class Token:
    access_token: str
    expires_at: float  # epoch seconds

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - 60  # 1 minute early


def _token_path(account_name: Optional[str] = None) -> str:
    base = os.path.expanduser("~/.kites")
    if account_name:
        base = os.path.join(base, account_name)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "token.json")


def _read_token_from_disk(path: str) -> Optional[Token]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return Token(access_token=data["access_token"], expires_at=float(data["expires_at"]))
    except FileNotFoundError:
        return None
def _read_automated_token(profile_name: Optional[str] = None) -> Optional[Token]:
    """Read token saved by fully automated auth (~/.kites/<profile>_access_token.txt)."""
    try:
        base_dir = os.path.expanduser("~/.kites")
        candidate_names = []
        if profile_name:
            # Try exact and lowercase variants
            candidate_names.extend([
                f"{profile_name}_access_token.txt",
                f"{profile_name.lower()}_access_token.txt",
            ])
        else:
            # Fallback single-profile filename pattern (rare)
            candidate_names.append("access_token.txt")

        for fname in candidate_names:
            fpath = os.path.join(base_dir, fname)
            if not os.path.exists(fpath):
                continue
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                access = data.get("access_token")
                expires_at_iso = data.get("expires_at")
                if not access or not expires_at_iso:
                    continue
                # Convert ISO8601 to epoch seconds
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00"))
                    exp = dt.timestamp()
                except Exception:
                    # Default to 8 hours from now if parse fails
                    import time as _t
                    exp = _t.time() + 8 * 3600
                tok = Token(access_token=access, expires_at=exp)
                if not tok.is_expired:
                    return tok
            except Exception:
                continue
    except Exception:
        pass
    return None


def _write_token_to_disk(path: str, token: Token) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"access_token": token.access_token, "expires_at": token.expires_at}, f)
    os.replace(tmp, path)


def get_valid_token(ctx: RuntimeContext, account: Optional[AccountConfig] = None) -> Optional[str]:
    name = account.name if account else None
    path = _token_path(name)
    token = _read_token_from_disk(path)
    if token and not token.is_expired:
        return token.access_token

    # Try reading tokens produced by fully automated auth
    automated = _read_automated_token(name)
    if automated and not automated.is_expired:
        return automated.access_token

    new_token = rotate_token(ctx, account)
    if new_token:
        return new_token
    return None


def rotate_token(ctx: RuntimeContext, account: Optional[AccountConfig] = None) -> Optional[str]:
    adapter = get_adapter(ctx)
    try:
        access_token, expires_in = adapter.authenticate(ctx)
    except Exception as exc:
        details = f"Account: {account.name if account else 'default'}\nError: {exc}"
        logger.exception("Token rotation crashed for %s", account.name if account else "default")
        send_failure_email(ctx, subject="Kites token rotation failed", details=details)
        return None

    if not access_token:
        msg = f"Token rotation failed: no access token for {account.name if account else 'default'}"
        logger.error(msg)
        send_failure_email(ctx, subject="Kites token rotation failed", details=msg)
        return None

    expiry = time.time() + (int(expires_in) if expires_in else 8 * 3600)
    path = _token_path(account.name if account else None)
    _write_token_to_disk(path, Token(access_token=access_token, expires_at=expiry))
    logger.info("Rotated token for %s; expires in %s seconds", account.name if account else "default", int(expires_in) if expires_in else 8 * 3600)
    return access_token


def rotate_all_tokens(ctx: RuntimeContext, token_only: bool = False) -> None:
    # Legacy path: run legacy project to ensure tokens exist
    if ctx.settings.legacy and ctx.settings.legacy.enabled:
        if token_only:
            logger.info("Token-only rotation: checking token validity without portfolio updates")
            # For token-only mode, we just validate existing tokens without running legacy updates
            # This prevents unnecessary portfolio updates during token rotation
            try:
                from ..legacy_adapter import _validate_legacy_tokens
                _validate_legacy_tokens(ctx)
            except Exception as exc:
                details = f"Legacy token validation failed\nError: {exc}"
                logger.exception("Legacy token validation failed")
                send_failure_email(ctx, subject="Kites token validation failed", details=details)
        else:
            logger.info("Rotating tokens via legacy project")
            try:
                run_legacy(ctx)
            except Exception as exc:
                details = f"Legacy token rotation failed\nError: {exc}"
                logger.exception("Legacy token rotation failed")
                send_failure_email(ctx, subject="Kites token rotation failed", details=details)
        return

    base = ctx.settings
    if base.accounts:
        for acct in base.accounts:
            eff = AppSettings.build_settings_for_account(base, acct)
            local_ctx = RuntimeContext(settings=eff)
            rotate_token(local_ctx, acct)
    else:
        rotate_token(ctx, None)
