"""Unit tests for config loading and profiles credential resolution."""

import json
from pathlib import Path
from unittest.mock import patch

from src.kites_automate.config import AppSettings
from src.kites_automate.profiles import (
    get_spreadsheet_name,
    load_profiles_config,
    resolve_api_credentials,
)
from src.kites_automate.sheets.client import _resolve_credentials_path


def test_app_settings_load_without_yaml(monkeypatch):
    """Verify settings load cleanly with defaults without requiring defaults.yaml."""
    monkeypatch.setenv("TIMEZONE", "Asia/Kolkata")
    monkeypatch.setenv("SPREADSHEET_NAME", "TestPortfolio")

    settings = AppSettings.load()
    assert settings.schedule.timezone == "Asia/Kolkata"
    assert settings.schedule.hour == 6


def test_resolve_api_credentials_from_vault(tmp_path, monkeypatch):
    """Verify API credentials can be resolved directly from the ~/.kites vault."""
    fake_vault = tmp_path / "credentials.json"
    vault_data = {
        "accounts": {
            "test_user": {
                "api_key": "vault_api_key_123",
                "api_secret": "vault_api_secret_456",
            }
        }
    }
    fake_vault.write_text(json.dumps(vault_data), encoding="utf-8")

    with patch("src.kites_automate.profiles.load_raw_credentials_vault", return_value=vault_data):
        key, secret = resolve_api_credentials("test_user")
        assert key == "vault_api_key_123"
        assert secret == "vault_api_secret_456"


def test_resolve_api_credentials_from_env(monkeypatch):
    """Verify API credentials fallback to environment variables."""
    monkeypatch.setenv("demo_api_key", "env_key_abc")
    monkeypatch.setenv("demo_api_secret", "env_secret_xyz")

    with patch("src.kites_automate.profiles.load_raw_credentials_vault", return_value={}):
        profile = {"api_key_env": "demo_api_key", "api_secret_env": "demo_api_secret"}
        key, secret = resolve_api_credentials("demo", profile)
        assert key == "env_key_abc"
        assert secret == "env_secret_xyz"


def test_google_credentials_resolution(tmp_path, monkeypatch):
    """Verify GOOGLE_APPLICATION_CREDENTIALS takes precedence."""
    dummy_key = tmp_path / "google_creds.json"
    dummy_key.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(dummy_key))
    resolved = _resolve_credentials_path()
    assert resolved == str(dummy_key.resolve())
