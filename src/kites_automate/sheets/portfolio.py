"""
Portfolio Data Processing & Google Sheets Formatter

Processes Zerodha Kite equity holdings and mutual fund portfolios,
aggregates P&L, and writes data to Google Sheets with local state
tracking for smart minimal formatting to prevent API quota exhaustion.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import gspread
from gspread_formatting import CellFormat, Color, NumberFormat, TextFormat, batch_updater

from ..utils.helpers import safe_float
from ..utils.retry import retry_with_backoff
from .client import SheetManager

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
QUANTITY_FMT = CellFormat(
    numberFormat=NumberFormat(type="NUMBER", pattern="#,##0.###"),
    horizontalAlignment="RIGHT",
)
CURRENCY_FMT = CellFormat(
    numberFormat=NumberFormat(type="CURRENCY", pattern="₹#,##0.00"),
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
SUMMARY_HEADER_FMT = CellFormat(
    backgroundColor=Color(0.9, 0.9, 0.9),
    textFormat=TextFormat(bold=True, fontSize=11),
    horizontalAlignment="LEFT",
)
SUMMARY_LABEL_FMT = CellFormat(
    textFormat=TextFormat(bold=True),
    horizontalAlignment="LEFT",
)


@dataclass
class PortfolioSummary:
    """Summary of a single account's holdings."""
    stocks_value: float = 0.0
    index_funds_value: float = 0.0
    other_funds_value: float = 0.0
    stocks_investment: float = 0.0
    index_funds_investment: float = 0.0
    other_funds_investment: float = 0.0

    @property
    def total_value(self) -> float:
        """Total portfolio current value."""
        return self.stocks_value + self.index_funds_value + self.other_funds_value

    @property
    def total_investment(self) -> float:
        """Total portfolio investment cost."""
        return self.stocks_investment + self.index_funds_investment + self.other_funds_investment

    @property
    def total_pnl(self) -> float:
        """Total unrealized profit / loss."""
        return self.total_value - self.total_investment

    @property
    def return_percentage(self) -> float:
        """Percentage return on total investment."""
        if self.total_investment > 0:
            return (self.total_pnl / self.total_investment) * 100
        return 0.0


class PortfolioManager:
    """Manages portfolio data processing and sheet writing."""

    def __init__(
        self,
        sheet_manager: SheetManager,
        state_file: str = ".portfolio_formatting_state.json",
    ):
        self.sheet_manager = sheet_manager
        self.state_file = Path(state_file)
        self.formatting_state = self._load_formatting_state()

    def _load_formatting_state(self) -> Dict[str, bool]:
        """Load formatting state from local JSON (avoids API calls)."""
        try:
            if self.state_file.is_file():
                return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load portfolio formatting state: %s", exc)
        return {}

    def _save_formatting_state(self) -> None:
        """Persist formatting state to local JSON file atomically."""
        try:
            tmp = self.state_file.with_suffix(".tmp")
            data = json.dumps(self.formatting_state, indent=2)
            tmp.write_text(data, encoding="utf-8")
            tmp.replace(self.state_file)
        except Exception as exc:
            logger.warning("Could not save portfolio formatting state: %s", exc)

    @staticmethod
    def _get_sheet_key(worksheet: gspread.Worksheet) -> str:
        return f"{worksheet.spreadsheet.id}_{worksheet.title}"

    def _is_formatted(self, worksheet: gspread.Worksheet) -> bool:
        return self.formatting_state.get(self._get_sheet_key(worksheet), False)

    def _mark_as_formatted(self, worksheet: gspread.Worksheet) -> None:
        key = self._get_sheet_key(worksheet)
        self.formatting_state[key] = True
        self._save_formatting_state()
        logger.debug("Marked %s as formatted in local state cache", key)

    def process_holdings(
        self,
        holdings: List[Dict[str, Any]],
        exception_list: Optional[List[str]] = None,
    ) -> Tuple[List[List[Any]], PortfolioSummary]:
        """Process equity holdings, grouping small holdings under 'Others'."""
        rows: List[List[Any]] = [
            ["📈 Stock Holdings"],
            ["Symbol", "Quantity", "Value (Purchased)", "Value (Current)", "P&L"],
        ]

        summary = PortfolioSummary()
        stock_rows: List[List[Any]] = []
        others = {"quantity": 0.0, "buy_value": 0.0, "current_value": 0.0, "pnl": 0.0}

        exceptions: Set[str] = set(s.upper() for s in (exception_list or []))

        for holding in holdings:
            symbol = str(holding.get("tradingsymbol", "")).strip()
            if not symbol or symbol in exceptions:
                continue

            # Prioritize opening_quantity for delivery holdings
            qty_raw = holding.get("opening_quantity")
            if qty_raw is None or qty_raw == 0:
                qty_raw = holding.get("quantity", 0)
            quantity = float(qty_raw or 0)
            if quantity <= 0:
                continue

            avg_price = safe_float(holding, "average_price")
            last_price = safe_float(holding, "last_price")
            buy_value = quantity * avg_price
            current_value = quantity * last_price
            pnl = current_value - buy_value

            if buy_value < 5_000.0:
                others["quantity"] += quantity
                others["buy_value"] += buy_value
                others["current_value"] += current_value
                others["pnl"] += pnl
            else:
                stock_rows.append([
                    symbol,
                    quantity,
                    round(buy_value, 2),
                    round(current_value, 2),
                    round(pnl, 2),
                ])
                summary.stocks_value += current_value
                summary.stocks_investment += buy_value

        if others["quantity"] > 0:
            stock_rows.append([
                "Others",
                others["quantity"],
                round(others["buy_value"], 2),
                round(others["current_value"], 2),
                round(others["pnl"], 2),
            ])
            summary.stocks_value += others["current_value"]
            summary.stocks_investment += others["buy_value"]

        # Sort stock holdings by P&L descending
        stock_rows.sort(key=lambda r: r[4], reverse=True)
        rows.extend(stock_rows)

        return rows, summary

    def process_mutual_funds(
        self,
        mf_holdings: List[Dict[str, Any]],
        summary: PortfolioSummary,
        exception_list: Optional[List[str]] = None,
    ) -> List[List[Any]]:
        """Process mutual funds into Index Funds and Other Mutual Funds categories."""
        rows: List[List[Any]] = []
        exceptions: Set[str] = set(s.upper() for s in (exception_list or []))

        filtered: List[Dict[str, Any]] = []
        for mf in mf_holdings:
            fund_name = str(mf.get("fund", "")).strip()
            if not fund_name or fund_name.upper() in exceptions:
                continue
            filtered.append(mf)

        # Index Mutual Funds
        rows.extend([
            [],
            ["📊 Index Mutual Funds"],
            ["Fund", "Units", "Value (Purchased)", "Value (Current)", "P&L"],
        ])

        for mf in filtered:
            fund_name = str(mf.get("fund", ""))
            if any(k in fund_name.lower() for k in ["index", "nifty"]):
                units = safe_float(mf, "quantity") or safe_float(mf, "units")
                nav = safe_float(mf, "last_price") or safe_float(mf, "nav")
                avg_price = safe_float(mf, "average_price")
                current_value = units * nav
                purchase_value = units * avg_price
                pnl = current_value - purchase_value

                rows.append([
                    fund_name,
                    units,
                    round(purchase_value, 2),
                    round(current_value, 2),
                    round(pnl, 2),
                ])
                summary.index_funds_value += current_value
                summary.index_funds_investment += purchase_value

        # Other Mutual Funds
        rows.extend([
            [],
            ["📊 Other Mutual Funds"],
            ["Fund", "Units", "Value (Purchased)", "Value (Current)", "P&L"],
        ])

        for mf in filtered:
            fund_name = str(mf.get("fund", ""))
            if not any(k in fund_name.lower() for k in ["index", "nifty"]):
                units = safe_float(mf, "units") or safe_float(mf, "quantity")
                nav = safe_float(mf, "nav") or safe_float(mf, "last_price")
                avg_price = safe_float(mf, "average_price")
                current_value = units * nav
                purchase_value = units * avg_price
                pnl = current_value - purchase_value

                rows.append([
                    fund_name,
                    units,
                    round(purchase_value, 2),
                    round(current_value, 2),
                    round(pnl, 2),
                ])
                summary.other_funds_value += current_value
                summary.other_funds_investment += purchase_value

        return rows

    def create_summary_rows(self, summary: PortfolioSummary) -> List[List[Any]]:
        """Create summary totals block for the account worksheet."""
        return [
            [],
            ["📊 Summary: Stocks"],
            ["Total Value", round(summary.stocks_value, 2)],
            [],
            ["📊 Summary: Index Mutual Funds"],
            ["Total Value", round(summary.index_funds_value, 2)],
            [],
            ["📊 Summary: Other Mutual Funds"],
            ["Total Value", round(summary.other_funds_value, 2)],
            [],
            ["🎯 Overall Portfolio Summary"],
            ["Total Portfolio Value", round(summary.total_value, 2)],
            ["Total Investment", round(summary.total_investment, 2)],
            ["Total P&L", round(summary.total_pnl, 2)],
        ]

    def update_sheet_smart(
        self,
        worksheet: gspread.Worksheet,
        kite_client: Any,
        exception_list: Optional[List[str]] = None,
        force_formatting: bool = False,
    ) -> PortfolioSummary:
        """Smart update: updates data, but only formats if not formatted previously or force_formatting=True."""
        is_formatted = self._is_formatted(worksheet)
        if not force_formatting and is_formatted:
            logger.info("Sheet '%s' already formatted; performing minimal data update.", worksheet.title)
            return self.update_sheet_minimal(worksheet, kite_client, exception_list)

        logger.info("Sheet '%s' applying formatting and data (force=%s)...", worksheet.title, force_formatting)
        summary = self.update_sheet(worksheet, kite_client, exception_list)
        self._mark_as_formatted(worksheet)
        return summary

    def update_sheet_minimal(
        self,
        worksheet: gspread.Worksheet,
        kite_client: Any,
        exception_list: Optional[List[str]] = None,
    ) -> PortfolioSummary:
        """Update only the values without re-applying expensive format requests."""
        all_rows, summary = self._prepare_all_rows(kite_client, exception_list)
        worksheet.clear()
        worksheet.update(values=all_rows, range_name="A1")
        logger.info("Updated data for '%s' (minimal mode, %d rows)", worksheet.title, len(all_rows))
        return summary

    def update_sheet(
        self,
        worksheet: gspread.Worksheet,
        kite_client: Any,
        exception_list: Optional[List[str]] = None,
    ) -> PortfolioSummary:
        """Full update: writes data and applies complete formatting."""
        all_rows, summary = self._prepare_all_rows(kite_client, exception_list)
        worksheet.clear()
        worksheet.update(values=all_rows, range_name="A1")

        # Apply formatting
        self._apply_sheet_formatting(worksheet, all_rows)
        logger.info("Updated data and applied styles for '%s'", worksheet.title)
        return summary

    def _prepare_all_rows(
        self,
        kite_client: Any,
        exception_list: Optional[List[str]],
    ) -> Tuple[List[List[Any]], PortfolioSummary]:
        # Fetch holdings from Kite
        logger.debug("Fetching equity holdings from Kite...")
        holdings = kite_client.holdings() or []
        logger.debug("Fetching mutual funds from Kite...")
        try:
            mf_holdings = kite_client.mf_holdings() or []
        except Exception as exc:
            logger.warning("Could not fetch mutual funds: %s", exc)
            mf_holdings = []

        stock_rows, summary = self.process_holdings(holdings, exception_list)
        mf_rows = self.process_mutual_funds(mf_holdings, summary, exception_list)
        summary_rows = self.create_summary_rows(summary)

        all_rows = stock_rows + mf_rows + summary_rows
        return all_rows, summary

    def update_portfolio_sheet(
        self,
        worksheet: gspread.Worksheet,
        holdings: List[Dict[str, Any]],
        mf_holdings: List[Dict[str, Any]],
        force_formatting: bool = False,
        exception_list: Optional[List[str]] = None,
    ) -> PortfolioSummary:
        """Update worksheet with explicitly provided holdings data."""
        stock_rows, summary = self.process_holdings(holdings or [], exception_list)
        mf_rows = self.process_mutual_funds(mf_holdings or [], summary, exception_list)
        summary_rows = self.create_summary_rows(summary)
        all_rows = stock_rows + mf_rows + summary_rows

        worksheet.clear()
        worksheet.update(values=all_rows, range_name="A1")

        is_formatted = self._is_formatted(worksheet)
        if force_formatting or not is_formatted:
            self._apply_sheet_formatting(worksheet, all_rows)
            self._mark_as_formatted(worksheet)
        return summary

    def update_data_only(
        self,
        worksheet: gspread.Worksheet,
        holdings: List[Dict[str, Any]],
        mf_holdings: List[Dict[str, Any]],
        exception_list: Optional[List[str]] = None,
    ) -> PortfolioSummary:
        """Update worksheet data without applying formatting calls."""
        return self.update_portfolio_sheet(
            worksheet=worksheet,
            holdings=holdings,
            mf_holdings=mf_holdings,
            force_formatting=False,
            exception_list=exception_list,
        )

    def _apply_sheet_formatting(self, worksheet: gspread.Worksheet, all_rows: List[List[Any]]) -> None:
        """Apply complete formatting to portfolio sheet via batch_updater (1 atomic API call)."""
        try:
            with batch_updater(worksheet.spreadsheet) as batch:
                # 1. Column widths
                widths = [
                    ("A", 320),  # Symbol / Fund
                    ("B", 110),  # Quantity / Units / Total Value label
                    ("C", 150),  # Value (Purchased)
                    ("D", 150),  # Value (Current)
                    ("E", 140),  # P&L
                ]
                batch.set_column_widths(worksheet, widths)

                # 2. Iterate through all rows and apply formats
                for idx, row in enumerate(all_rows, start=1):
                    if not row:
                        continue
                    first_cell = str(row[0]).strip()

                    # Main section headers
                    if any(h in first_cell for h in ["Stock Holdings", "Index Mutual Funds", "Other Mutual Funds"]):
                        batch.format_cell_range(worksheet, f"A{idx}:E{idx}", HEADER_FMT)
                    # Table subheaders (column names)
                    elif first_cell in ("Symbol", "Fund"):
                        batch.format_cell_range(worksheet, f"A{idx}:E{idx}", SUBHEADER_FMT)
                    # Summary block headers
                    elif any(s in first_cell for s in [
                        "Summary: Stocks",
                        "Summary: Index Mutual Funds",
                        "Summary: Other Mutual Funds",
                        "Overall Portfolio Summary",
                    ]):
                        batch.format_cell_range(worksheet, f"A{idx}:B{idx}", SUMMARY_HEADER_FMT)
                    # Summary value rows
                    elif first_cell in ("Total Value", "Total Portfolio Value", "Total Investment"):
                        batch.format_cell_range(worksheet, f"A{idx}", SUMMARY_LABEL_FMT)
                        batch.format_cell_range(worksheet, f"B{idx}", CURRENCY_FMT)
                    elif first_cell == "Total P&L":
                        batch.format_cell_range(worksheet, f"A{idx}", SUMMARY_LABEL_FMT)
                        pnl_val = safe_float({"val": row[1]}, "val") if len(row) > 1 else 0.0
                        fmt = GREEN_PNL_FMT if pnl_val >= 0 else RED_PNL_FMT
                        batch.format_cell_range(worksheet, f"B{idx}", fmt)
                    # Data row (Symbol or Fund with 5 columns: [name, qty/units, buy_val, curr_val, pnl])
                    elif len(row) >= 5 and isinstance(row[2], (int, float)):
                        batch.format_cell_range(worksheet, f"B{idx}", QUANTITY_FMT)
                        batch.format_cell_range(worksheet, f"C{idx}:D{idx}", CURRENCY_FMT)
                        pnl_val = float(row[4])
                        fmt = GREEN_PNL_FMT if pnl_val >= 0 else RED_PNL_FMT
                        batch.format_cell_range(worksheet, f"E{idx}", fmt)

            logger.info("Worksheet '%s' formatted successfully in 1 batched request.", worksheet.title)
        except Exception as exc:
            logger.warning("Formatting error on worksheet '%s': %s", worksheet.title, exc, exc_info=True)
