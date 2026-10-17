"""
Kite Authentication Manager

Interactive and token-based authentication helper for Zerodha KiteConnect.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from kiteconnect import KiteConnect

logger = logging.getLogger(__name__)


class KiteAuthManager:
    """Manages authentication and access token loading for Zerodha KiteConnect."""

    def __init__(self, api_key: str, api_secret: str, token_file: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.token_file = token_file
        self.kite = KiteConnect(api_key=api_key)

    @property
    def token_path(self) -> Path:
        """Full path to the token file under ~/.kites/."""
        token_dir = Path.home() / ".kites"
        token_dir.mkdir(parents=True, exist_ok=True)
        return token_dir / self.token_file

    def load_token_data(self) -> Dict[str, Any]:
        """Load token data from ~/.kites/<token_file>."""
        if self.token_path.exists():
            try:
                return json.loads(self.token_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not parse token file at %s: %s", self.token_path, exc)
                return {}
        return {}

    def save_token_data(self, data: Dict[str, Any]) -> None:
        """Atomically persist token data."""
        tmp = self.token_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.token_path)

    def try_load_token(self) -> bool:
        """Attempt to load and validate existing saved access token."""
        token_data = self.load_token_data()
        token = token_data.get("access_token")
        if token:
            try:
                self.kite.set_access_token(token)
                self.kite.profile()
                logger.info("Validated session using saved token for key length=%d", len(self.api_key))
                return True
            except Exception:
                logger.debug("Saved token was invalid or expired.")
        return False

    def login(self) -> None:
        """Interactive console login flow."""
        print(f"🔐 Login required for API key (len={len(self.api_key)})")
        print("URL:", self.kite.login_url())
        req = input("request_token: ").strip()
        data = self.kite.generate_session(req, api_secret=self.api_secret)
        self.kite.set_access_token(data["access_token"])

        token_data = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "created_at": datetime.datetime.now().isoformat(),
            "expires_at": (datetime.datetime.now() + datetime.timedelta(days=1)).isoformat(),
        }
        self.save_token_data(token_data)
        print("✅ Logged in & token saved.")

    def get_client(self) -> KiteConnect:
        """Get an authenticated KiteConnect client, prompting login if needed."""
        if not self.try_load_token():
            self.login()
        return self.kite
