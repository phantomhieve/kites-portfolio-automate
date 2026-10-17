"""
Unified Kites Adapter

Bridges Zerodha KiteConnect API client and Google Sheets manager.
Fetches equity holdings and mutual funds, processes calculations,
and applies smart cached formatting to Google Sheets.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

from kiteconnect import KiteConnect

from .config import AccountConfig, RuntimeContext
from .profiles import get_profile_by_name, get_spreadsheet_name, get_summary_sheet_name, load_profiles_config
from .sheets import PortfolioManager, SheetManager
from .utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class BaseKitesAdapter:
    """Base interface for Kites adapters."""

    def authenticate(self, ctx: RuntimeContext) -> Tuple[Optional[str], Optional[int]]:
        raise NotImplementedError

    def update_portfolio(
        self,
        ctx: RuntimeContext,
        token: str,
        account: Optional[AccountConfig] = None,
    ) -> Optional[dict]:
        raise NotImplementedError


class UnifiedKitesAdapter(BaseKitesAdapter):
    """Direct, strongly-typed adapter combining KiteConnect API with Google Sheets."""

    def __init__(self, sheet_manager: Optional[SheetManager] = None):
        self._sheet_manager = sheet_manager

    def _get_sheet_manager(self) -> SheetManager:
        if self._sheet_manager is None:
            self._sheet_manager = SheetManager()
        return self._sheet_manager

    def authenticate(self, ctx: RuntimeContext) -> Tuple[Optional[str], Optional[int]]:
        """Lightweight check of configured API credentials."""
        api_key = ctx.settings.kites.api_key
        if api_key:
            return api_key, 8 * 3600
        return None, None

    def update_portfolio(
        self,
        ctx: RuntimeContext,
        token: str,
        account: Optional[AccountConfig] = None,
    ) -> Optional[dict]:
        """Fetch holdings for the account and update the corresponding Google Sheet tab."""
        account_name = account.name if account else "default"
        logger.info("Updating portfolio for account '%s'...", account_name)

        profiles_cfg = load_profiles_config()
        matched_profile = get_profile_by_name(account_name, profiles_cfg)

        if not matched_profile:
            logger.error("No profile configuration found in profiles.json for '%s'", account_name)
            raise RuntimeError(f"No profile found for account: {account_name}")

        # Resolve credentials (from ~/.kites vault or .env)
        from .profiles import resolve_api_credentials
        api_key, api_secret = resolve_api_credentials(account_name, matched_profile)

        if not api_key or not api_secret:
            logger.error(
                "Missing API credentials for '%s'. Configure in ~/.kites/credentials.json or .env",
                account_name,
            )
            raise RuntimeError(f"Missing API credentials for {account_name}")

        logger.info("Using API key for %s (len=%d)", account_name, len(api_key))
        if not token:
            raise RuntimeError(f"No valid access token available for {account_name}")

        logger.info("Using access token for %s (len=%d)", account_name, len(token))

        # Initialize KiteConnect client
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(token)

        # Validate token with lightweight profile call
        try:
            _ = kite.profile()
            logger.info("Token validation successful for %s", account_name)
        except Exception as exc:
            logger.error("Token validation failed for %s: %s", account_name, exc)
            raise RuntimeError(f"Token validation failed for {account_name}: {exc}") from exc

        # Open Google Sheets
        sheet_manager = self._get_sheet_manager()
        spreadsheet_name = get_spreadsheet_name(profiles_cfg)
        summary_sheet_name = get_summary_sheet_name(profiles_cfg)

        spreadsheet = sheet_manager.get_or_create_sheet(spreadsheet_name)
        profile_tab_name = matched_profile.get("profile_name", account_name)
        worksheet = sheet_manager.get_or_create_worksheet(spreadsheet, profile_tab_name)

        # Process holdings and update worksheet
        portfolio_manager = PortfolioManager(sheet_manager)
        exceptions = matched_profile.get("exception_list", [])

        # Smart update: only formats if sheet hasn't been styled yet
        summary = portfolio_manager.update_sheet_smart(
            worksheet=worksheet,
            kite_client=kite,
            exception_list=exceptions,
        )

        logger.info(
            "Portfolio updated for '%s': Current Value=%.2f, Investment=%.2f, P&L=%.2f (%.2f%%)",
            profile_tab_name,
            summary.total_value,
            summary.total_investment,
            summary.total_pnl,
            summary.return_percentage,
        )

        return {
            "profile_name": profile_tab_name,
            "summary": summary,
            "sheet_manager": sheet_manager,
            "spreadsheet": spreadsheet,
            "summary_sheet_name": summary_sheet_name,
        }


# Backwards compatibility alias
LocalKitesAdapter = UnifiedKitesAdapter


def get_adapter(ctx: RuntimeContext) -> BaseKitesAdapter:
    """Factory returning the unified Kites adapter."""
    return UnifiedKitesAdapter()
