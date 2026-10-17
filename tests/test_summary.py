"""Tests for summary sheet manager and consolidation logic."""

from unittest.mock import MagicMock
from src.kites_automate.sheets.portfolio import PortfolioSummary
from src.kites_automate.sheets.summary import SummaryManager, OverallSummary


def test_create_summary_data():
    mock_sm = MagicMock()
    mgr = SummaryManager(mock_sm, state_file="/tmp/test_summary_state.json")

    portfolio_summaries = {
        "Account1": PortfolioSummary(
            stocks_value=100000.0,
            index_funds_value=50000.0,
            other_funds_value=25000.0,
            stocks_investment=80000.0,
            index_funds_investment=40000.0,
            other_funds_investment=20000.0,
        ),
        "Account2": PortfolioSummary(
            stocks_value=200000.0,
            index_funds_value=100000.0,
            other_funds_value=50000.0,
            stocks_investment=150000.0,
            index_funds_investment=80000.0,
            other_funds_investment=40000.0,
        ),
    }

    rows, overall = mgr.create_summary_data(portfolio_summaries)

    assert isinstance(overall, OverallSummary)
    assert overall.total_stocks_value == 300000.0
    assert overall.total_index_funds_value == 150000.0
    assert overall.total_other_funds_value == 75000.0
    assert overall.total_current_value == 525000.0
    assert overall.total_investment == 410000.0
    assert overall.total_pnl == 115000.0

    # Verify table rows
    accounts = [r[0] for r in rows if r and isinstance(r[0], str)]
    assert "Account1" in accounts
    assert "Account2" in accounts
    assert "TOTAL" in accounts
