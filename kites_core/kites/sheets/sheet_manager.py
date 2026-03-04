"""
Google Sheets Manager

This module handles all interactions with Google Sheets,
including authentication and basic sheet operations.
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_formatting import (
    format_cell_range, CellFormat, Color, TextFormat, Border, Borders,
    NumberFormat, set_column_widths, set_frozen
)


class SheetManager:
    """Manages Google Sheets operations and formatting."""

    # Formatting constants
    HEADER_BLUE = CellFormat(
        backgroundColor=Color(0.2, 0.4, 0.8),
        textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1))
    )
    HEADER_GREEN = CellFormat(
        backgroundColor=Color(0.4, 0.6, 0.4),
        textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1))
    )
    HEADER_BROWN = CellFormat(
        backgroundColor=Color(0.55, 0.55, 0.25),
        textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1))
    )
    SUMMARY_HEADER = CellFormat(
        backgroundColor=Color(0.8, 0.8, 1),
        textFormat=TextFormat(bold=True)
    )
    CURRENCY_FORMAT = CellFormat(
        numberFormat=NumberFormat(type='CURRENCY', pattern='₹#,##0.00')
    )
    BORDER_FORMAT = CellFormat(
        borders=Borders(
            top=Border("SOLID", Color(0.7, 0.7, 0.7)),
            bottom=Border("SOLID", Color(0.7, 0.7, 0.7)),
            left=Border("SOLID", Color(0.7, 0.7, 0.7)),
            right=Border("SOLID", Color(0.7, 0.7, 0.7))
        )
    )
    GREEN_CELL = CellFormat(
        backgroundColor=Color(0.82, 1, 0.82),
        textFormat=TextFormat(bold=True, foregroundColor=Color(0, 0.5, 0))
    )
    RED_CELL = CellFormat(
        backgroundColor=Color(1, 0.88, 0.88),
        textFormat=TextFormat(bold=True, foregroundColor=Color(0.7, 0, 0))
    )

    def __init__(self, creds_path: str = "credentials.json"):
        """
        Initialize the SheetManager.

        Args:
            creds_path: Path to the Google Sheets credentials file
        """
        self.client = self._get_client(creds_path)

    def _get_client(self, creds_path: str) -> gspread.Client:
        """Get an authorized Google Sheets client."""
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        return gspread.authorize(creds)

    def get_or_create_sheet(self, name: str) -> gspread.Spreadsheet:
        """
        Get or create a spreadsheet with the given name.

        Args:
            name: Name of the spreadsheet

        Returns:
            gspread.Spreadsheet: The spreadsheet object
        """
        try:
            return self.client.open(name)
        except gspread.SpreadsheetNotFound:
            return self.client.create(name)

    def get_or_create_worksheet(self, sheet: gspread.Spreadsheet, 
                              name: str, rows: int = 1000, 
                              cols: int = 26) -> gspread.Worksheet:
        """
        Get or create a worksheet in the given spreadsheet.

        Args:
            sheet: The parent spreadsheet
            name: Name of the worksheet
            rows: Number of rows (default: 1000)
            cols: Number of columns (default: 26)

        Returns:
            gspread.Worksheet: The worksheet object
        """
        try:
            ws = sheet.worksheet(name)
            ws.clear()
            return ws
        except gspread.WorksheetNotFound:
            return sheet.add_worksheet(name, rows=rows, cols=cols)

    @staticmethod
    def apply_column_widths(worksheet: gspread.Worksheet, 
                           widths: dict[str, int]) -> None:
        """
        Apply column widths to the worksheet.

        Args:
            worksheet: The worksheet to format
            widths: Dictionary mapping column letters to widths
        """
        set_column_widths(worksheet, [(col, width) for col, width in widths.items()])

    @staticmethod
    def format_range(worksheet: gspread.Worksheet, 
                    cell_range: str, 
                    format: CellFormat) -> None:
        """
        Apply formatting to a range of cells.

        Args:
            worksheet: The worksheet to format
            cell_range: The A1 notation of the range to format
            format: The CellFormat to apply
        """
        format_cell_range(worksheet, cell_range, format) 