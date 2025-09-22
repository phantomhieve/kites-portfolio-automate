from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, List

import yaml
from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


class EmailSettings(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    email_from: str
    email_to: str
    use_tls: bool = True


class ScheduleSettings(BaseModel):
    day_of_month: int = Field(default=15, ge=1, le=28)
    hour: int = Field(default=6, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    timezone: str = "UTC"


class KitesSettings(BaseModel):
    base_url: Optional[HttpUrl] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class AccountConfig(BaseModel):
    name: str
    base_url: Optional[HttpUrl] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    email_to: Optional[str] = None


class LegacySettings(BaseModel):
    enabled: bool = False
    project_path: Optional[str] = None
    module_name: str = "main"
    mode: str = "smart"  # smart|minimal|force_format|show_status|reset_state
    env_file: Optional[str] = None  # path to .env in legacy project


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    email: EmailSettings
    schedule: ScheduleSettings = ScheduleSettings()
    kites: KitesSettings = KitesSettings()
    accounts: List[AccountConfig] = []
    legacy: LegacySettings = LegacySettings()

    @staticmethod
    def _read_yaml_defaults(path: str) -> dict:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _apply_env_overrides(defaults: dict) -> dict:
        # Build a mutable copy
        cfg = {**defaults}
        cfg.setdefault("kites", {})
        cfg.setdefault("schedule", {})
        cfg.setdefault("email", {})
        cfg.setdefault("accounts", cfg.get("accounts", []))
        cfg.setdefault("legacy", cfg.get("legacy", {}))

        env = os.environ
        # Kites flat keys
        if env.get("KITES_BASE_URL") is not None:
            cfg["kites"]["base_url"] = env.get("KITES_BASE_URL")
        if env.get("KITES_USERNAME") is not None:
            cfg["kites"]["username"] = env.get("KITES_USERNAME")
        if env.get("KITES_PASSWORD") is not None:
            cfg["kites"]["password"] = env.get("KITES_PASSWORD")
        if env.get("KITES_API_KEY") is not None:
            cfg["kites"]["api_key"] = env.get("KITES_API_KEY")
        if env.get("KITES_CLIENT_ID") is not None:
            cfg["kites"]["client_id"] = env.get("KITES_CLIENT_ID")
        if env.get("KITES_CLIENT_SECRET") is not None:
            cfg["kites"]["client_secret"] = env.get("KITES_CLIENT_SECRET")

        # Schedule flat keys
        if env.get("SCHEDULE_DAY_OF_MONTH") is not None:
            cfg["schedule"]["day_of_month"] = int(env.get("SCHEDULE_DAY_OF_MONTH"))
        if env.get("SCHEDULE_HOUR") is not None:
            cfg["schedule"]["hour"] = int(env.get("SCHEDULE_HOUR"))
        if env.get("SCHEDULE_MINUTE") is not None:
            cfg["schedule"]["minute"] = int(env.get("SCHEDULE_MINUTE"))
        if env.get("TIMEZONE") is not None:
            cfg["schedule"]["timezone"] = env.get("TIMEZONE")

        # Email flat keys
        if env.get("SMTP_HOST") is not None:
            cfg["email"]["smtp_host"] = env.get("SMTP_HOST")
        if env.get("SMTP_PORT") is not None:
            cfg["email"]["smtp_port"] = int(env.get("SMTP_PORT"))
        if env.get("SMTP_USERNAME") is not None:
            cfg["email"]["smtp_username"] = env.get("SMTP_USERNAME")
        if env.get("SMTP_PASSWORD") is not None:
            cfg["email"]["smtp_password"] = env.get("SMTP_PASSWORD")
        if env.get("EMAIL_FROM") is not None:
            cfg["email"]["email_from"] = env.get("EMAIL_FROM")
        if env.get("EMAIL_TO") is not None:
            cfg["email"]["email_to"] = env.get("EMAIL_TO")
        if env.get("EMAIL_USE_TLS") is not None:
            v = env.get("EMAIL_USE_TLS").strip().lower()
            cfg["email"]["use_tls"] = v in ("1", "true", "yes", "on")

        # Legacy flat keys
        if env.get("LEGACY_ENABLED") is not None:
            v = env.get("LEGACY_ENABLED").strip().lower()
            cfg.setdefault("legacy", {})["enabled"] = v in ("1", "true", "yes", "on")
        if env.get("LEGACY_PROJECT_PATH") is not None:
            cfg.setdefault("legacy", {})["project_path"] = env.get("LEGACY_PROJECT_PATH")
        if env.get("LEGACY_MODULE_NAME") is not None:
            cfg.setdefault("legacy", {})["module_name"] = env.get("LEGACY_MODULE_NAME")
        if env.get("LEGACY_MODE") is not None:
            cfg.setdefault("legacy", {})["mode"] = env.get("LEGACY_MODE")
        if env.get("LEGACY_ENV_FILE") is not None:
            cfg.setdefault("legacy", {})["env_file"] = env.get("LEGACY_ENV_FILE")

        return cfg

    @staticmethod
    def _sanitize_config(cfg: dict) -> dict:
        # Convert empty base_url strings to None to satisfy HttpUrl validation
        if cfg.get("kites", {}).get("base_url", None) == "":
            cfg["kites"]["base_url"] = None
        accounts = cfg.get("accounts", []) or []
        for acc in accounts:
            if acc.get("base_url", None) == "":
                # remove or set None; pydantic treats None as Optional
                acc["base_url"] = None
        return cfg

    @classmethod
    def load(cls, defaults_path: str = "config/defaults.yaml") -> "AppSettings":
        load_dotenv(override=False)
        defaults = cls._read_yaml_defaults(defaults_path)
        merged = cls._apply_env_overrides(defaults)
        sanitized = cls._sanitize_config(merged)
        return cls.model_validate(sanitized)

    @classmethod
    def build_settings_for_account(cls, base: "AppSettings", account: AccountConfig) -> "AppSettings":
        # Merge base settings with account-specific overrides
        data = base.model_dump()
        # Override kites
        data["kites"] = {
            "base_url": str(account.base_url) if account.base_url else (str(base.kites.base_url) if base.kites.base_url else None),
            "username": account.username or base.kites.username,
            "password": account.password or base.kites.password,
            "api_key": account.api_key or base.kites.api_key,
            "client_id": account.client_id or base.kites.client_id,
            "client_secret": account.client_secret or base.kites.client_secret,
        }
        # Optional per-account email_to override
        if account.email_to:
            data["email"]["email_to"] = account.email_to
        return cls.model_validate(data)


@dataclass
class RuntimeContext:
    settings: AppSettings


