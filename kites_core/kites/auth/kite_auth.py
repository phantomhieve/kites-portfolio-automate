"""
KiteAuthManager compatibility shim.
Delegates to unified src.kites_automate.auth.kite_auth.KiteAuthManager.
"""

from src.kites_automate.auth.kite_auth import KiteAuthManager

__all__ = ["KiteAuthManager"]