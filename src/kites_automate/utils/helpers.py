"""
General helper functions for data formatting and extraction.
"""

from __future__ import annotations

from typing import Any, Dict


def safe_float(data: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """Safely extract a float value from a dictionary."""
    if not isinstance(data, dict):
        return default
    try:
        val = data.get(key, default)
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def format_currency_inr(amount: float) -> str:
    """Format a float as an Indian Rupee string (e.g., ₹1,23,456.78)."""
    try:
        is_neg = amount < 0
        amount = abs(amount)
        parts = f"{amount:.2f}".split(".")
        whole, dec = parts[0], parts[1]
        if len(whole) > 3:
            last_three = whole[-3:]
            remaining = whole[:-3]
            grouped = []
            while remaining:
                grouped.insert(0, remaining[-2:])
                remaining = remaining[:-2]
            whole = ",".join(grouped) + "," + last_three
        sign = "-" if is_neg else ""
        return f"{sign}₹{whole}.{dec}"
    except Exception:
        return f"₹{amount:.2f}"
