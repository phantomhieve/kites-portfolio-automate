import importlib
import logging
import os
import sys
from typing import Optional, Tuple, Callable

from .config import RuntimeContext, AccountConfig

logger = logging.getLogger(__name__)


class BaseKitesAdapter:
    def authenticate(self, ctx: RuntimeContext) -> Tuple[Optional[str], Optional[int]]:
        raise NotImplementedError

    def update_portfolio(self, ctx: RuntimeContext, token: str, account: Optional[AccountConfig] = None) -> None:
        raise NotImplementedError


class LocalKitesAdapter(BaseKitesAdapter):
    def __init__(self, module_name: str, client_class: str) -> None:
        self.module_name = module_name
        self.client_class = client_class
        self._client = None

    def _ensure_client(self, ctx: RuntimeContext):
        if self._client is not None:
            return self._client
        mod = importlib.import_module(self.module_name)
        client_cls = getattr(mod, self.client_class)
        
        # Special handling for PortfolioManager which requires SheetManager
        if self.client_class == "PortfolioManager":
            try:
                # Import SheetManager from the same module
                sheet_manager_cls = getattr(mod, "SheetManager")
                # Create SheetManager with credentials file path
                credentials_path = os.path.join(ctx.settings.legacy.project_path or "/Users/phantomhive/Desktop/Atul/kites", "credentials.json")
                sheet_manager = sheet_manager_cls(credentials_path)
                # Create PortfolioManager with SheetManager
                self._client = client_cls(sheet_manager)
                return self._client
            except Exception as exc:
                logger.warning("Failed to create PortfolioManager with SheetManager: %s", exc)
        
        # Fallback to original logic for other client types
        try:
            self._client = client_cls(
                base_url=str(ctx.settings.kites.base_url) if ctx.settings.kites.base_url else None
            )
        except TypeError:
            self._client = client_cls()
        return self._client

    def authenticate(self, ctx: RuntimeContext) -> Tuple[Optional[str], Optional[int]]:
        try:
            client = self._ensure_client(ctx)
            # Expected to return (access_token, expires_in_seconds)
            if ctx.settings.kites.api_key:
                return client.authenticate_with_api_key(ctx.settings.kites.api_key)
            if ctx.settings.kites.client_id and ctx.settings.kites.client_secret:
                return client.authenticate_client_credentials(ctx.settings.kites.client_id, ctx.settings.kites.client_secret)
            if ctx.settings.kites.username and ctx.settings.kites.password:
                return client.authenticate_password(ctx.settings.kites.username, ctx.settings.kites.password)
        except Exception as exc:
            logger.warning("Local kites adapter auth failed: %s", exc)
        return None, None

    def update_portfolio(self, ctx: RuntimeContext, token: str, account: Optional[AccountConfig] = None) -> None:
        try:
            client = self._ensure_client(ctx)
            
            # Special handling for PortfolioManager which has different method signature
            if self.client_class == "PortfolioManager":
                logger.info("Updating portfolio using PortfolioManager with Kite API")
                
                # Get the legacy project path for credentials and profiles
                legacy_path = ctx.settings.legacy.project_path or "/Users/phantomhive/Desktop/Atul/kites"
                credentials_path = os.path.join(legacy_path, "credentials.json")
                profiles_path = os.path.join(legacy_path, "profiles.json")
                
                # Load profiles to get account information
                import json
                with open(profiles_path, 'r') as f:
                    profiles = json.load(f)
                
                # Find the profile for the current account
                current_account = None
                account_name = account.name if account else "default"
                for profile in profiles.get("profiles", []):
                    if profile["profile_name"].lower() == account_name.lower():
                        current_account = profile
                        break
                
                if not current_account:
                    logger.warning("No profile found for account: %s", account_name)
                    return
                
                # Get API credentials from environment variables
                api_key = os.getenv(current_account['api_key_env'])
                api_secret = os.getenv(current_account['api_secret_env'])
                
                if not api_key or not api_secret:
                    logger.warning("Missing API credentials for %s (env vars: %s, %s)", 
                                 account_name, current_account['api_key_env'], current_account['api_secret_env'])
                    return
                
                # Import required classes
                mod = importlib.import_module(self.module_name)
                KiteAuthManager = getattr(mod, "KiteAuthManager")
                SheetManager = getattr(mod, "SheetManager")
                
                # Create SheetManager
                sheet_manager = SheetManager(credentials_path)
                
                # Create KiteAuthManager and get client
                # Use the token file name that matches the automated token generation
                # The automated auth creates tokens as {profile_name}_access_token.txt (preserving case from profiles.json)
                # So "HUF" becomes "Account1_access_token.txt", not "huf_access_token.txt"
                token_file = f"{current_account['profile_name']}_access_token.txt"
                
                # Debug: Check what token files actually exist
                kites_dir = os.path.expanduser("~/.kites")
                if os.path.exists(kites_dir):
                    all_files = os.listdir(kites_dir)
                    logger.info("Files in ~/.kites/: %s", all_files)
                    logger.info("Looking for token file: %s", token_file)
                else:
                    logger.warning("~/.kites directory does not exist")
                
                # Instead of using KiteAuthManager (which might fail validation),
                # use the token that was already validated by the kites-automate system
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=api_key)
                
                # Get the validated token from the kites-automate token system
                # Use dynamic import to avoid relative import issues
                import sys
                import importlib
                token_rotator_module = importlib.import_module('kites_automate.auth.token_rotator')
                get_valid_token = getattr(token_rotator_module, 'get_valid_token')
                
                valid_token = get_valid_token(ctx, account)
                if not valid_token:
                    logger.error("No valid token available for %s", account_name)
                    return
                
                # Set the token directly (bypassing KiteAuthManager validation)
                kite.set_access_token(valid_token)
                logger.info("Using validated token for %s (bypassing KiteAuthManager)", account_name)
                
                # Get spreadsheet and worksheet
                spreadsheet_name = profiles.get("settings", {}).get("spreadsheet_name", "Portfolio")
                spreadsheet = sheet_manager.get_or_create_sheet(spreadsheet_name)
                worksheet = sheet_manager.get_or_create_worksheet(spreadsheet, current_account["profile_name"])
                
                # Update portfolio using PortfolioManager
                summary = client.update_portfolio_sheet(
                    worksheet,
                    kite.holdings(),
                    kite.mf_holdings(),
                    force_formatting=False
                )
                
                logger.info("Portfolio updated successfully using PortfolioManager")
                return
            
            # Try the standard update_portfolio method for other client types
            if hasattr(client, 'update_portfolio'):
                client.update_portfolio(token=token)
            else:
                logger.warning("Client %s has no update_portfolio method", self.client_class)
        except Exception as exc:
            logger.warning("Local kites adapter portfolio update failed: %s", exc)


class RestKitesAdapter(BaseKitesAdapter):
    def authenticate(self, ctx: RuntimeContext) -> Tuple[Optional[str], Optional[int]]:
        logger.info("REST adapter not implemented; provide local client via KITES_LOCAL_PATH")
        return None, None

    def update_portfolio(self, ctx: RuntimeContext, token: str, account: Optional[AccountConfig] = None) -> None:
        logger.info("REST adapter not implemented; skipping portfolio update")


def get_adapter(ctx: RuntimeContext) -> BaseKitesAdapter:
    # Try to use local codebase if provided
    local_path = os.environ.get("KITES_LOCAL_PATH", "/Users/phantomhive/Desktop/Atul/kites")
    module_name = os.environ.get("KITES_LOCAL_MODULE", "kites_client")
    client_class = os.environ.get("KITES_LOCAL_CLIENT_CLASS", "KitesClient")
    factory_spec = os.environ.get("KITES_LOCAL_FACTORY")  # format: module:function

    if os.path.isdir(local_path) and local_path not in sys.path:
        sys.path.insert(0, local_path)

    # If a factory is provided, prefer it to construct the client with custom deps
    if factory_spec:
        try:
            factory_module, factory_func = factory_spec.split(":", 1)
            mod = importlib.import_module(factory_module)
            create_client: Callable[[], object] = getattr(mod, factory_func)

            client_instance = create_client()

            class GenericLocalAdapter(BaseKitesAdapter):
                def __init__(self, client_obj: object) -> None:
                    self.client = client_obj

                def authenticate(self, ctx: RuntimeContext) -> Tuple[Optional[str], Optional[int]]:
                    # Try the same auth patterns as LocalKitesAdapter against the provided client
                    try:
                        if ctx.settings.kites.api_key and hasattr(self.client, "authenticate_with_api_key"):
                            return getattr(self.client, "authenticate_with_api_key")(ctx.settings.kites.api_key)
                        if ctx.settings.kites.client_id and ctx.settings.kites.client_secret and hasattr(self.client, "authenticate_client_credentials"):
                            return getattr(self.client, "authenticate_client_credentials")(ctx.settings.kites.client_id, ctx.settings.kites.client_secret)
                        if ctx.settings.kites.username and ctx.settings.kites.password and hasattr(self.client, "authenticate_password"):
                            return getattr(self.client, "authenticate_password")(ctx.settings.kites.username, ctx.settings.kites.password)
                    except Exception as exc2:
                        logger.warning("Generic local auth failed: %s", exc2)
                    return None, None

                def update_portfolio(self, ctx: RuntimeContext, token: str, account: Optional[AccountConfig] = None) -> None:
                    try:
                        if hasattr(self.client, "update_portfolio"):
                            return getattr(self.client, "update_portfolio")(token=token)
                        logger.warning("Client instance has no update_portfolio method; skipping")
                    except Exception as exc2:
                        logger.warning("Generic local portfolio update failed: %s", exc2)

            logger.info("Using LocalKitesAdapter via factory (%s)", factory_spec)
            return GenericLocalAdapter(client_instance)
        except Exception as exc:
            logger.warning("Factory load failed (%s): %s", factory_spec, exc)

    # Class-based construction fallback
    try:
        importlib.import_module(module_name)
        logger.info("Using LocalKitesAdapter (%s.%s)", module_name, client_class)
        return LocalKitesAdapter(module_name=module_name, client_class=client_class)
    except Exception as exc:
        logger.warning(
            "Failed to load local client (path=%s, module=%s, class=%s): %s",
            local_path,
            module_name,
            client_class,
            exc,
        )
        logger.info("Falling back to RestKitesAdapter")
        return RestKitesAdapter()
