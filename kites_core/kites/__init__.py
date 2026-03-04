"""
Kites - A Portfolio Tracking System for Zerodha Kite

This package provides tools to track and analyze investment portfolios
across multiple Zerodha Kite accounts, with automated Google Sheets integration.
"""

__version__ = "1.0.0"

from .auth.kite_auth import KiteAuthManager
from .sheets.portfolio import PortfolioManager
from .sheets.sheet_manager import SheetManager

__all__ = ['KiteAuthManager', 'PortfolioManager', 'SheetManager'] 