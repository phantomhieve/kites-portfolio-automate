import importlib
import logging
import os
import sys
from contextlib import contextmanager
from typing import Optional

from .config import RuntimeContext

logger = logging.getLogger(__name__)


@contextmanager
def _pushd(path: str):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _ensure_path_on_sys(path: str):
    if path not in sys.path:
        sys.path.insert(0, path)


def run_legacy(ctx: RuntimeContext) -> None:
    legacy = ctx.settings.legacy
    if not legacy or not legacy.enabled:
        logger.info("Legacy mode disabled")
        return

    project_path = legacy.project_path or "/home/phantomhive/kites-automate"
    module_name = legacy.module_name or "main"
    mode = (legacy.mode or "smart").lower()

    _ensure_path_on_sys(project_path)

    # Optionally load env file in legacy project
    if legacy.env_file and os.path.exists(legacy.env_file):
        try:
            from dotenv import load_dotenv  # type: ignore
            load_dotenv(dotenv_path=legacy.env_file, override=False)
        except Exception as exc:
            logger.warning("Could not load legacy env file: %s", exc)

    with _pushd(project_path):
        mod = importlib.import_module(module_name)
        if mode == "smart":
            fn = getattr(mod, "smart_update")
            fn()
        elif mode == "minimal":
            fn = getattr(mod, "minimal_update")
            fn()
        elif mode == "force_format":
            # Some flows prompt; stub input to "y"
            import builtins
            old_input = builtins.input
            try:
                builtins.input = lambda *_: "y"  # type: ignore
                fn = getattr(mod, "force_format")
                fn()
            finally:
                builtins.input = old_input
        elif mode == "show_status":
            fn = getattr(mod, "show_status")
            fn()
        elif mode == "reset_state":
            import builtins
            old_input = builtins.input
            try:
                builtins.input = lambda *_: "y"  # type: ignore
                fn = getattr(mod, "reset_formatting_state")
                fn()
            finally:
                builtins.input = old_input
        else:
            raise ValueError(f"Unknown legacy mode: {mode}")

    logger.info("Legacy run completed (mode=%s)", mode)
