"""
Fully automated authentication for Kite Connect API.

This module provides complete hands-off token renewal by:
1. Starting a local webhook server
2. Automating browser login with stored credentials
3. Generating TOTP codes automatically
4. Capturing request tokens from OAuth redirects
5. Generating access tokens without any manual intervention

⚠️ SECURITY WARNING: This stores sensitive credentials and automates login.
Use only in secure environments and ensure credentials are properly encrypted.
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import threading

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    import pyotp
except ImportError as e:
    raise ImportError(f"Missing dependencies for full automation: {e}. Run: pip install selenium pyotp")

from .webhook_server import TokenWebhookServer

logger = logging.getLogger(__name__)

# Shared Firefox driver for the duration of a renewal batch
_SHARED_DRIVER = None  # type: ignore[var-annotated]

def _shutdown_shared_driver() -> None:
    """Gracefully shutdown the shared webdriver, if any."""
    global _SHARED_DRIVER
    try:
        if _SHARED_DRIVER is not None:
            try:
                _SHARED_DRIVER.quit()
            except Exception:
                pass
    finally:
        _SHARED_DRIVER = None


class FullyAutomatedKiteAuth:
    """Fully automated authentication manager for Kite Connect."""
    
    def __init__(self, api_key: str, api_secret: str, profile_name: str, 
                 username: str, password: str, totp_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.profile_name = profile_name
        self.username = username
        self.password = password
        self.totp_secret = totp_secret
        self.token_file = os.path.expanduser(f"~/.kites/{profile_name}_access_token.txt")
        
    def get_valid_token(self) -> Optional[str]:
        """Get a valid access token, fully automated renewal if necessary."""
        # Check if we have a valid token
        if self._is_token_valid():
            token_data = self._load_token()
            if token_data:
                logger.info("Using existing valid token for %s", self.profile_name)
                return token_data.get('access_token')
        
        # Token is expired or missing - attempt fully automated renewal
        logger.info("Token expired or missing for %s, starting fully automated renewal", self.profile_name)
        return self._fully_automated_renewal()
    
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
    
    def _generate_totp(self) -> Optional[str]:
        """Generate TOTP code from stored secret."""
        if not self.totp_secret:
            return None
        
        try:
            totp = pyotp.TOTP(self.totp_secret)
            code = totp.now()
            logger.info("Generated TOTP code for %s", self.profile_name)
            return code
        except Exception as exc:
            logger.error("Error generating TOTP for %s: %s", self.profile_name, exc)
            return None
    
    def _setup_webdriver(self) -> webdriver.Firefox:
        """Setup Firefox webdriver with appropriate options."""
        global _SHARED_DRIVER
        if _SHARED_DRIVER is not None:
            # Verify the existing session is still alive; if not, recreate
            try:
                _SHARED_DRIVER.execute_script("return 1")
                return _SHARED_DRIVER
            except Exception:
                _SHARED_DRIVER = None
        firefox_options = Options()
        # Force headless; also works without Xvfb
        firefox_options.add_argument("--headless")
        firefox_options.add_argument("--width=1920")
        firefox_options.add_argument("--height=1080")
        
        # Performance optimizations
        firefox_options.set_preference("dom.webdriver.enabled", False)
        firefox_options.set_preference("useAutomationExtension", False)
        firefox_options.set_preference("permissions.default.image", 2)  # Disable images
        firefox_options.set_preference("permissions.default.stylesheet", 2)  # Disable CSS
        firefox_options.set_preference("permissions.default.plugin", 2)  # Disable plugins
        firefox_options.set_preference("javascript.enabled", True)  # Keep JS for form submission
        firefox_options.set_preference("dom.ipc.plugins.enabled.libflashplayer.so", False)
        firefox_options.set_preference("media.volume_scale", "0.0")  # Mute audio
        firefox_options.set_preference("network.http.pipelining", True)
        firefox_options.set_preference("network.http.pipelining.maxrequests", 8)
        firefox_options.set_preference("content.notify.interval", 500000)
        firefox_options.set_preference("content.notify.ontimer", True)
        firefox_options.set_preference("content.switch.threshold", 500000)
        firefox_options.set_preference("browser.cache.disk.enable", False)
        firefox_options.set_preference("browser.cache.memory.enable", False)
        firefox_options.set_preference("browser.cache.offline.enable", False)
        firefox_options.set_preference("network.http.use-cache", False)
        
        # Use system geckodriver (try multiple paths for cross-platform)
        geckodriver_paths = [
            "/opt/homebrew/bin/geckodriver",  # macOS Homebrew
            "/usr/local/bin/geckodriver",     # Linux manual install
            "/usr/bin/geckodriver",           # Linux package manager
            "geckodriver"                     # System PATH
        ]
        
        for driver_path in geckodriver_paths:
            try:
                logger.info("Trying geckodriver at: %s", driver_path)
                # Suppress geckodriver logs
                service = Service(driver_path, log_output=os.devnull)
                driver = webdriver.Firefox(service=service, options=firefox_options)
                driver.implicitly_wait(1)  # Fast: 1 second only
                logger.info("Firefox webdriver initialized via: %s", driver_path)
                _SHARED_DRIVER = driver
                return _SHARED_DRIVER
            except Exception as exc:
                logger.warning("Geckodriver path failed %s: %s", driver_path, exc)
                continue

        # Fallback: use webdriver-manager to download/manage geckodriver
        try:
            from webdriver_manager.firefox import GeckoDriverManager
            logger.info("Attempting geckodriver setup via webdriver-manager")
            driver_path = GeckoDriverManager().install()
            service = Service(driver_path, log_output=os.devnull)
            driver = webdriver.Firefox(service=service, options=firefox_options)
            driver.implicitly_wait(1)
            logger.info("Firefox webdriver initialized via webdriver-manager")
            _SHARED_DRIVER = driver
            return _SHARED_DRIVER
        except Exception as exc:
            logger.error("webdriver-manager failed to provision geckodriver: %s", exc)
            logger.error("All geckodriver setup attempts failed")
            raise Exception("Could not initialize Firefox webdriver")
    
    def _automated_browser_login(self, login_url: str, timeout: int = 120) -> Optional[str]:
        """Perform fully automated browser login and capture request token."""
        driver = None
        server = None
        
        try:
            # Start webhook server
            server = TokenWebhookServer(host="localhost", port=8080)
            server.start()
            logger.info("Webhook server started for %s", self.profile_name)
            
            # Setup webdriver
            logger.info("Starting automated browser login for %s", self.profile_name)
            driver = self._setup_webdriver()
            try:
                # Ensure a clean session per profile (avoid cross-account bleed)
                driver.delete_all_cookies()
                driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
            except Exception:
                pass
            
            # Navigate to login page with a more forgiving strategy/timeout
            try:
                # Eager: DOMContentLoaded is enough; avoids waiting on ads/analytics
                driver.execute_script("return 1")
                driver.set_page_load_timeout(60)
                # Build login URL using the server's redirect URL helper
                login_url = server.get_redirect_url(self.api_key)
                driver.get(login_url)
                logger.info("Navigated to login page for %s", self.profile_name)
            except Exception as exc:
                logger.warning("Page load timed out/failed for %s: %s", self.profile_name, exc)
                # Save a screenshot for debugging and try to proceed anyway
                try:
                    driver.save_screenshot(f"/tmp/zerodha_login_timeout_{self.profile_name}.png")
                    logger.info("Timeout screenshot saved to /tmp/zerodha_login_timeout_%s.png", self.profile_name)
                except Exception:
                    pass
                # Attempt a single retry after a short pause
                try:
                    import time as _t
                    _t.sleep(2)
                    driver.get(login_url)
                    logger.info("Retry navigated to login page for %s", self.profile_name)
                except Exception as exc2:
                    logger.error("Retry page load failed for %s: %s", self.profile_name, exc2)
                    # Continue to element detection anyway; some sites still render enough
            
            # Wait for login form and fill credentials
            wait = WebDriverWait(driver, 5)  # Slightly more tolerant
            
            # Check page loaded correctly
            logger.info("Login page loaded: %s", driver.title)
            
            # Try different possible username field selectors (optimized order)
            username_field = None
            username_selectors = [
                (By.ID, "userid"),  # WINNER from logs - try first!
                (By.NAME, "user_id"),
                (By.NAME, "userid"),
                (By.ID, "user_id"),
                (By.NAME, "username"),
                (By.ID, "username")
            ]
            
            for selector_type, selector_value in username_selectors:
                try:
                    username_field = WebDriverWait(driver, 0.5).until(EC.presence_of_element_located((selector_type, selector_value)))
                    logger.info("Found username field using %s: %s", selector_type, selector_value)
                    break
                except Exception:
                    continue
            
            if not username_field:
                logger.error("Could not find username field on page")
                # Take screenshot for debugging
                driver.save_screenshot("/tmp/zerodha_login_debug.png")
                logger.info("Debug screenshot saved to /tmp/zerodha_login_debug.png")
                raise Exception("Username field not found")
            
            # Robustly focus and fill inputs in headless firefox
            def _robust_fill(el, text):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", el)
                except Exception:
                    pass
                try:
                    from selenium.webdriver import ActionChains
                    ActionChains(driver).move_to_element(el).perform()
                except Exception:
                    pass
                try:
                    el.click()
                except Exception:
                    pass
                try:
                    el.clear()
                except Exception:
                    pass
                try:
                    el.send_keys(text)
                    return True
                except Exception:
                    # Fallback: set value via JS and dispatch events
                    try:
                        driver.execute_script(
                            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true})); arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                            el,
                            text,
                        )
                        return True
                    except Exception:
                        return False

            if not _robust_fill(username_field, self.username):
                raise Exception("Failed to fill username field")
            logger.info("Username entered for %s", self.profile_name)
            
            # Fill password - optimized order
            password_field = None
            password_selectors = [
                (By.ID, "password"),  # WINNER from logs - try first!
                (By.NAME, "password"),
                (By.XPATH, "//input[@type='password']")
            ]
            
            for selector_type, selector_value in password_selectors:
                try:
                    password_field = driver.find_element(selector_type, selector_value)
                    logger.info("Found password field using %s: %s", selector_type, selector_value)
                    break
                except Exception:
                    continue
            
            if not password_field:
                logger.error("Could not find password field on page")
                driver.save_screenshot("/tmp/zerodha_password_debug.png")
                logger.info("Debug screenshot saved to /tmp/zerodha_password_debug.png")
                raise Exception("Password field not found")
            
            if not _robust_fill(password_field, self.password):
                raise Exception("Failed to fill password field")
            logger.info("Password entered for %s", self.profile_name)
            
            # Click login button
            login_button = driver.find_element(By.XPATH, "//button[@type='submit' or contains(text(), 'Login')]")
            login_button.click()
            logger.info("Login button clicked for %s", self.profile_name)
            
            # Handle 2FA if TOTP secret is provided
            if self.totp_secret:
                try:
                    logger.info("Waiting for 2FA page for %s", self.profile_name)
                    
                    # Wait for 2FA page to load
                    time.sleep(0.5)  # Very fast
                    
                    # Try TOTP field selectors - optimized order
                    totp_field = None
                    totp_selectors = [
                        (By.XPATH, "//input[@maxlength='6']"),  # WINNER from logs - try first!
                        (By.NAME, "totp"),
                        (By.ID, "totp"),
                        (By.CSS_SELECTOR, "input[autocomplete='one-time-code']")
                    ]
                    
                    for selector_type, selector_value in totp_selectors:
                        try:
                            totp_field = WebDriverWait(driver, 6).until(EC.presence_of_element_located((selector_type, selector_value)))
                            logger.info("Found TOTP field using %s: %s", selector_type, selector_value)
                            break
                        except Exception:
                            continue
                    
                    if not totp_field:
                        logger.error("Could not find TOTP field on 2FA page")
                        driver.save_screenshot("/tmp/zerodha_2fa_debug.png")
                        logger.info("2FA debug screenshot saved to /tmp/zerodha_2fa_debug.png")
                        raise Exception("TOTP field not found")
                    
                    # Generate and enter TOTP
                    totp_code = self._generate_totp()
                    if totp_code:
                        totp_field.clear()
                        totp_field.send_keys(totp_code)
                        logger.info("✅ TOTP code entered for %s", self.profile_name)
                        
                        # Try submit button selectors - optimized order
                        submit_button = None
                        submit_selectors = [
                            (By.XPATH, "//button[@type='submit']"),  # WINNER from logs - try first!
                            (By.CSS_SELECTOR, "button[type='submit']"),
                            (By.XPATH, "//input[@type='submit']")
                        ]
                        
                        for selector_type, selector_value in submit_selectors:
                            try:
                                submit_button = driver.find_element(selector_type, selector_value)
                                logger.info("Found submit button using %s: %s", selector_type, selector_value)
                                break
                            except Exception:
                                continue
                        
                        if submit_button:
                            submit_button.click()
                            logger.info("2FA submitted for %s", self.profile_name)
                        else:
                            logger.warning("Could not find submit button, trying Enter key")
                            totp_field.send_keys(Keys.RETURN)
                            logger.info("2FA submitted via Enter key for %s", self.profile_name)
                    else:
                        logger.warning("Failed to generate TOTP for %s", self.profile_name)
                        
                except Exception as exc:
                    logger.warning("2FA handling failed for %s: %s", self.profile_name, exc)
            
            # Wait for OAuth authorization page and approve
            try:
                logger.info("Waiting for OAuth authorization page for %s", self.profile_name)
                time.sleep(0.5)  # Minimal wait for page transition
                
                # Try multiple selectors for authorization button
                approve_button = None
                approve_selectors = [
                    (By.XPATH, "//button[contains(text(), 'Authorise')]"),
                    (By.XPATH, "//button[contains(text(), 'Authorize')]"),
                    (By.XPATH, "//button[contains(text(), 'Approve')]"),
                    (By.XPATH, "//button[contains(text(), 'Allow')]"),
                    (By.XPATH, "//button[contains(text(), 'Continue')]"),
                    (By.XPATH, "//input[@type='submit' and contains(@value, 'Authorise')]"),
                    (By.XPATH, "//input[@type='submit' and contains(@value, 'Approve')]"),
                    (By.CSS_SELECTOR, "button.btn-primary"),
                    (By.CSS_SELECTOR, ".authorize-btn"),
                    (By.CSS_SELECTOR, ".approve-btn"),
                    (By.XPATH, "//button[@type='submit']")
                ]
                
                for selector_type, selector_value in approve_selectors:
                    try:
                        approve_button = WebDriverWait(driver, 0.5).until(EC.element_to_be_clickable((selector_type, selector_value)))
                        logger.info("Found approval button using %s: %s", selector_type, selector_value)
                        break
                    except Exception:
                        continue
                
                if approve_button:
                    approve_button.click()
                    logger.info("OAuth authorization approved for %s", self.profile_name)
                else:
                    logger.warning("Could not find OAuth approval button for %s", self.profile_name)
                    driver.save_screenshot("/tmp/zerodha_oauth_debug.png")
                    logger.info("OAuth debug screenshot saved to /tmp/zerodha_oauth_debug.png")
                    
            except Exception as exc:
                logger.warning("OAuth approval failed for %s: %s", self.profile_name, exc)
            
            # Wait for webhook to capture token (more generous for slower approvals)
            logger.info("Waiting for OAuth redirect capture for %s", self.profile_name)
            token_data = server.wait_for_token(timeout=60)
            
            if token_data and token_data.get('request_token'):
                request_token = token_data['request_token']
                logger.info("✅ Request token captured successfully for %s", self.profile_name)
                return request_token
            else:
                logger.error("Failed to capture request token for %s", self.profile_name)
                return None
                
        except Exception as exc:
            logger.error("Automated browser login failed for %s: %s", self.profile_name, exc)
            return None
        finally:
            # Keep the shared driver alive across profiles for speed and stability
            if server:
                server.stop()
    
    def _generate_access_token(self, request_token: str) -> Optional[str]:
        """Generate access token from request token using kiteconnect."""
        try:
            # Import kiteconnect in the legacy project's venv
            python_code = f"""
import sys
import os

# kiteconnect is now installed in current venv

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
            
            # Use current venv (has kiteconnect installed)
            import sys
            current_python = sys.executable
            
            result = subprocess.run(
                [current_python, "-c", python_code],
                cwd=os.getcwd(),
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
    
    def _fully_automated_renewal(self) -> Optional[str]:
        """Perform fully automated token renewal."""
        try:
            # Generate login URL with webhook callback
            callback_url = "http://localhost:8080/callback"
            login_url = f"https://kite.zerodha.com/connect/login?api_key={self.api_key}&v=3&redirect_url={callback_url}"
            
            logger.info("Starting fully automated renewal for %s", self.profile_name)
            
            # Step 1: Automated browser login and token capture
            request_token = self._automated_browser_login(login_url)
            
            if not request_token:
                logger.error("Failed to capture request token for %s", self.profile_name)
                return None
            
            # Step 2: Generate access token
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
                
                logger.info("✅ Fully automated token renewal completed for %s", self.profile_name)
                return access_token
            else:
                logger.error("Failed to generate access token for %s", self.profile_name)
                return None
                
        except Exception as exc:
            logger.error("Fully automated token renewal failed for %s: %s", self.profile_name, exc)
            return None


def fully_automated_token_renewal(profiles_config: Dict[str, Any], credentials_config: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Perform fully automated token renewal for all profiles.
    
    Args:
        profiles_config: Dictionary containing profile configurations
        credentials_config: Dictionary containing login credentials and TOTP secrets
        
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
            
            # Get login credentials
            creds = credentials_config.get(profile_name.lower(), {})
            username = creds.get('username')
            password = creds.get('password')
            totp_secret = creds.get('totp_secret')
            
            if not all([username, password]):
                logger.warning("Missing login credentials for %s", profile_name)
                results[profile_name] = None
                continue
            
            # Attempt fully automated renewal
            logger.info("🤖 Starting fully automated renewal for %s", profile_name)
            auth_manager = FullyAutomatedKiteAuth(
                api_key, api_secret, profile_name, 
                username, password, totp_secret
            )
            
            access_token = auth_manager.get_valid_token()
            results[profile_name] = access_token
            
            if access_token:
                logger.info("✅ Fully automated renewal successful for %s", profile_name)
            else:
                logger.error("❌ Fully automated renewal failed for %s", profile_name)
            
            # Reduced delay between profiles
            time.sleep(1)
            
    except Exception as exc:
        logger.error("Fully automated token renewal failed: %s", exc)
    finally:
        # Cleanup the shared browser session after the batch
        _shutdown_shared_driver()

    return results


def load_credentials_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load credentials configuration from secure file.
    
    Expected format:
    {
        "huf": {
            "username": "your_account1_user_id",
            "password": "your_account1_password", 
            "totp_secret": "your_account1_totp_secret"
        },
        "account2": {
            "username": "your_account2_user_id",
            "password": "your_account2_password",
            "totp_secret": "your_account2_totp_secret"
        },
        "atul": {
            "username": "your_account3_user_id", 
            "password": "your_account3_password",
            "totp_secret": "your_account3_totp_secret"
        }
    }
    """
    if not config_path:
        config_path = os.path.expanduser("~/.kites/credentials.json")
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        else:
            logger.warning("Credentials config not found: %s", config_path)
            return {}
    except Exception as exc:
        logger.error("Error loading credentials config: %s", exc)
        return {}
