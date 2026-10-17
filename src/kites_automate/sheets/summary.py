"""
Summary Sheet Manager

Consolidates portfolio summaries across all configured accounts into a unified,
executive Google Sheets overview tab with smart formatting state management.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import gspread
from gspread_formatting import CellFormat, Color, NumberFormat, TextFormat

from .client import SheetManager
from .portfolio import PortfolioSummary

logger = logging.getLogger(__name__)


@dataclass
class OverallSummary:
    """Overall summary aggregated across all accounts."""
    total_stocks_value: float = 0.0
    total_index_funds_value: float = 0.0
    total_other_funds_value: float = 0.0
    total_investment: float = 0.0
    total_pnl: float = 0.0

    @property
    def total_current_value(self) -> float:
        """Total current value of all portfolios."""
        return self.total_stocks_value + self.total_index_funds_value + self.total_other_funds_value

    @property
    def overall_return_percentage(self) -> float:
        """Overall return percentage."""
        if self.total_investment > 0:
            return (self.total_pnl / self.total_investment) * 100
        return 0.0


class SummaryManager:
    """Manages cross-account consolidated summary sheet creation and styling."""

    def __init__(
        self,
        sheet_manager: SheetManager,
        state_file: str = ".summary_formatting_state.json",
    ):
        self.sheet_manager = sheet_manager
        self.state_file = Path(state_file)
        self.formatting_state = self._load_formatting_state()

    def _load_formatting_state(self) -> Dict[str, bool]:
        """Load formatting state from local file."""
        try:
            if self.state_file.is_file():
                return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load summary formatting state: %s", exc)
        return {}

    def _save_formatting_state(self) -> None:
        """Save formatting state atomically."""
        try:
            tmp = self.state_file.with_suffix(".tmp")
            data = json.dumps(self.formatting_state, indent=2)
            tmp.write_text(data, encoding="utf-8")
            tmp.replace(self.state_file)
        except Exception as exc:
            logger.warning("Could not save summary formatting state: %s", exc)

    @staticmethod
    def _get_sheet_key(worksheet: gspread.Worksheet) -> str:
        return f"{worksheet.spreadsheet.id}_{worksheet.title}"

    def _is_formatted(self, worksheet: gspread.Worksheet) -> bool:
        return self.formatting_state.get(self._get_sheet_key(worksheet), False)

    def _mark_as_formatted(self, worksheet: gspread.Worksheet) -> None:
        key = self._get_sheet_key(worksheet)
        self.formatting_state[key] = True
        self._save_formatting_state()
        logger.debug("Marked %s as formatted in summary state cache", key)

    def create_summary_data(
        self,
        portfolio_summaries: Dict[str, PortfolioSummary],
    ) -> tuple[List[List[Any]], OverallSummary]:
        """Create summary table rows and overall aggregate totals."""
        overall = OverallSummary()

        header_title = ["🏆 Consolidated Portfolio Summary"]
        timestamp_row = [f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
        table_headers = [
            "Account",
            "Stocks Value",
            "Index Funds Value",
            "Other Funds Value",
            "Total Current Value",
            "Total Investment",
            "Total P&L",
            "Return %",
        ]

        rows: List[List[Any]] = [header_title, timestamp_row, [], table_headers]

        for name, summ in portfolio_summaries.items():
            ret_pct = f"{summ.return_percentage:.2f}%" if summ.total_investment > 0 else "0.00%"
            rows.append([
                name,
                round(summ.stocks_value, 2),
                round(summ.index_funds_value, 2),
                round(summ.other_funds_value, 2),
                round(summ.total_value, 2),
                round(summ.total_investment, 2),
                round(summ.total_pnl, 2),
                ret_pct,
            ])
            overall.total_stocks_value += summ.stocks_value
            overall.total_index_funds_value += summ.index_funds_value
            overall.total_other_funds_value += summ.other_funds_value
            overall.total_investment += summ.total_investment
            overall.total_pnl += summ.total_pnl

        # Total Aggregate Row
        overall_ret = f"{overall.overall_return_percentage:.2f}%" if overall.total_investment > 0 else "0.00%"
        rows.append([
            "TOTAL",
            round(overall.total_stocks_value, 2),
            round(overall.total_index_funds_value, 2),
            round(overall.total_other_funds_value, 2),
            round(overall.total_current_value, 2),
            round(overall.total_investment, 2),
            round(overall.total_pnl, 2),
            overall_ret,
        ])

        return rows, overall

    def update_summary_sheet(
        self,
        worksheet: gspread.Worksheet,
        portfolio_summaries: Dict[str, PortfolioSummary],
        force_formatting: bool = False,
    ) -> OverallSummary:
        """Update summary sheet with retry handling and optional formatting."""
        rows, overall = self.create_summary_data(portfolio_summaries)
        worksheet.clear()
        worksheet.update(values=rows, range_name="A1")

        is_formatted = self._is_formatted(worksheet)
        if force_formatting or not is_formatted:
            self._apply_formatting(worksheet, len(rows), len(portfolio_summaries))
            self._mark_as_formatted(worksheet)
            logger.info("Summary sheet updated and formatted with %d accounts", len(portfolio_summaries))
        else:
            logger.info("Summary sheet updated (minimal mode, %d accounts)", len(portfolio_summaries))

        return overall

    def update_data_only(
        self,
        worksheet: gspread.Worksheet,
        portfolio_summaries: Dict[str, PortfolioSummary],
    ) -> OverallSummary:
        """Update summary sheet data only without applying formatting calls."""
        return self.update_summary_sheet(worksheet, portfolio_summaries, force_formatting=False)

    def _apply_formatting(self, worksheet: gspread.Worksheet, total_rows: int, account_count: int) -> None:
        """Apply styling to summary worksheet."""
        try:
            # Column widths
            widths = {
                "A": 160,
                "B": 140,
                "C": 140,
                "D": 140,
                "E": 160,
                "F": 160,
                "G": 140,
                "H": 100,
            }
            self.sheet_manager.apply_column_widths(worksheet, widths)

            # Title format
            title_fmt = CellFormat(
                backgroundColor=Color(0.15, 0.3, 0.6),
                textFormat=TextFormat(bold=True, fontSize=12, foregroundColor=Color(1, 1, 1)),
            )
            self.sheet_manager.format_range(worksheet, "A1:H1", title_fmt)

            # Table header format
            tbl_hdr_fmt = CellFormat(
                backgroundColor=Color(0.85, 0.9, 0.98),
                textFormat=TextFormat(bold=True),
            )
            self.sheet_manager.format_range(worksheet, "A4:H4", tbl_hdr_fmt)

            # Currency formats for B5:G{total_rows}
            self.sheet_manager.format_range(worksheet, f"B5:G{total_rows}", self.sheet_manager.CURRENCY_FORMAT)

            # Total row format
            total_fmt = CellFormat(
                backgroundColor=Color(0.92, 0.95, 1.0),
                textFormat=TextFormat(bold=True),
            )
            self.sheet_manager.format_range(worksheet, f"A{total_rows}:H{total_rows}", total_fmt)
        except Exception as exc:
            logger.warning("Formatting error on summary worksheet: %s", exc)
