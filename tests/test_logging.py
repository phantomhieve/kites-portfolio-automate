"""Tests for secret redaction logging filter."""

import logging
from src.kites_automate.logging_setup import SecretRedactingFilter


def test_secret_redacting_filter():
    filt = SecretRedactingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Login with password='supersecret123' and api_key=xyz9876543210",
        args=(),
        exc_info=None,
    )

    filt.filter(record)
    assert "supersecret123" not in record.msg
    assert "xyz9876543210" not in record.msg
    assert "[REDACTED]" in record.msg


def test_bearer_token_redacted():
    filt = SecretRedactingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Header Authorization: Bearer abcdef1234567890xyz",
        args=(),
        exc_info=None,
    )

    filt.filter(record)
    assert "abcdef1234567890xyz" not in record.msg
    assert "[REDACTED]" in record.msg
