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
from typing import Any, Dict, List, Optional, Tuple

import gspread
from gspread_formatting import CellFormat, Color, NumberFormat, TextFormat, batch_updater

from .client import SheetManager
from .portfolio import PortfolioSummary

logger = logging.getLogger(__name__)


# Theme Formats (Light Gray #E6E6E6 palette matching original dashboard template)
HEADER_FMT = CellFormat(
    backgroundColor=Color(0.9, 0.9, 0.9),  # #E6E6E6
    textFormat=TextFormat(bold=True, fontSize=11),
    horizontalAlignment="LEFT",
)
SUBHEADER_FMT = CellFormat(
    backgroundColor=Color(0.95, 0.95, 0.95),  # #F2F2F2
    textFormat=TextFormat(bold=True, fontSize=10),
    horizontalAlignment="LEFT",
)
CURRENCY_FMT = CellFormat(
    numberFormat=NumberFormat(type="CURRENCY", pattern="₹#,##0.00"),
    horizontalAlignment="RIGHT",
)
PERCENT_FMT = CellFormat(
    textFormat=TextFormat(bold=True),
    horizontalAlignment="RIGHT",
)
GREEN_PNL_FMT = CellFormat(
    numberFormat=NumberFormat(type="CURRENCY", pattern="₹#,##0.00"),
    textFormat=TextFormat(bold=True, foregroundColor=Color(0.0, 0.55, 0.0)),
    horizontalAlignment="RIGHT",
)
RED_PNL_FMT = CellFormat(
    numberFormat=NumberFormat(type="CURRENCY", pattern="-₹#,##0.00"),
    textFormat=TextFormat(bold=True, foregroundColor=Color(0.75, 0.0, 0.0)),
    horizontalAlignment="RIGHT",
)
GREEN_TEXT_FMT = CellFormat(
    textFormat=TextFormat(bold=True, foregroundColor=Color(0.0, 0.55, 0.0)),
    horizontalAlignment="RIGHT",
)
RED_TEXT_FMT = CellFormat(
    textFormat=TextFormat(bold=True, foregroundColor=Color(0.75, 0.0, 0.0)),
    horizontalAlignment="RIGHT",
)


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
    ) -> Tuple[List[List[Any]], OverallSummary]:
        """Create summary table rows across all 3 dashboard sections and calculate aggregate totals."""
        overall = OverallSummary()
        for summary in portfolio_summaries.values():
            overall.total_stocks_value += summary.stocks_value
            overall.total_index_funds_value += summary.index_funds_value
            overall.total_other_funds_value += summary.other_funds_value
            overall.total_investment += summary.total_investment
            overall.total_pnl += summary.total_pnl

        def _calc_pct(val: float, tot: float) -> str:
            return f"{(val / tot) * 100:.1f}%" if tot > 0 else "0.0%"

        # Section 1: Header + Timestamp + Investment Breakdown
        # Section 2: Portfolio Performance
        # Section 3: Individual Portfolio Summary
        rows: List[List[Any]] = [
            ["📊 Portfolio Summary Dashboard"],
            ["Last Updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [],
            ["📈 Investment Breakdown"],
            ["Category", "Current Value", "Percentage"],
            ["Stocks", round(overall.total_stocks_value, 2), _calc_pct(overall.total_stocks_value, overall.total_current_value)],
            ["Index Funds", round(overall.total_index_funds_value, 2), _calc_pct(overall.total_index_funds_value, overall.total_current_value)],
            ["Other Funds", round(overall.total_other_funds_value, 2), _calc_pct(overall.total_other_funds_value, overall.total_current_value)],
            [],
            ["📊 Portfolio Performance"],
            ["Metric", "Value"],
            ["Total Current Value", round(overall.total_current_value, 2)],
            ["Total Investment", round(overall.total_investment, 2)],
            ["Total P&L", round(overall.total_pnl, 2)],
            ["Overall Return %", f"{overall.overall_return_percentage:.2f}%"],
            [],
            ["📈 Individual Portfolio Summary"],
            [
                "Portfolio",
                "Stocks",
                "Index Funds",
                "Other Funds",
                "Total Value",
                "Total Investment",
                "Total P&L",
                "Return %",
            ],
        ]

        # Individual account breakdown rows
        for portfolio_name, summary in portfolio_summaries.items():
            ret_pct = f"{summary.return_percentage:.2f}%" if summary.total_investment > 0 else "0.00%"
            rows.append([
                portfolio_name,
                round(summary.stocks_value, 2),
                round(summary.index_funds_value, 2),
                round(summary.other_funds_value, 2),
                round(summary.total_value, 2),
                round(summary.total_investment, 2),
                round(summary.total_pnl, 2),
                ret_pct,
            ])

        # TOTAL aggregate row
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
        """Update summary sheet with retry handling and batched formatting."""
        rows, overall = self.create_summary_data(portfolio_summaries)
        worksheet.clear()
        worksheet.update(values=rows, range_name="A1")

        is_formatted = self._is_formatted(worksheet)
        if force_formatting or not is_formatted:
            self._apply_formatting(worksheet, rows, portfolio_summaries, overall)
            self._mark_as_formatted(worksheet)
            logger.info("Summary sheet updated and formatted with %d accounts (force=%s)", len(portfolio_summaries), force_formatting)
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

    def _apply_formatting(
        self,
        worksheet: gspread.Worksheet,
        rows: List[List[Any]],
        portfolio_summaries: Dict[str, PortfolioSummary],
        overall: OverallSummary,
    ) -> None:
        """Apply styling to summary worksheet in a single atomic batch_updater call."""
        try:
            with batch_updater(worksheet.spreadsheet) as batch:
                # 1. Column widths
                widths = [
                    ("A", 260),
                    ("B", 150),
                    ("C", 140),
                    ("D", 140),
                    ("E", 160),
                    ("F", 160),
                    ("G", 140),
                    ("H", 110),
                ]
                batch.set_column_widths(worksheet, widths)

                # 2. Main Title (A1:H1) and Last Updated (A2:B2)
                title_fmt = CellFormat(
                    backgroundColor=Color(0.9, 0.9, 0.9),
                    textFormat=TextFormat(bold=True, fontSize=13),
                    horizontalAlignment="LEFT",
                )
                ts_fmt = CellFormat(
                    textFormat=TextFormat(italic=True, fontSize=9, foregroundColor=Color(0.4, 0.4, 0.4)),
                    horizontalAlignment="LEFT",
                )
                batch.format_cell_range(worksheet, "A1:H1", title_fmt)
                batch.format_cell_range(worksheet, "A2:B2", ts_fmt)

                # 3. Section 1: Investment Breakdown (Row 4-8)
                batch.format_cell_range(worksheet, "A4:C4", HEADER_FMT)
                batch.format_cell_range(worksheet, "A5:C5", SUBHEADER_FMT)
                batch.format_cell_range(worksheet, "B6:B8", CURRENCY_FMT)
                batch.format_cell_range(worksheet, "C6:C8", PERCENT_FMT)

                # 4. Section 2: Portfolio Performance (Row 10-15)
                batch.format_cell_range(worksheet, "A10:B10", HEADER_FMT)
                batch.format_cell_range(worksheet, "A11:B11", SUBHEADER_FMT)
                batch.format_cell_range(worksheet, "B12:B13", CURRENCY_FMT)
                # Total P&L (B14)
                pnl_fmt = GREEN_PNL_FMT if overall.total_pnl >= 0 else RED_PNL_FMT
                batch.format_cell_range(worksheet, "B14", pnl_fmt)
                # Return % (B15)
                ret_fmt = GREEN_TEXT_FMT if overall.overall_return_percentage >= 0 else RED_TEXT_FMT
                batch.format_cell_range(worksheet, "B15", ret_fmt)

                # 5. Section 3: Individual Portfolio Summary (Row 17+)
                batch.format_cell_range(worksheet, "A17:H17", HEADER_FMT)
                batch.format_cell_range(worksheet, "A18:H18", SUBHEADER_FMT)

                num_accounts = len(portfolio_summaries)
                start_row = 19
                end_account_row = start_row + num_accounts - 1
                total_row = start_row + num_accounts

                # Account rows
                if num_accounts > 0:
                    batch.format_cell_range(worksheet, f"B{start_row}:F{end_account_row}", CURRENCY_FMT)
                    for offset, summary in enumerate(portfolio_summaries.values()):
                        curr_r = start_row + offset
                        acct_pnl_fmt = GREEN_PNL_FMT if summary.total_pnl >= 0 else RED_PNL_FMT
                        acct_ret_fmt = GREEN_TEXT_FMT if summary.return_percentage >= 0 else RED_TEXT_FMT
                        batch.format_cell_range(worksheet, f"G{curr_r}", acct_pnl_fmt)
                        batch.format_cell_range(worksheet, f"H{curr_r}", acct_ret_fmt)

                # TOTAL row
                batch.format_cell_range(worksheet, f"A{total_row}:H{total_row}", HEADER_FMT)
                batch.format_cell_range(worksheet, f"B{total_row}:F{total_row}", CURRENCY_FMT)
                tot_pnl_fmt = GREEN_PNL_FMT if overall.total_pnl >= 0 else RED_PNL_FMT
                tot_ret_fmt = GREEN_TEXT_FMT if overall.overall_return_percentage >= 0 else RED_TEXT_FMT
                batch.format_cell_range(worksheet, f"G{total_row}", tot_pnl_fmt)
                batch.format_cell_range(worksheet, f"H{total_row}", tot_ret_fmt)

            logger.info("Summary sheet batch formatting applied successfully.")
        except Exception as exc:
            logger.warning("Formatting error on summary worksheet: %s", exc, exc_info=True)
