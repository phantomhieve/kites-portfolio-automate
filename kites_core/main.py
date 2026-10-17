"""
Kites Core — Facade and Compatibility Layer

Provides backward-compatible entry points (smart_update, minimal_update, etc.)
delegating directly to the unified src.kites_automate.sheets package.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Ensure src is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kites_automate.auth.kite_auth import KiteAuthManager  # type: ignore[attr-defined] # noqa
from src.kites_automate.profiles import (
    get_profile_by_name,
    get_spreadsheet_name,
    get_summary_sheet_name,
    load_profiles_config,
)
from src.kites_automate.sheets import (
    OverallSummary,
    PortfolioManager,
    PortfolioSummary,
    SheetManager,
    SummaryManager,
)


def get_profiles() -> List[Dict[str, Any]]:
    """Get validated profile configurations from profiles.json."""
    config = load_profiles_config()
    profiles: List[Dict[str, Any]] = []

    for profile_config in config.get("profiles", []):
        api_key = os.getenv(profile_config.get("api_key_env", ""))
        api_secret = os.getenv(profile_config.get("api_secret_env", ""))

        if not api_key or not api_secret:
            continue

        profiles.append({
            "api_key": api_key,
            "api_secret": api_secret,
            "token_file": profile_config.get("token_file", f"{profile_config['profile_name']}.json"),
            "profile_name": profile_config.get("profile_name", ""),
            "description": profile_config.get("description", ""),
            "exception_list": profile_config.get("exception_list", []),
        })

    if not profiles:
        raise ValueError("No valid profiles configured with active environment variables.")
    return profiles


def reset_formatting_state() -> None:
    """Reset local formatting state cache files."""
    for fname in [".portfolio_formatting_state.json", ".summary_formatting_state.json"]:
        p = Path(fname)
        if p.exists():
            try:
                p.unlink()
                print(f"🗑️  Removed {fname}")
            except OSError as exc:
                print(f"⚠️  Could not remove {fname}: {exc}")
    print("✅ Formatting state reset successfully.")


def show_status() -> None:
    """Display current formatting cache status."""
    print("📊 Portfolio Sheet Formatting Status")
    print("=" * 50)
    for fname in [".portfolio_formatting_state.json", ".summary_formatting_state.json"]:
        p = Path(fname)
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                print(f"📄 {fname}: {len(data)} cached sheets -> {list(data.keys())}")
            except Exception as exc:
                print(f"⚠️ {fname}: Error reading cache ({exc})")
        else:
            print(f"ℹ️ {fname}: No cache file present.")


def smart_update() -> None:
    """Smart update mode — updates data and formats only on first run."""
    load_dotenv()
    print("🧠 Smart Update Mode (Quota-Optimized)")
    print("=" * 50)

    sheet_manager = SheetManager()
    portfolio_manager = PortfolioManager(sheet_manager)
    summary_manager = SummaryManager(sheet_manager)

    spreadsheet_name = get_spreadsheet_name()
    sheet = sheet_manager.get_or_create_sheet(spreadsheet_name)
    portfolio_summaries: Dict[str, PortfolioSummary] = {}

    for profile in get_profiles():
        prof_name = profile["profile_name"]
        print(f"\n📊 Processing {prof_name}...")
        try:
            from kiteconnect import KiteConnect

            auth_mgr = KiteAuthManager(profile["api_key"], profile["api_secret"], profile["token_file"])
            kite = auth_mgr.get_client()

            worksheet = sheet_manager.get_or_create_worksheet(sheet, prof_name)
            summary = portfolio_manager.update_portfolio_sheet(
                worksheet=worksheet,
                holdings=kite.holdings(),
                mf_holdings=kite.mf_holdings(),
                force_formatting=False,
                exception_list=profile.get("exception_list"),
            )
            portfolio_summaries[prof_name] = summary
            print(f"✅ Updated {prof_name} (Value: ₹{summary.total_value:,.2f})")
        except Exception as exc:
            print(f"❌ Error updating {prof_name}: {exc}")
        time.sleep(3)

    if portfolio_summaries:
        print("\n📊 Updating summary tab...")
        summary_ws = sheet_manager.get_or_create_worksheet(sheet, get_summary_sheet_name())
        overall = summary_manager.update_summary_sheet(summary_ws, portfolio_summaries, force_formatting=False)
        print(f"✅ Summary complete! Total Portfolio Value: ₹{overall.total_current_value:,.2f}")


def minimal_update() -> None:
    """Minimal update mode — updates values only, preserving formatting."""
    load_dotenv()
    print("⚡ Minimal Update Mode (Data Only)")
    print("=" * 50)

    sheet_manager = SheetManager()
    portfolio_manager = PortfolioManager(sheet_manager)
    summary_manager = SummaryManager(sheet_manager)

    spreadsheet_name = get_spreadsheet_name()
    sheet = sheet_manager.get_or_create_sheet(spreadsheet_name)
    portfolio_summaries: Dict[str, PortfolioSummary] = {}

    for profile in get_profiles():
        prof_name = profile["profile_name"]
        print(f"\n📊 Updating data for {prof_name}...")
        try:
            auth_mgr = KiteAuthManager(profile["api_key"], profile["api_secret"], profile["token_file"])
            kite = auth_mgr.get_client()

            worksheet = sheet_manager.get_or_create_worksheet(sheet, prof_name)
            summary = portfolio_manager.update_data_only(
                worksheet=worksheet,
                holdings=kite.holdings(),
                mf_holdings=kite.mf_holdings(),
                exception_list=profile.get("exception_list"),
            )
            portfolio_summaries[prof_name] = summary
            print(f"✅ Updated {prof_name}")
        except Exception as exc:
            print(f"❌ Error updating {prof_name}: {exc}")
        time.sleep(2)

    if portfolio_summaries:
        summary_ws = sheet_manager.get_or_create_worksheet(sheet, get_summary_sheet_name())
        overall = summary_manager.update_data_only(summary_ws, portfolio_summaries)
        print(f"✅ Summary data updated! Total Value: ₹{overall.total_current_value:,.2f}")


def force_format() -> None:
    """Force format mode — reapplies all styling to all sheets."""
    load_dotenv()
    print("🎨 Force Format Mode")
    print("=" * 50)

    sheet_manager = SheetManager()
    portfolio_manager = PortfolioManager(sheet_manager)
    summary_manager = SummaryManager(sheet_manager)

    spreadsheet_name = get_spreadsheet_name()
    sheet = sheet_manager.get_or_create_sheet(spreadsheet_name)
    portfolio_summaries: Dict[str, PortfolioSummary] = {}

    for profile in get_profiles():
        prof_name = profile["profile_name"]
        print(f"\n🎨 Formatting and updating {prof_name}...")
        try:
            auth_mgr = KiteAuthManager(profile["api_key"], profile["api_secret"], profile["token_file"])
            kite = auth_mgr.get_client()

            worksheet = sheet_manager.get_or_create_worksheet(sheet, prof_name)
            summary = portfolio_manager.update_portfolio_sheet(
                worksheet=worksheet,
                holdings=kite.holdings(),
                mf_holdings=kite.mf_holdings(),
                force_formatting=True,
                exception_list=profile.get("exception_list"),
            )
            portfolio_summaries[prof_name] = summary
            print(f"✅ Formatted {prof_name}")
        except Exception as exc:
            print(f"❌ Error formatting {prof_name}: {exc}")
        time.sleep(5)

    if portfolio_summaries:
        summary_ws = sheet_manager.get_or_create_worksheet(sheet, get_summary_sheet_name())
        overall = summary_manager.update_summary_sheet(summary_ws, portfolio_summaries, force_formatting=True)
        print(f"✅ Formatted Summary! Total: ₹{overall.total_current_value:,.2f}")


if __name__ == "__main__":
    load_dotenv()
    print("1. Smart Update")
    print("2. Minimal Update")
    print("3. Force Format")
    print("4. Show Status")
    print("5. Reset Formatting State")
    choice = input("Enter choice [1-5]: ").strip()
    if choice == "1":
        smart_update()
    elif choice == "2":
        minimal_update()
    elif choice == "3":
        force_format()
    elif choice == "4":
        show_status()
    elif choice == "5":
        reset_formatting_state()
    else:
        print("Invalid choice.")