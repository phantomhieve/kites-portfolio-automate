"""
Portfolio Manager

This module handles portfolio data processing and sheet updates,
including stock and mutual fund holdings.
"""

from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
import gspread
import os
import json

from .sheet_manager import SheetManager
from ..utils.helpers import safe_float


@dataclass
class PortfolioSummary:
    """Summary of a portfolio's holdings."""
    stocks_value: float = 0.0
    index_funds_value: float = 0.0
    other_funds_value: float = 0.0
    stocks_investment: float = 0.0
    index_funds_investment: float = 0.0
    other_funds_investment: float = 0.0

    @property
    def total_value(self) -> float:
        """Total portfolio value."""
        return self.stocks_value + self.index_funds_value + self.other_funds_value
    
    @property
    def total_investment(self) -> float:
        """Total investment value."""
        return self.stocks_investment + self.index_funds_investment + self.other_funds_investment
    
    @property
    def total_pnl(self) -> float:
        """Total profit/loss."""
        return self.total_value - self.total_investment


class PortfolioManager:
    """Manages portfolio data and sheet updates."""

    def __init__(self, sheet_manager: SheetManager, state_file: str = ".portfolio_formatting_state.json"):
        """
        Initialize the PortfolioManager.

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
            print(f"Warning: Could not load portfolio formatting state: {e}")
        return {}

    def _save_formatting_state(self):
        """Save formatting state to local file (no API calls)."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.formatting_state, f)
        except Exception as e:
            print(f"Warning: Could not save portfolio formatting state: {e}")

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

    def process_holdings(self, holdings: List[Dict[str, Any]], exception_list: List[str] = None) -> Tuple[List[List[Any]], PortfolioSummary]:
        """
        Process stock holdings data.

        Args:
            holdings: List of holding dictionaries from Kite API
            exception_list: List of stock symbols to exclude

        Returns:
            Tuple containing:
            - List of rows for the sheet
            - PortfolioSummary with calculated totals
        """
        rows = [
            ["📈 Stock Holdings"],
            ["Symbol", "Quantity", "Value (Purchased)", "Value (Current)", "P&L"]
        ]

        summary = PortfolioSummary()
        stock_rows = []
        others = {"quantity": 0, "buy_value": 0, "current_value": 0, "pnl": 0}
        
        # Normalize exception list
        exceptions = set(s.upper() for s in (exception_list or []))

        for holding in holdings:
            symbol = holding["tradingsymbol"]
            if symbol in exceptions:
                continue

            quantity = holding.get("opening_quantity", holding.get("quantity", 0))
            buy_value = quantity * holding["average_price"]
            current_value = quantity * holding["last_price"]
            pnl = current_value - buy_value

            if buy_value < 5_000:  # Group small holdings
                others["quantity"] += quantity
                others["buy_value"] += buy_value
                others["current_value"] += current_value
                others["pnl"] += pnl
            else:
                stock_rows.append([
                    symbol,
                    quantity,
                    buy_value,
                    current_value,
                    round(pnl, 2)
                ])
                summary.stocks_value += current_value
                summary.stocks_investment += buy_value

        # Add others row if exists
        if others["quantity"]:
            stock_rows.append([
                "Others",
                others["quantity"],
                others["buy_value"],
                others["current_value"],
                round(others["pnl"], 2)
            ])
            summary.stocks_value += others["current_value"]
            summary.stocks_investment += others["buy_value"]

        # Sort by P&L
        stock_rows.sort(key=lambda r: r[4], reverse=True)
        rows.extend(stock_rows)

        return rows, summary

    def process_mutual_funds(self, mf_holdings: List[Dict[str, Any]], 
                           summary: PortfolioSummary,
                           exception_list: List[str] = None) -> List[List[Any]]:
        """
        Process mutual fund holdings data.

        Args:
            mf_holdings: List of mutual fund holdings from Kite API
            summary: PortfolioSummary to update with fund values
            exception_list: List of fund names to exclude

        Returns:
            List of rows for the sheet
        """
        rows = []
        
        # Normalize exception list
        exceptions = set(s.upper() for s in (exception_list or []))

        # Filter holdings
        filtered_holdings = []
        for mf in mf_holdings:
            fund_name = mf.get("fund", "")
            # Check for exact match or substring match from exception list
            # Using exact match for now based on typical usage, but handling potential case differences
            if fund_name.upper() in exceptions:
                continue
            filtered_holdings.append(mf)

        # Process Index Funds
        rows.extend([
            [],
            ["📊 Index Mutual Funds"],
            ["Fund", "Units", "Value (Purchased)", "Value (Current)", "P&L"]
        ])

        for mf in filtered_holdings:
            if any(k in mf.get("fund", "").lower() for k in ["index", "nifty"]):
                units = safe_float(mf, "quantity")
                nav = safe_float(mf, "last_price")
                avg_price = safe_float(mf, "average_price")
                current_value = units * nav
                purchase_value = units * avg_price
                pnl = current_value - purchase_value
                
                rows.append([
                    mf["fund"],
                    units,
                    round(purchase_value, 2),
                    round(current_value, 2),
                    round(pnl, 2)
                ])
                summary.index_funds_value += current_value
                summary.index_funds_investment += purchase_value

        # Process Other Funds
        rows.extend([
            [],
            ["📊 Other Mutual Funds"],
            ["Fund", "Units", "Value (Purchased)", "Value (Current)", "P&L"]
        ])

        for mf in filtered_holdings:
            if not any(k in mf.get("fund", "").lower() for k in ["index", "nifty"]):
                units = safe_float(mf, "units") or safe_float(mf, "quantity")
                nav = safe_float(mf, "nav") or safe_float(mf, "last_price")
                avg_price = safe_float(mf, "average_price")
                current_value = units * nav
                purchase_value = units * avg_price
                pnl = current_value - purchase_value
                
                rows.append([
                    mf["fund"],
                    units,
                    round(purchase_value, 2),
                    round(current_value, 2),
                    round(pnl, 2)
                ])
                summary.other_funds_value += current_value
                summary.other_funds_investment += purchase_value

        return rows

    def create_summary_rows(self, summary: PortfolioSummary) -> List[List[Any]]:
        """Create simple summary rows for the portfolio."""
        return [
            ["📊 Summary: Stocks"],
            ["Total Value", summary.stocks_value],
            [],
            ["📊 Summary: Index Mutual Funds"],
            ["Total Value", summary.index_funds_value],
            [],
            ["📊 Summary: Other Mutual Funds"],
            ["Total Value", summary.other_funds_value],
            [],
            ["📊 Summary: Total Portfolio"],
            ["Total Value", summary.total_value]
        ]

    def format_portfolio_sheet(self, worksheet: gspread.Worksheet, 
                             stock_rows: int, idx_hdr: int, 
                             oth_hdr: int) -> None:
        """Apply formatting to the portfolio sheet."""
        # Clear existing formatting
        worksheet.clear_basic_filter()

        # Define formats
        header_format = {
            "backgroundColor": {
                "red": 0.9,
                "green": 0.9,
                "blue": 0.9
            },
            "textFormat": {
                "bold": True
            },
            "horizontalAlignment": "LEFT"
        }

        currency_format = {
            "numberFormat": {
                "type": "CURRENCY",
                "pattern": "₹#,##0.00"
            }
        }

        # Get actual data to find section positions dynamically
        try:
            all_data = worksheet.get_all_values()
            
            # Find actual positions of each section
            idx_funds_row = None
            other_funds_row = None
            
            for i, row in enumerate(all_data):
                if row and len(row) > 0:
                    if "📊 Index Mutual Funds" in str(row[0]):
                        idx_funds_row = i + 1  # Convert to 1-based
                    elif "📊 Other Mutual Funds" in str(row[0]):
                        other_funds_row = i + 1  # Convert to 1-based
            
        except Exception as e:
            print(f"Warning: Could not read data for formatting: {e}")
            # Fallback to calculated positions
            idx_funds_row = idx_hdr if idx_hdr > 0 else None
            other_funds_row = oth_hdr if oth_hdr > 0 else None

        # Format Stock Holdings section (always exists)
        worksheet.format("A1:E1", {
            "textFormat": {"bold": True},
            "backgroundColor": {
                "red": 0.9,
                "green": 0.9,
                "blue": 0.9
            }
        })

        # Format column headers
        worksheet.format("A2:E2", header_format)

        # Format currency columns for stocks (from row 3 to before next section)
        if idx_funds_row:
            stock_end = idx_funds_row - 2  # Before empty row and index header
        elif other_funds_row:
            stock_end = other_funds_row - 2  # Before empty row and other header
        else:
            stock_end = len(all_data) if 'all_data' in locals() else 10  # Default fallback
        
        if stock_end > 2:
            worksheet.format(f"C3:E{stock_end}", currency_format)

        # Format Index Funds section (if exists)
        if idx_funds_row:
            # Format section header
            worksheet.format(f"A{idx_funds_row}:E{idx_funds_row}", header_format)
            
            # Format subheader (Fund, Units, etc.)
            worksheet.format(f"A{idx_funds_row+1}:E{idx_funds_row+1}", header_format)
            
            # Format currency columns for index funds
            if other_funds_row:
                idx_end = other_funds_row - 2  # Before empty row and other header
            else:
                idx_end = len(all_data) if 'all_data' in locals() else idx_funds_row + 10
            
            if idx_end > idx_funds_row + 1:
                worksheet.format(f"C{idx_funds_row+2}:E{idx_end}", currency_format)

        # Format Other Funds section (if exists)
        if other_funds_row:
            # Format section header
            worksheet.format(f"A{other_funds_row}:E{other_funds_row}", header_format)
            
            # Format subheader (Fund, Units, etc.)
            worksheet.format(f"A{other_funds_row+1}:E{other_funds_row+1}", header_format)
            
            # Format currency columns for other funds
            other_end = len(all_data) if 'all_data' in locals() else other_funds_row + 10
            if other_end > other_funds_row + 1:
                worksheet.format(f"C{other_funds_row+2}:E{other_end}", currency_format)

        # Format P&L columns with conditional formatting
        try:
            if 'all_data' in locals():
                total_rows = len(all_data)
                
                # Create valid ranges for each section that exists
                valid_ranges = []
                
                # Stocks P&L range
                stock_start = 3
                if idx_funds_row:
                    stock_end = idx_funds_row - 2
                elif other_funds_row:
                    stock_end = other_funds_row - 2
                else:
                    stock_end = total_rows
                
                if stock_end >= stock_start:
                    valid_ranges.append((f"E{stock_start}:E{stock_end}", "stocks"))
                
                # Index funds P&L range
                if idx_funds_row:
                    idx_start = idx_funds_row + 2
                    if other_funds_row:
                        idx_end = other_funds_row - 2
                    else:
                        idx_end = total_rows
                    
                    if idx_end >= idx_start:
                        valid_ranges.append((f"E{idx_start}:E{idx_end}", "index_funds"))
                
                # Other funds P&L range
                if other_funds_row:
                    oth_start = other_funds_row + 2
                    oth_end = total_rows
                    
                    if oth_end >= oth_start:
                        valid_ranges.append((f"E{oth_start}:E{oth_end}", "other_funds"))
                
                # Apply conditional formatting to valid ranges
                for pnl_range, section in valid_ranges:
                    start_row = int(pnl_range.split(":")[0][1:])
                    end_row = int(pnl_range.split(":")[1][1:])
                    
                    if end_row < start_row:
                        continue
                        
                    # Add conditional formatting for positive and negative values
                    worksheet.spreadsheet.batch_update({
                        "requests": [{
                            "addConditionalFormatRule": {
                                "rule": {
                                    "ranges": [{
                                        "sheetId": worksheet._properties['sheetId'],
                                        "startRowIndex": start_row - 1,
                                        "endRowIndex": end_row,
                                        "startColumnIndex": 4,  # Column E
                                        "endColumnIndex": 5
                                    }],
                                    "booleanRule": {
                                        "condition": {
                                            "type": "NUMBER_GREATER",
                                            "values": [{"userEnteredValue": "0"}]
                                        },
                                        "format": {
                                            "textFormat": {
                                                "foregroundColor": {
                                                    "red": 0,
                                                    "green": 0.6,
                                                    "blue": 0
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }, {
                            "addConditionalFormatRule": {
                                "rule": {
                                    "ranges": [{
                                        "sheetId": worksheet._properties['sheetId'],
                                        "startRowIndex": start_row - 1,
                                        "endRowIndex": end_row,
                                        "startColumnIndex": 4,  # Column E
                                        "endColumnIndex": 5
                                    }],
                                    "booleanRule": {
                                        "condition": {
                                            "type": "NUMBER_LESS",
                                            "values": [{"userEnteredValue": "0"}]
                                        },
                                        "format": {
                                            "textFormat": {
                                                "foregroundColor": {
                                                    "red": 0.8,
                                                    "green": 0,
                                                    "blue": 0
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }]
                    })
                    
        except Exception as e:
            print(f"Warning: Could not apply conditional formatting: {e}")

        # Format simple Summary section
        summary_header_positions = [
            (1, "📊 Summary: Stocks"),           # Row 1
            (4, "📊 Summary: Index Mutual Funds"), # Row 4  
            (7, "📊 Summary: Other Mutual Funds"), # Row 7
            (10, "📊 Summary: Total Portfolio")   # Row 10
        ]

        for row_num, title in summary_header_positions:
            worksheet.format(f"J{row_num}", {
                "textFormat": {"bold": True},
                "backgroundColor": {
                    "red": 0.9,
                    "green": 0.9,
                    "blue": 0.9
                }
            })

        # Format simple summary value cells
        summary_value_rows = [2, 5, 8, 11]  # Based on simple create_summary_rows structure
        for row_num in summary_value_rows:
            # Format "Total Value" label
            worksheet.format(f"J{row_num}", {
                "textFormat": {"bold": True},
                "backgroundColor": {
                    "red": 0.95,
                    "green": 0.95,
                    "blue": 0.98
                }
            })
            
            # Format value cell with currency
            worksheet.format(f"K{row_num}", {
                "numberFormat": {
                    "type": "CURRENCY",
                    "pattern": "₹#,##0.00"
                },
                "textFormat": {"bold": True},
                "horizontalAlignment": "RIGHT"
            })

        # Set column widths using sheet_manager method
        widths = {
            "A": 300,  # Fund/Stock name
            "B": 100,  # Quantity/Units
            "C": 150,  # Purchase Value
            "D": 150,  # Current Value
            "E": 120,  # P&L
            "J": 200,  # Summary headers
            "K": 150,  # Summary values
        }
        self.sheet_manager.apply_column_widths(worksheet, widths)

    def update_portfolio_sheet(self, worksheet: gspread.Worksheet,
                             holdings: List[Dict[str, Any]],
                             mf_holdings: List[Dict[str, Any]], 
                             force_formatting: bool = False,
                             exception_list: List[str] = None) -> PortfolioSummary:
        """
        Update a worksheet with portfolio data.

        Args:
            worksheet: The worksheet to update
            holdings: Stock holdings data
            mf_holdings: Mutual fund holdings data
            force_formatting: Force apply formatting even if already applied
            exception_list: List of stock symbols to exclude

        Returns:
            PortfolioSummary: Summary of the portfolio
        """
        print("📝 Processing portfolio data...")
        
        # Process holdings
        stock_rows, summary = self.process_holdings(holdings, exception_list)
        
        # Process mutual funds
        mf_rows = self.process_mutual_funds(mf_holdings, summary, exception_list)
        
        # Combine all rows
        all_rows = stock_rows + mf_rows
        
        print("⬆️ Updating main data...")
        # Update main data
        worksheet.update("A1", all_rows)
        
        print("⬆️ Updating summary data...")
        # Update simple summary
        summary_rows = self.create_summary_rows(summary)
        worksheet.update("J1", summary_rows)
        
        print("✅ Data updated successfully!")
        
        # Check local state for formatting (NO API CALLS)
        is_already_formatted = self._is_formatted(worksheet)
        
        if force_formatting or not is_already_formatted:
            if not is_already_formatted:
                print("🎨 First time formatting this portfolio sheet...")
            else:
                print("🎨 Force formatting requested...")
            
            print("🎨 Applying portfolio formatting...")
            # Apply formatting
            self.format_portfolio_sheet(
                worksheet,
                len(stock_rows) + 2,  # +2 for headers
                len(stock_rows) + 5,  # +5 for spacing and headers
                len(stock_rows) + len(mf_rows) - 3  # -3 for last section
            )
            self._mark_as_formatted(worksheet)  # Save state locally
        else:
            print("✅ Portfolio sheet already formatted (checked local state - no API calls)")
            print("💡 Use force_formatting=True to reformat anyway")
        
        print("✅ Portfolio sheet update completed!")
        return summary

    def update_data_only(self, worksheet: gspread.Worksheet,
                        holdings: List[Dict[str, Any]],
                        mf_holdings: List[Dict[str, Any]],
                        exception_list: List[str] = None) -> PortfolioSummary:
        """
        Update only the data without any formatting (minimal API usage).

        Args:
            worksheet: The worksheet to update
            holdings: Stock holdings data
            mf_holdings: Mutual fund holdings data
            exception_list: List of stock symbols to exclude

        Returns:
            PortfolioSummary: Summary of the portfolio
        """
        print("📝 Processing portfolio data (data only)...")
        
        # Process holdings
        stock_rows, summary = self.process_holdings(holdings, exception_list)
        
        # Process mutual funds
        mf_rows = self.process_mutual_funds(mf_holdings, summary, exception_list)
        
        # Combine all rows
        all_rows = stock_rows + mf_rows
        
        print("⬆️ Updating main data (no formatting)...")
        # Update main data only
        worksheet.update("A1", all_rows)
        
        print("⬆️ Updating summary data (no formatting)...")
        # Update simple summary only
        summary_rows = self.create_summary_rows(summary)
        worksheet.update("J1", summary_rows)
        
        print("✅ Portfolio data updated successfully (no formatting)!")
        
        return summary 