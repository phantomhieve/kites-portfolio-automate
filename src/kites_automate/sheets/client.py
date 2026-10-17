"""
Google Sheets Client & SheetManager

Provides resilient, quota-aware Google Sheets operations with exponential
backoff retry handling to prevent HTTP 429 (Resource Exhausted) failures.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import gspread
from gspread_formatting import (
    Border,
    Borders,
    CellFormat,
    Color,
    NumberFormat,
    TextFormat,
    format_cell_range,
    set_column_widths,
)

from ..utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# Transient Google Sheets API exceptions worth retrying
SHEETS_RETRY_EXCEPTIONS = (
    gspread.exceptions.APIError,
    gspread.exceptions.GSpreadException,
    ConnectionError,
    TimeoutError,
    OSError,
)


def _resolve_credentials_path(explicit_path: Optional[str] = None) -> str:
    """Find the credentials.json file in standard locations."""
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.extend([
        Path("credentials.json"),
        Path.home() / ".kites" / "credentials.json",
        Path(__file__).resolve().parent.parent.parent.parent / "credentials.json",
    ])
    for cand in candidates:
        if cand.is_file():
            return str(cand.resolve())
    # Return explicit_path or default fallback
    return explicit_path or "credentials.json"


class SheetManager:
    """Manages Google Sheets operations and formatting with automatic retry backoff."""

    # Pre-defined cell formats
    HEADER_BLUE = CellFormat(
        backgroundColor=Color(0.2, 0.4, 0.8),
        textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1)),
    )
    HEADER_GREEN = CellFormat(
        backgroundColor=Color(0.4, 0.6, 0.4),
        textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1)),
    )
    HEADER_BROWN = CellFormat(
        backgroundColor=Color(0.55, 0.55, 0.25),
        textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1)),
    )
    SUMMARY_HEADER = CellFormat(
        backgroundColor=Color(0.8, 0.8, 1),
        textFormat=TextFormat(bold=True),
    )
    CURRENCY_FORMAT = CellFormat(
        numberFormat=NumberFormat(type="CURRENCY", pattern="₹#,##0.00")
    )
    BORDER_FORMAT = CellFormat(
        borders=Borders(
            top=Border("SOLID", Color(0.7, 0.7, 0.7)),
            bottom=Border("SOLID", Color(0.7, 0.7, 0.7)),
            left=Border("SOLID", Color(0.7, 0.7, 0.7)),
            right=Border("SOLID", Color(0.7, 0.7, 0.7)),
        )
    )
    GREEN_CELL = CellFormat(
        backgroundColor=Color(0.82, 1, 0.82),
        textFormat=TextFormat(bold=True, foregroundColor=Color(0, 0.5, 0)),
    )
    RED_CELL = CellFormat(
        backgroundColor=Color(1, 0.88, 0.88),
        textFormat=TextFormat(bold=True, foregroundColor=Color(0.7, 0, 0)),
    )

    def __init__(self, creds_path: Optional[str] = None):
        resolved_path = _resolve_credentials_path(creds_path)
        self.creds_path = resolved_path
        self.client = self._get_client(resolved_path)

    @staticmethod
    def _get_client(creds_path: str) -> gspread.Client:
        """Authenticate with Google Sheets using service account credentials."""
        if not os.path.exists(creds_path):
            logger.warning("Google credentials file not found: %s", creds_path)
            raise FileNotFoundError(f"Google credentials file not found: {creds_path}")

        # Try google.oauth2 first (modern standard)
        try:
            from google.oauth2.service_account import Credentials
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(creds_path, scopes=scope)
            return gspread.authorize(creds)
        except ImportError:
            pass

        # Fallback to gspread native service_account loader
        try:
            return gspread.service_account(filename=creds_path)
        except Exception:
            pass

        # Fallback to oauth2client if present
        try:
            from oauth2client.service_account import ServiceAccountCredentials
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
            return gspread.authorize(creds)
        except ImportError as exc:
            raise ImportError(
                "Neither google-auth nor oauth2client is available to authorize Google Sheets."
            ) from exc

    @retry_with_backoff(retries=5, initial_delay=2.0, exceptions=SHEETS_RETRY_EXCEPTIONS, retry_message="Retrying Google Spreadsheet open/create")
    def get_or_create_sheet(self, name: str) -> gspread.Spreadsheet:
        """Get or create a spreadsheet with the given name."""
        try:
            return self.client.open(name)
        except gspread.SpreadsheetNotFound:
            logger.info("Spreadsheet '%s' not found; creating new spreadsheet...", name)
            return self.client.create(name)

    @retry_with_backoff(retries=5, initial_delay=2.0, exceptions=SHEETS_RETRY_EXCEPTIONS, retry_message="Retrying Worksheet get/create")
    def get_or_create_worksheet(
        self,
        sheet: gspread.Spreadsheet,
        name: str,
        rows: int = 1000,
        cols: int = 26,
    ) -> gspread.Worksheet:
        """Get or create a worksheet in the given spreadsheet."""
        try:
            ws = sheet.worksheet(name)
            ws.clear()
            return ws
        except gspread.WorksheetNotFound:
            logger.info("Worksheet '%s' not found; creating with %dx%d dimensions...", name, rows, cols)
            return sheet.add_worksheet(name, rows=rows, cols=cols)

    @staticmethod
    @retry_with_backoff(retries=4, initial_delay=2.0, exceptions=SHEETS_RETRY_EXCEPTIONS, retry_message="Retrying column width formatting")
    def apply_column_widths(worksheet: gspread.Worksheet, widths: dict[str, int]) -> None:
        """Apply column widths to the worksheet."""
        set_column_widths(worksheet, [(col, width) for col, width in widths.items()])

    @staticmethod
    @retry_with_backoff(retries=4, initial_delay=2.0, exceptions=SHEETS_RETRY_EXCEPTIONS, retry_message="Retrying cell range formatting")
    def format_range(worksheet: gspread.Worksheet, cell_range: str, format_spec: CellFormat) -> None:
        """Apply formatting to a range of cells."""
        format_cell_range(worksheet, cell_range, format_spec)

    @staticmethod
    @retry_with_backoff(retries=5, initial_delay=2.0, exceptions=SHEETS_RETRY_EXCEPTIONS, retry_message="Retrying worksheet value batch update")
    def update_values(worksheet: gspread.Worksheet, range_name: str, values: List[List[Any]]) -> None:
        """Batch update cell values."""
        worksheet.update(values=values, range_name=range_name)
