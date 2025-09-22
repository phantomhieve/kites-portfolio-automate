"""
Automated authentication for Kite Connect API using webhook capture.

This module provides semi-automated token renewal by:
1. Starting a local webhook server
2. Opening login URLs for user authentication
3. Automatically capturing request tokens from OAuth redirects
4. Generating access tokens without manual copy/paste
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from .webhook_server import capture_token_via_webhook

logger = logging.getLogger(__name__)


class AutomatedKiteAuth:
    """Automated authentication manager for Kite Connect."""
    
    def __init__(self, api_key: str, api_secret: str, profile_name: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.profile_name = profile_name
        self.token_file = os.path.expanduser(f"~/.kites/{profile_name}_access_token.txt")
        
    def get_valid_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if necessary."""
        # Check if we have a valid token
        if self._is_token_valid():
            token_data = self._load_token()
            if token_data:
                return token_data.get('access_token')
        
        # Token is expired or missing - attempt renewal
        logger.info("Token expired or missing for %s, attempting renewal", self.profile_name)
        return self._renew_token()
    
    def _is_token_valid(self) -> bool:
        """Check if the current token is valid and not expired."""
        try:
            token_data = self._load_token()
            if not token_data or 'expires_at' not in token_data:
                return False
            
            expires_str = token_data['expires_at']
            expires_dt = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
            
            # Consider token invalid if it expires within 1 hour
            now = datetime.now()
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=None)
                now = now.replace(tzinfo=None)
            
            return expires_dt > now + timedelta(hours=1)
            
        except Exception as exc:
            logger.warning("Error checking token validity for %s: %s", self.profile_name, exc)
            return False
    
    def _load_token(self) -> Optional[Dict[str, Any]]:
        """Load token data from file."""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    return json.load(f)
        except Exception as exc:
            logger.warning("Error loading token for %s: %s", self.profile_name, exc)
        return None
    
    def _save_token(self, token_data: Dict[str, Any]) -> None:
        """Save token data to file."""
        try:
            os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
            with open(self.token_file, 'w') as f:
                json.dump(token_data, f, indent=2)
            logger.info("Token saved for %s", self.profile_name)
        except Exception as exc:
            logger.error("Error saving token for %s: %s", self.profile_name, exc)
    
    def _renew_token(self) -> Optional[str]:
        """Renew the access token using webhook automation."""
        try:
            # Step 1: Capture request token via webhook
            logger.info("Starting automated token renewal for %s", self.profile_name)
            logger.info("🌐 Please open the URL that will be displayed and complete the login")
            
            request_token = capture_token_via_webhook(self.api_key, timeout=300)
            
            if not request_token:
                logger.error("Failed to capture request token for %s", self.profile_name)
                return None
            
            # Step 2: Generate access token using kiteconnect
            access_token = self._generate_access_token(request_token)
            
            if access_token:
                # Step 3: Save token with metadata
                token_data = {
                    "access_token": access_token,
                    "refresh_token": "",
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(days=1)).isoformat()
                }
                self._save_token(token_data)
                
                logger.info("✅ Token renewal completed for %s", self.profile_name)
                return access_token
            else:
                logger.error("Failed to generate access token for %s", self.profile_name)
                return None
                
        except Exception as exc:
            logger.error("Token renewal failed for %s: %s", self.profile_name, exc)
            return None
    
    def _generate_access_token(self, request_token: str) -> Optional[str]:
        """Generate access token from request token using kiteconnect."""
        try:
            # Import kiteconnect in the legacy project's venv
            python_code = f"""
import sys
import os

# Add legacy project to path
legacy_path = os.path.expanduser("~/apps/kites-portfolio-tracker")
if legacy_path not in sys.path:
    sys.path.insert(0, legacy_path)

from kiteconnect import KiteConnect

# Initialize KiteConnect
kite = KiteConnect(api_key="{self.api_key}")

# Generate session
try:
    data = kite.generate_session("{request_token}", api_secret="{self.api_secret}")
    print(data["access_token"])
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
"""
            
            # Run in legacy project's venv
            legacy_venv_python = os.path.expanduser("~/apps/kites-portfolio-tracker/.venv/bin/python")
            if not os.path.exists(legacy_venv_python):
                legacy_venv_python = "python3"
            
            result = subprocess.run(
                [legacy_venv_python, "-c", python_code],
                cwd=os.path.expanduser("~/apps/kites-portfolio-tracker"),
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                access_token = result.stdout.strip()
                if access_token and not access_token.startswith("ERROR:"):
                    return access_token
                else:
                    logger.error("Access token generation failed: %s", result.stdout)
            else:
                logger.error("Access token generation failed: %s", result.stderr)
                
        except Exception as exc:
            logger.error("Error generating access token: %s", exc)
        
        return None
    
    def open_login_url(self) -> str:
        """Generate and optionally open the login URL."""
        callback_url = "http://localhost:8080/callback"
        login_url = f"https://kite.zerodha.com/connect/login?api_key={self.api_key}&v=3&redirect_url={callback_url}"
        
        # Try to open URL in browser (if running on a system with GUI)
        try:
            import webbrowser
            webbrowser.open(login_url)
            logger.info("🌐 Login URL opened in browser")
        except Exception:
            logger.info("🌐 Please open this URL manually: %s", login_url)
        
        return login_url


def automated_token_renewal(profiles_config: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Perform automated token renewal for all profiles.
    
    Args:
        profiles_config: Dictionary containing profile configurations
        
    Returns:
        Dictionary mapping profile names to access tokens (or None if failed)
    """
    results = {}
    
    try:
        profiles = profiles_config.get('profiles', [])
        
        for profile in profiles:
            profile_name = profile.get('profile_name')
            api_key_env = profile.get('api_key_env')
            api_secret_env = profile.get('api_secret_env')
            
            if not all([profile_name, api_key_env, api_secret_env]):
                logger.warning("Incomplete profile config for %s", profile_name)
                results[profile_name] = None
                continue
            
            # Get API credentials from environment
            api_key = os.getenv(api_key_env)
            api_secret = os.getenv(api_secret_env)
            
            if not all([api_key, api_secret]):
                logger.warning("Missing API credentials for %s", profile_name)
                results[profile_name] = None
                continue
            
            # Attempt automated renewal
            auth_manager = AutomatedKiteAuth(api_key, api_secret, profile_name)
            access_token = auth_manager.get_valid_token()
            results[profile_name] = access_token
            
            if access_token:
                logger.info("✅ Token renewal successful for %s", profile_name)
            else:
                logger.error("❌ Token renewal failed for %s", profile_name)
            
            # Small delay between profiles
            time.sleep(2)
            
    except Exception as exc:
        logger.error("Automated token renewal failed: %s", exc)
    
    return results
