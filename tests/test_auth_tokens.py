"""Unit tests for token renewal and cutoff logic."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from src.kites_automate.auth.token_rotator import Token, _read_automated_token


def test_token_expired_property():
    """Verify Token expiration detection."""
    t_expired = Token(access_token="tok1", expires_at=100.0)
    assert t_expired.is_expired is True

    t_valid = Token(access_token="tok2", expires_at=datetime.now().timestamp() + 3600)
    assert t_valid.is_expired is False


def test_automated_token_zerodha_cutoff(tmp_path, monkeypatch):
    """Verify tokens created before 06:00 AM IST are treated as expired on current day."""
    ist = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(ist)
    yesterday_ist = now_ist - timedelta(days=1)

    fake_kites = tmp_path / ".kites"
    fake_kites.mkdir()
    token_file = fake_kites / "test_access_token.txt"

    token_data = {
        "access_token": "valid_looking_token_32_chars_123",
        "created_at": yesterday_ist.isoformat(),
        "expires_at": (now_ist + timedelta(hours=10)).isoformat(),
    }
    import json
    token_file.write_text(json.dumps(token_data), encoding="utf-8")

    monkeypatch.setenv("HOME", str(tmp_path))

    # If now is past 06:00 AM, yesterday's token should be rejected
    if now_ist.hour >= 6:
        tok = _read_automated_token("test")
        assert tok is None
