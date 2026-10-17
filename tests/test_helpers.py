"""Tests for data helper functions."""

from src.kites_automate.utils.helpers import safe_float, format_currency_inr


def test_safe_float():
    assert safe_float({"val": "123.45"}, "val") == 123.45
    assert safe_float({"val": 50}, "val") == 50.0
    assert safe_float({"val": None}, "val", default=10.0) == 10.0
    assert safe_float({"val": "invalid"}, "val", default=0.0) == 0.0
    assert safe_float({}, "missing", default=99.0) == 99.0


def test_format_currency_inr():
    assert format_currency_inr(100.5) == "₹100.50"
    assert format_currency_inr(1000) == "₹1,000.00"
    assert format_currency_inr(100000) == "₹1,00,000.00"
    assert format_currency_inr(12345678.9) == "₹1,23,45,678.90"
    assert format_currency_inr(-5000) == "-₹5,000.00"
