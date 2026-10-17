"""
PortfolioManager compatibility shim.
Delegates to unified src.kites_automate.sheets.portfolio.PortfolioManager.
"""

from src.kites_automate.sheets.portfolio import PortfolioManager, PortfolioSummary

__all__ = ["PortfolioManager", "PortfolioSummary"]