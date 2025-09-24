import importlib
import logging
import os
import sys
from typing import Optional, Tuple, Callable

from .config import RuntimeContext

logger = logging.getLogger(__name__)


class BaseKitesAdapter:
    def authenticate(self, ctx: RuntimeContext) -> Tuple[Optional[str], Optional[int]]:
        raise NotImplementedError

    def update_portfolio(self, ctx: RuntimeContext, token: str) -> None:
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
        # Some local clients don't accept base_url; try with, then without
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

    def update_portfolio(self, ctx: RuntimeContext, token: str) -> None:
        try:
            client = self._ensure_client(ctx)
            client.update_portfolio(token=token)
        except Exception as exc:
            logger.warning("Local kites adapter portfolio update failed: %s", exc)


class RestKitesAdapter(BaseKitesAdapter):
    def authenticate(self, ctx: RuntimeContext) -> Tuple[Optional[str], Optional[int]]:
        logger.info("REST adapter not implemented; provide local client via KITES_LOCAL_PATH")
        return None, None

    def update_portfolio(self, ctx: RuntimeContext, token: str) -> None:
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

                def update_portfolio(self, ctx: RuntimeContext, token: str) -> None:
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
