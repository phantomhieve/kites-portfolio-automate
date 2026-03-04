"""
Helper functions for the Kites package.
"""

from typing import Dict, Any, Union


def safe_float(data: Dict[str, Any], key: str) -> float:
    """
    Safely extract a float value from a dictionary.

    Args:
        data: Dictionary to extract from
        key: Key to extract

    Returns:
        float: The extracted value or 0.0 if not found/invalid
    """
    try:
        value = data.get(key, 0)
        return float(value if value is not None else 0)
    except (ValueError, TypeError):
        return 0.0 