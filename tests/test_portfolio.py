"""Tests for portfolio processing and aggregation logic."""

from unittest.mock import MagicMock
from src.kites_automate.sheets.portfolio import PortfolioManager, PortfolioSummary


def test_portfolio_summary_calculations():
    summary = PortfolioSummary(
        stocks_value=100000.0,
        index_funds_value=50000.0,
        other_funds_value=25000.0,
        stocks_investment=80000.0,
        index_funds_investment=40000.0,
        other_funds_investment=20000.0,
    )
    assert summary.total_value == 175000.0
    assert summary.total_investment == 140000.0
    assert summary.total_pnl == 35000.0
    assert round(summary.return_percentage, 2) == 25.0


def test_process_holdings():
    mock_sm = MagicMock()
    pm = PortfolioManager(mock_sm, state_file="/tmp/test_portfolio_state.json")

    sample_holdings = [
        # Large holding > 5000
        {
            "tradingsymbol": "INFY",
            "opening_quantity": 100,
            "quantity": 100,
            "average_price": 1400.0,
            "last_price": 1600.0,
        },
        # Small holding < 5000 (should group in Others)
        {
            "tradingsymbol": "PENNY",
            "opening_quantity": 10,
            "quantity": 10,
            "average_price": 100.0,
            "last_price": 120.0,
        },
        # Excluded holding
        {
            "tradingsymbol": "EXCLUDE_ME",
            "opening_quantity": 50,
            "quantity": 50,
            "average_price": 200.0,
            "last_price": 250.0,
        },
    ]

    rows, summary = pm.process_holdings(sample_holdings, exception_list=["EXCLUDE_ME"])

    symbols = [r[0] for r in rows if r and isinstance(r[0], str)]
    assert "INFY" in symbols
    assert "Others" in symbols
    assert "EXCLUDE_ME" not in symbols
    assert summary.stocks_value == (100 * 1600.0) + (10 * 120.0)
    assert summary.stocks_investment == (100 * 1400.0) + (10 * 100.0)


def test_process_mutual_funds():
    mock_sm = MagicMock()
    pm = PortfolioManager(mock_sm, state_file="/tmp/test_portfolio_state.json")
    summary = PortfolioSummary()

    sample_mf = [
        # Index fund
        {
            "fund": "UTI Nifty 50 Index Fund",
            "quantity": 1000.0,
            "average_price": 120.0,
            "last_price": 150.0,
        },
        # Active fund
        {
            "fund": "Parag Parikh Flexi Cap Fund",
            "units": 500.0,
            "average_price": 50.0,
            "last_price": 75.0,
        },
    ]

    rows = pm.process_mutual_funds(sample_mf, summary)
    assert summary.index_funds_value == 150000.0
    assert summary.other_funds_value == 37500.0
    assert len(rows) > 0
