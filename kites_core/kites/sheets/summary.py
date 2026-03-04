"""
Summary Sheet Manager

This module handles overall portfolio summary data processing and sheet updates,
providing a high-level overview of all portfolio holdings.
"""

from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
import gspread
from datetime import datetime
import time
import random
import os
import json

from .sheet_manager import SheetManager
from .portfolio import PortfolioSummary
from ..utils.helpers import safe_float


@dataclass
class OverallSummary:
    """Overall summary across all portfolios."""
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
    """Manages summary sheet data and formatting."""

    def __init__(self, sheet_manager: SheetManager, state_file: str = ".summary_formatting_state.json"):
        """
        Initialize the SummaryManager.

        Args:
            sheet_manager: SheetManager instance for Google Sheets operations
            state_file: Local file to track formatting state (no API calls needed)
        """
        self.sheet_manager = sheet_manager
        self.state_file = state_file
        self.formatting_state = self._load_formatting_state()

    def _load_formatting_state(self) -> Dict[str, bool]:
        """Load formatting state from local file (no API calls)."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load formatting state: {e}")
        return {}

    def _save_formatting_state(self):
        """Save formatting state to local file (no API calls)."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.formatting_state, f)
        except Exception as e:
            print(f"Warning: Could not save formatting state: {e}")

    def _get_sheet_key(self, worksheet: gspread.Worksheet) -> str:
        """Get a unique key for the worksheet to track formatting state."""
        return f"{worksheet.spreadsheet.id}_{worksheet.title}"

    def _is_formatted(self, worksheet: gspread.Worksheet) -> bool:
        """Check if worksheet is formatted using local state (NO API CALLS)."""
        sheet_key = self._get_sheet_key(worksheet)
        return self.formatting_state.get(sheet_key, False)

    def _mark_as_formatted(self, worksheet: gspread.Worksheet):
        """Mark worksheet as formatted in local state (NO API CALLS)."""
        sheet_key = self._get_sheet_key(worksheet)
        self.formatting_state[sheet_key] = True
        self._save_formatting_state()
        print(f"✅ Marked {sheet_key} as formatted in local state")

    def create_summary_data(self, portfolio_summaries: Dict[str, PortfolioSummary]) -> List[List[Any]]:
        """
        Create summary data from multiple portfolio summaries.

        Args:
            portfolio_summaries: Dictionary mapping portfolio names to their summaries

        Returns:
            List of rows for the summary sheet
        """
        # Create overall summary
        overall = OverallSummary()
        
        # Aggregate all portfolio data
        for summary in portfolio_summaries.values():
            overall.total_stocks_value += summary.stocks_value
            overall.total_index_funds_value += summary.index_funds_value
            overall.total_other_funds_value += summary.other_funds_value
            overall.total_investment += summary.total_investment
            overall.total_pnl += summary.total_pnl

        rows = [
            ["📊 Portfolio Summary Dashboard"],
            ["Last Updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [],
            ["📈 Investment Breakdown"],
            ["Category", "Current Value", "Percentage"],
            ["Stocks", overall.total_stocks_value, self._calculate_percentage(overall.total_stocks_value, overall.total_current_value)],
            ["Index Funds", overall.total_index_funds_value, self._calculate_percentage(overall.total_index_funds_value, overall.total_current_value)],
            ["Other Funds", overall.total_other_funds_value, self._calculate_percentage(overall.total_other_funds_value, overall.total_current_value)],
            [],
            ["📊 Portfolio Performance"],
            ["Metric", "Value"],
            ["Total Current Value", overall.total_current_value],
            ["Total Investment", overall.total_investment],
            ["Total P&L", overall.total_pnl],
            ["Overall Return %", f"{overall.overall_return_percentage:.2f}%"],
            [],
            ["📈 Individual Portfolio Summary"],
            ["Portfolio", "Stocks", "Index Funds", "Other Funds", "Total Value"]
        ]

        # Add individual portfolio rows
        for portfolio_name, summary in portfolio_summaries.items():
            rows.append([
                portfolio_name,
                summary.stocks_value,
                summary.index_funds_value,
                summary.other_funds_value,
                summary.total_value
            ])

        return rows

    def _calculate_percentage(self, value: float, total: float) -> str:
        """Calculate percentage and return as formatted string."""
        if total > 0:
            percentage = (value / total) * 100
            return f"{percentage:.1f}%"
        return "0.0%"

    def _retry_api_call(self, func, *args, max_retries=3, **kwargs):
        """Retry API calls with exponential backoff for quota limits."""
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if "429" in str(e) or "Quota exceeded" in str(e):
                    if attempt < max_retries - 1:
                        # Exponential backoff with jitter
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        print(f"Quota limit hit, waiting {wait_time:.1f}s before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print("Max retries reached for quota limit. Skipping this formatting operation.")
                        return None
                else:
                    # Re-raise non-quota errors immediately
                    raise e

    def format_summary_sheet(self, worksheet: gspread.Worksheet) -> None:
        """Apply formatting to the summary sheet using batched requests to minimize API calls."""
        
        try:
            # Clear existing formatting
            worksheet.clear_basic_filter()
            
            # Small delay to avoid hitting quota
            time.sleep(0.5)
            
        except Exception as e:
            if "429" in str(e):
                print("Quota limit hit during clear. Continuing with formatting...")
                time.sleep(2)
            else:
                print(f"Warning: Could not clear formatting: {e}")

        # Get data once to determine ranges
        try:
            all_data = self._retry_api_call(worksheet.get_all_values)
            if all_data is None:
                print("Could not get sheet data due to quota limits. Using default ranges.")
                portfolio_end_row = 25  # Safe default
            else:
                portfolio_end_row = len(all_data)
        except Exception as e:
            print(f"Could not get sheet data: {e}. Using default ranges.")
            portfolio_end_row = 25

        # Batch all formatting requests to minimize API calls
        try:
            batch_requests = []
            sheet_id = worksheet._properties['sheetId']
            
            # 1. Main dashboard header (A1:E1)
            batch_requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 5
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                            "textFormat": {"bold": True, "fontSize": 14},
                            "horizontalAlignment": "CENTER"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                }
            })

            # 2. Last updated (A2:B2)
            batch_requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 2,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.98, "green": 0.98, "blue": 0.98},
                            "textFormat": {"italic": True}
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)"
                }
            })

            # 3. Section headers (Investment Breakdown, Portfolio Performance, Individual Portfolio)
            section_headers = [
                (3, 4, 0, 3),   # A4:C4 - Investment Breakdown
                (4, 5, 0, 3),   # A5:C5 - Investment Breakdown column headers
                (9, 10, 0, 2),  # A10:B10 - Portfolio Performance
                (10, 11, 0, 2), # A11:B11 - Portfolio Performance column headers
                (16, 17, 0, 5), # A17:E17 - Individual Portfolio Summary
                (17, 18, 0, 5)  # A18:E18 - Individual Portfolio column headers
            ]
            
            for start_row, end_row, start_col, end_col in section_headers:
                batch_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                                "textFormat": {"bold": True},
                                "horizontalAlignment": "LEFT"
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                    }
                })

            # 4. Currency formatting for value columns
            currency_ranges = [
                (5, 8, 1, 2),   # B6:B8 - Investment breakdown values
                (11, 16, 1, 2), # B12:B16 - Portfolio performance values
            ]
            
            # Add individual portfolio currency formatting if we have data
            if portfolio_end_row >= 19:
                currency_ranges.append((18, portfolio_end_row, 1, 5))  # B19:E{end} - Individual portfolios
            
            for start_row, end_row, start_col, end_col in currency_ranges:
                batch_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {"type": "CURRENCY", "pattern": "₹#,##0.00"}
                            }
                        },
                        "fields": "userEnteredFormat(numberFormat)"
                    }
                })

            # 5. Percentage column formatting (C6:C8)
            batch_requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 5,
                        "endRowIndex": 8,
                        "startColumnIndex": 2,
                        "endColumnIndex": 3
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "horizontalAlignment": "RIGHT"
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,horizontalAlignment)"
                }
            })

            # Execute batch formatting with retry logic
            if batch_requests:
                result = self._retry_api_call(
                    worksheet.spreadsheet.batch_update,
                    {"requests": batch_requests}
                )
                if result:
                    print("Basic formatting applied successfully")
                else:
                    print("Basic formatting skipped due to quota limits")

            # Small delay before conditional formatting
            time.sleep(1)

            # Apply conditional formatting for P&L (separate request due to complexity)
            self._apply_conditional_formatting(worksheet, sheet_id)

        except Exception as e:
            print(f"Warning: Could not apply batch formatting: {e}")

        # Set column widths (less API intensive)
        try:
            widths = {
                "A": 300,  # Category/Portfolio name
                "B": 150,  # Values
                "C": 120,  # Percentage/Values
                "D": 150,  # Values
                "E": 150,  # Values
            }
            self._retry_api_call(self.sheet_manager.apply_column_widths, worksheet, widths)
        except Exception as e:
            print(f"Warning: Could not apply column widths: {e}")

    def _apply_conditional_formatting(self, worksheet: gspread.Worksheet, sheet_id: int) -> None:
        """Apply conditional formatting with retry logic."""
        try:
            # Conditional formatting for P&L and return percentage
            conditional_requests = []
            
            # P&L formatting (row 14, column B)
            for condition_type, color in [("NUMBER_GREATER", {"red": 0, "green": 0.6, "blue": 0}), 
                                        ("NUMBER_LESS", {"red": 0.8, "green": 0, "blue": 0})]:
                conditional_requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 13,
                                "endRowIndex": 14,
                                "startColumnIndex": 1,
                                "endColumnIndex": 2
                            }],
                            "booleanRule": {
                                "condition": {"type": condition_type, "values": [{"userEnteredValue": "0"}]},
                                "format": {"textFormat": {"foregroundColor": color}}
                            }
                        }
                    }
                })

            # Return percentage formatting (row 15, column B)
            for condition_type, color in [("NUMBER_GREATER", {"red": 0, "green": 0.6, "blue": 0}), 
                                        ("NUMBER_LESS", {"red": 0.8, "green": 0, "blue": 0})]:
                conditional_requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 14,
                                "endRowIndex": 15,
                                "startColumnIndex": 1,
                                "endColumnIndex": 2
                            }],
                            "booleanRule": {
                                "condition": {"type": condition_type, "values": [{"userEnteredValue": "0"}]},
                                "format": {"textFormat": {"foregroundColor": color}}
                            }
                        }
                    }
                })

            # Apply conditional formatting with retry
            if conditional_requests:
                result = self._retry_api_call(
                    worksheet.spreadsheet.batch_update,
                    {"requests": conditional_requests}
                )
                if result:
                    print("Conditional formatting applied successfully")
                else:
                    print("Conditional formatting skipped due to quota limits")

        except Exception as e:
            print(f"Warning: Could not apply conditional formatting: {e}")

    def update_data_only(self, worksheet: gspread.Worksheet,
                        portfolio_summaries: Dict[str, PortfolioSummary]) -> OverallSummary:
        """
        Update only the data without any formatting (minimal API usage).

        Args:
            worksheet: The worksheet to update
            portfolio_summaries: Dictionary of portfolio names to their summaries

        Returns:
            OverallSummary: Overall summary across all portfolios
        """
        print("📝 Creating summary data...")
        # Create summary data
        summary_rows = self.create_summary_data(portfolio_summaries)
        
        print("⬆️ Updating sheet data (no formatting)...")
        # Update the sheet with retry logic - ONLY data update
        result = self._retry_api_call(worksheet.update, "A1", summary_rows)
        if result is None:
            print("❌ Failed to update sheet data due to quota limits")
            return OverallSummary()  # Return empty summary
        
        print("✅ Data updated successfully!")
        
        # Create and return overall summary
        overall = OverallSummary()
        for summary in portfolio_summaries.values():
            overall.total_stocks_value += summary.stocks_value
            overall.total_index_funds_value += summary.index_funds_value
            overall.total_other_funds_value += summary.other_funds_value
            overall.total_investment += summary.total_investment
            overall.total_pnl += summary.total_pnl
        
        return overall

    def update_summary_sheet(self, worksheet: gspread.Worksheet,
                           portfolio_summaries: Dict[str, PortfolioSummary],
                           force_formatting: bool = False) -> OverallSummary:
        """
        Update a worksheet with summary data.

        Args:
            worksheet: The worksheet to update
            portfolio_summaries: Dictionary of portfolio names to their summaries
            force_formatting: Force apply formatting even if already applied

        Returns:
            OverallSummary: Overall summary across all portfolios
        """
        print("📝 Creating summary data...")
        # Create summary data
        summary_rows = self.create_summary_data(portfolio_summaries)
        
        print("⬆️ Updating sheet data...")
        # Update the sheet with retry logic
        result = self._retry_api_call(worksheet.update, "A1", summary_rows)
        if result is None:
            print("❌ Failed to update sheet data due to quota limits")
            return OverallSummary()  # Return empty summary
        
        print("✅ Data updated successfully!")
        
        # Check local state for formatting (NO API CALLS)
        is_already_formatted = self._is_formatted(worksheet)
        
        if force_formatting or not is_already_formatted:
            if not is_already_formatted:
                print("🎨 First time formatting this sheet...")
            else:
                print("🎨 Force formatting requested...")
            
            print("🎨 Applying formatting...")
            self.format_summary_sheet(worksheet)
            self._mark_as_formatted(worksheet)  # Save state locally
        else:
            print("✅ Sheet already formatted (checked local state - no API calls)")
            print("💡 Use force_formatting=True to reformat anyway")
        
        print("📊 Creating overall summary...")
        # Create and return overall summary
        overall = OverallSummary()
        for summary in portfolio_summaries.values():
            overall.total_stocks_value += summary.stocks_value
            overall.total_index_funds_value += summary.index_funds_value
            overall.total_other_funds_value += summary.other_funds_value
            overall.total_investment += summary.total_investment
            overall.total_pnl += summary.total_pnl
        
        print("✅ Summary sheet update completed!")
        return overall 