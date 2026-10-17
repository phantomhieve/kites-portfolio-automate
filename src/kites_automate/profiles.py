"""
Profiles configuration manager.

Resolves and validates profiles.json for multi-account Zerodha portfolios.
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
        Path("kites_core/profiles.json"),
        Path(__file__).resolve().parent.parent.parent / "profiles.json",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand.resolve()
    return None


def load_profiles_config(explicit_path: Optional[str] = None) -> Dict[str, Any]:
    """Load profiles configuration dictionary from JSON."""
    p = find_profiles_file(explicit_path)
    if not p:
        logger.warning("profiles.json not found in standard paths.")
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as exc:
        logger.error("Failed to parse profiles configuration at %s: %s", p, exc)
        return {}


def get_spreadsheet_name(config: Optional[Dict[str, Any]] = None) -> str:
    """Get target Google Spreadsheet name from settings."""
    cfg = config or load_profiles_config()
    return cfg.get("settings", {}).get("spreadsheet_name", "Portfolio")


def get_summary_sheet_name(config: Optional[Dict[str, Any]] = None) -> str:
    """Get summary sheet name from settings."""
    cfg = config or load_profiles_config()
    return cfg.get("settings", {}).get("summary_sheet_name", "Summary")


def get_profile_by_name(name: str, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Find profile config by account/profile name case-insensitively."""
    cfg = config or load_profiles_config()
    target = name.strip().lower()
    for prof in cfg.get("profiles", []):
        if str(prof.get("profile_name", "")).strip().lower() == target:
            return prof
    return None
