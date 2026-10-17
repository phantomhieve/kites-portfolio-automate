"""
SheetManager compatibility shim.
Delegates to unified src.kites_automate.sheets.client.SheetManager.
"""

from src.kites_automate.sheets.client import SheetManager

__all__ = ["SheetManager"]