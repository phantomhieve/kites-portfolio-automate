import logging
import os
import subprocess
import sys
from typing import Optional

from .config import RuntimeContext

logger = logging.getLogger(__name__)


def run_legacy(ctx: RuntimeContext) -> None:
    legacy = ctx.settings.legacy
    if not legacy or not legacy.enabled:
        logger.info("Legacy mode disabled")
        return

    project_path = legacy.project_path or "/home/phantomhive/kites-automate"
    module_name = legacy.module_name or "main"
    mode = (legacy.mode or "smart").lower()

    if not os.path.exists(project_path):
        logger.error("Legacy project path does not exist: %s", project_path)
        return

    # Look for venv in legacy project
    venv_python = os.path.join(project_path, ".venv", "bin", "python")
    if not os.path.exists(venv_python):
        venv_python = "python3"  # fallback to system python
        logger.warning("Legacy venv not found, using system python")

    # Set up environment
    env = os.environ.copy()
    if legacy.env_file and os.path.exists(legacy.env_file):
        # Load env vars from legacy .env file
        try:
            from dotenv import dotenv_values
            env_vars = dotenv_values(legacy.env_file)
            for key, value in env_vars.items():
                if key and value:
                    env[key] = value
        except Exception as exc:
            logger.warning("Could not load legacy env file: %s", exc)

    # Map mode to function call
    function_map = {
        "smart": "smart_update()",
        "minimal": "minimal_update()",
        "force_format": "force_format()",
        "show_status": "show_status()",
        "reset_state": "reset_formatting_state()"
    }
    
    if mode not in function_map:
        raise ValueError(f"Unknown legacy mode: {mode}")

    function_call = function_map[mode]
    
    # For functions that need input stubbing, prepare the input
    python_code = f"""
import sys
sys.path.insert(0, '{project_path}')

# Stub input for interactive functions
if '{mode}' in ['force_format', 'reset_state']:
    import builtins
    builtins.input = lambda *_: 'y'

import {module_name}
{module_name}.{function_call}
"""

    try:
        result = subprocess.run(
            [venv_python, "-c", python_code],
            cwd=project_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            logger.error("Legacy run failed with code %d: %s", result.returncode, result.stderr)
            raise RuntimeError(f"Legacy execution failed: {result.stderr}")
        
        if result.stdout:
            # Log legacy output at info level
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    logger.info("Legacy: %s", line.strip())
                    
        logger.info("Legacy run completed (mode=%s)", mode)
        
    except subprocess.TimeoutExpired:
        logger.error("Legacy run timed out after 5 minutes")
        raise RuntimeError("Legacy execution timed out")
    except Exception as exc:
        logger.error("Legacy run failed: %s", exc)
        raise
