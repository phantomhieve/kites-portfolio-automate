"""
SummaryManager compatibility shim.
Delegates to unified src.kites_automate.sheets.summary.SummaryManager.
"""

from src.kites_automate.sheets.summary import SummaryManager, OverallSummary

__all__ = ["SummaryManager", "OverallSummary"]