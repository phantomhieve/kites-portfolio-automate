"""
Kite Authentication Manager

This module handles authentication with the Zerodha Kite API,
including token management and secure storage.
"""

import json
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from kiteconnect import KiteConnect


class KiteAuthManager:
    """Manages authentication and token handling for Kite API."""

    def __init__(self, api_key: str, api_secret: str, token_file: str):
        """
        Initialize the KiteAuthManager.

        Args:
            api_key: Kite API key
            api_secret: Kite API secret
            token_file: Name of the file to store the access token
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.token_file = token_file
        self.kite = KiteConnect(api_key=api_key)

    @property
    def token_path(self) -> Path:
        """Returns the full path to the token file in the .kites directory."""
        token_dir = Path.home() / ".kites"
        token_dir.mkdir(exist_ok=True)
        return token_dir / self.token_file

    def load_token_data(self) -> Dict[str, Any]:
        """Load token data from the secure token file."""
        if self.token_path.exists():
            try:
                with open(self.token_path) as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_token_data(self, data: Dict[str, Any]) -> None:
        """Save token data to the secure token file."""
        with open(self.token_path, "w") as f:
            json.dump(data, f)

    def try_load_token(self) -> bool:
        """
        Attempt to load and validate a saved access token.

        Returns:
            bool: True if a valid token was loaded, False otherwise
        """
        token_data = self.load_token_data()
        if token_data and "access_token" in token_data:
            try:
                self.kite.set_access_token(token_data["access_token"])
                self.kite.profile()  # Validate token
                print("✅  Logged in with saved token.")
                return True
            except Exception:
                print("⚠️  Saved token invalid.")
        return False

    def login(self) -> None:
        """
        Perform the login flow and save the new access token.
        
        This method will:
        1. Generate the login URL
        2. Prompt for the request token
        3. Generate and save the access token
        """
        print("🔐  Login required.")
        print("URL:", self.kite.login_url())
        req = input("request_token: ").strip()
        data = self.kite.generate_session(req, api_secret=self.api_secret)
        self.kite.set_access_token(data["access_token"])
        
        # Save token with metadata
        token_data = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "created_at": datetime.datetime.now().isoformat(),
            "expires_at": (datetime.datetime.now() + datetime.timedelta(days=1)).isoformat()
        }
        self.save_token_data(token_data)
        print("✅  Logged in & token saved securely.")

    def get_client(self) -> KiteConnect:
        """
        Get an authenticated KiteConnect client.

        Returns:
            KiteConnect: An authenticated client instance
        
        Raises:
            Exception: If authentication fails
        """
        if not self.try_load_token():
            self.login()
        return self.kite 