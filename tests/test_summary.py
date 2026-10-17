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

    # Verify table rows and 3 distinct sections
    first_cols = [r[0] for r in rows if r and isinstance(r[0], str)]
    assert "📊 Portfolio Summary Dashboard" in first_cols
    assert "📈 Investment Breakdown" in first_cols
    assert "📊 Portfolio Performance" in first_cols
    assert "📈 Individual Portfolio Summary" in first_cols
    assert "Account1" in first_cols
    assert "Account2" in first_cols
    assert "TOTAL" in first_cols

    # Verify Investment Breakdown percentages
    breakdown_rows = {r[0]: (r[1], r[2]) for r in rows if len(r) == 3 and r[0] in ("Stocks", "Index Funds", "Other Funds")}
    assert "Stocks" in breakdown_rows
    assert breakdown_rows["Stocks"][0] == 300000.0
    assert "57.1%" in breakdown_rows["Stocks"][1]

    # Verify Portfolio Performance metrics
    perf_metrics = {r[0]: r[1] for r in rows if len(r) == 2 and r[0] in ("Total Current Value", "Total Investment", "Total P&L", "Overall Return %")}
    assert perf_metrics["Total Current Value"] == 525000.0
    assert perf_metrics["Total Investment"] == 410000.0
    assert perf_metrics["Total P&L"] == 115000.0
    assert perf_metrics["Overall Return %"] == "28.05%"


def test_summary_manager_update_sheet():
    mock_sm = MagicMock()
    mgr = SummaryManager(mock_sm, state_file="/tmp/test_summary_state_update.json")

    mock_ws = MagicMock()
    mock_ws.spreadsheet.id = "test_ss_id"
    mock_ws.title = "Summary"

    portfolio_summaries = {
        "HUF": PortfolioSummary(stocks_value=100.0, stocks_investment=80.0),
    }

    overall = mgr.update_summary_sheet(mock_ws, portfolio_summaries, force_formatting=True)
    assert overall.total_stocks_value == 100.0
    assert mock_ws.clear.called
    assert mock_ws.update.called
