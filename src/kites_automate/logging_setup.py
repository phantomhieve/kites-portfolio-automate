"""
Logging configuration with automatic secret redaction.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Pattern

# Patterns that match potential secrets in log strings
REDACT_PATTERNS: list[Pattern[str]] = [
    re.compile(r"(?i)(api[_-]?secret|api[_-]?key|password|totp[_-]?secret|access[_-]?token|refresh[_-]?token)\s*[:=]\s*['\"]?([^\s'\",&]+)", re.IGNORECASE),
    re.compile(r"(?i)(request_token=)([a-zA-Z0-9]+)", re.IGNORECASE),
    re.compile(r"(?i)(Bearer\s+)([a-zA-Z0-9_\-\.]{15,})", re.IGNORECASE),
]


class SecretRedactingFilter(logging.Filter):
    """Logging filter that scrubs sensitive credentials from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self._redact(str(a)) if isinstance(a, str) else a for a in record.args)
        return True

    @staticmethod
    def _redact(text: str) -> str:
        for pattern in REDACT_PATTERNS:
            text = pattern.sub(r"\1=[REDACTED]", text)
        return text


def setup_logging(level: int = logging.INFO) -> None:
    """Set up root logger with formatting and secret redaction."""
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    if not root.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SecretRedactingFilter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.addFilter(SecretRedactingFilter())

    # Suppress verbose third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
