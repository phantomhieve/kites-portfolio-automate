"""
Profiles & Unified Vault Configuration Manager

Provides single-source-of-truth account resolution supporting both:
1. Unified Vault in ~/.kites/credentials.json (co-locating credentials + API keys)
2. Decoupled setup via profiles.json + .env
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def find_profiles_file(explicit_path: Optional[str] = None) -> Optional[Path]:
    """Find the profiles.json file in standard locations."""
    if explicit_path:
        p = Path(explicit_path)
        if p.is_file():
            return p

    candidates = [
        Path("profiles.json"),
        Path.home() / ".kites" / "profiles.json",
        Path(__file__).resolve().parent.parent.parent / "profiles.json",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand.resolve()
    return None


def load_raw_credentials_vault(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load ~/.kites/credentials.json if present."""
    p = Path(config_path) if config_path else (Path.home() / ".kites" / "credentials.json")
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.warning("Could not read credentials vault at %s: %s", p, exc)
    return {}


def load_profiles_config(explicit_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load unified profile configuration. Merges profiles.json and ~/.kites/credentials.json.
    """
    profiles_data: Dict[str, Any] = {"profiles": [], "settings": {}}

    p = find_profiles_file(explicit_path)
    if p:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                profiles_data = data
        except Exception as exc:
            logger.error("Failed to parse profiles configuration at %s: %s", p, exc)

    # Defaults for settings
    settings = profiles_data.setdefault("settings", {})
    settings.setdefault("spreadsheet_name", os.getenv("SPREADSHEET_NAME", "Portfolio"))
    settings.setdefault("summary_sheet_name", os.getenv("SUMMARY_SHEET_NAME", "Summary"))
    settings.setdefault("default_update_mode", "smart")

    existing_names = {
        str(prof.get("profile_name", "")).strip().lower()
        for prof in profiles_data.get("profiles", [])
    }

    # Discover accounts defined in ~/.kites/credentials.json
    vault = load_raw_credentials_vault()
    vault_accounts = vault.get("accounts", vault)  # Supports both {"accounts": {...}} and flat {...}

    if isinstance(vault_accounts, dict):
        for acct_id, acct_data in vault_accounts.items():
            if acct_id == "settings" or not isinstance(acct_data, dict):
                continue
            acct_lower = acct_id.lower()
            if acct_lower not in existing_names:
                display_name = acct_data.get("display_name", acct_id.capitalize())
                profiles_data["profiles"].append({
                    "profile_name": display_name,
                    "api_key_env": f"{acct_lower}_api_key",
                    "api_secret_env": f"{acct_lower}_api_secret",
                    "token_file": f"{display_name}_access_token.txt",
                    "description": f"{display_name} portfolio",
                    "exception_list": acct_data.get("exception_list", []),
                })
                existing_names.add(acct_lower)

    return profiles_data


def get_spreadsheet_name(config: Optional[Dict[str, Any]] = None) -> str:
    """Get target Google Spreadsheet name from settings."""
    cfg = config or load_profiles_config()
    return cfg.get("settings", {}).get("spreadsheet_name", os.getenv("SPREADSHEET_NAME", "Portfolio"))


def get_summary_sheet_name(config: Optional[Dict[str, Any]] = None) -> str:
    """Get summary sheet name from settings."""
    cfg = config or load_profiles_config()
    return cfg.get("settings", {}).get("summary_sheet_name", os.getenv("SUMMARY_SHEET_NAME", "Summary"))


def get_profile_by_name(name: str, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Find profile config by account/profile name case-insensitively."""
    cfg = config or load_profiles_config()
    target = name.strip().lower()
    for prof in cfg.get("profiles", []):
        if str(prof.get("profile_name", "")).strip().lower() == target:
            return prof
    return None


def resolve_api_credentials(account_name: str, profile: Optional[Dict[str, Any]] = None) -> tuple[Optional[str], Optional[str]]:
    """
    Resolve api_key and api_secret for an account in precedence order:
    1. Direct in ~/.kites/credentials.json account definition
    2. Environment variable named in profile['api_key_env']
    3. Environment variable <account>_api_key or <ACCOUNT>_API_KEY
    """
    prof = profile or get_profile_by_name(account_name) or {}
    acct_lower = account_name.strip().lower()

    # 1. Check ~/.kites/credentials.json vault
    vault = load_raw_credentials_vault()
    vault_accounts = vault.get("accounts", vault)
    if isinstance(vault_accounts, dict):
        acct_vault = vault_accounts.get(acct_lower, {})
        if isinstance(acct_vault, dict):
            key = acct_vault.get("api_key")
            secret = acct_vault.get("api_secret")
            if key and secret:
                return str(key).strip(), str(secret).strip()

    # 2. Check environment variable from profile['api_key_env']
    key_env = prof.get("api_key_env")
    secret_env = prof.get("api_secret_env")
    if key_env and secret_env:
        key = os.getenv(key_env)
        secret = os.getenv(secret_env)
        if key and secret:
            return key.strip(), secret.strip()

    # 3. Fallback to standard convention
    for key_candidate in (f"{acct_lower}_api_key", f"{account_name.upper()}_API_KEY"):
        val = os.getenv(key_candidate)
        if val:
            for sec_candidate in (f"{acct_lower}_api_secret", f"{account_name.upper()}_API_SECRET"):
                sval = os.getenv(sec_candidate)
                if sval:
                    return val.strip(), sval.strip()

    return None, None
