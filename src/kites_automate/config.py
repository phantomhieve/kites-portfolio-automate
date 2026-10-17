"""
Application Configuration & Settings

Loads and validates settings using Pydantic, deriving values from .env
and automatically discovering configured accounts from profiles.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseModel):
    smtp_host: Optional[str] = ""
    smtp_port: int = 587
    smtp_username: Optional[str] = ""
    smtp_password: Optional[str] = ""
    email_from: Optional[str] = ""
    email_to: Optional[str] = ""
    use_tls: bool = True


class ScheduleSettings(BaseModel):
    day_of_month: int = Field(default=15, ge=1, le=28)
    hour: int = Field(default=21, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    timezone: str = "Asia/Kolkata"


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


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    email: EmailSettings = EmailSettings()
    schedule: ScheduleSettings = ScheduleSettings()
    kites: KitesSettings = KitesSettings()
    accounts: List[AccountConfig] = []

    @staticmethod
    def _apply_env_overrides(base_cfg: dict) -> dict:
        cfg = {**base_cfg}
        cfg.setdefault("kites", {})
        cfg.setdefault("schedule", {})
        cfg.setdefault("email", {})
        cfg.setdefault("accounts", cfg.get("accounts", []))

        env = os.environ
        # Kites keys
        if env.get("KITES_BASE_URL"):
            cfg["kites"]["base_url"] = env.get("KITES_BASE_URL")
        if env.get("KITES_API_KEY"):
            cfg["kites"]["api_key"] = env.get("KITES_API_KEY")

        # Schedule keys
        if env.get("SCHEDULE_DAY_OF_MONTH"):
            cfg["schedule"]["day_of_month"] = int(env.get("SCHEDULE_DAY_OF_MONTH"))
        if env.get("SCHEDULE_HOUR"):
            cfg["schedule"]["hour"] = int(env.get("SCHEDULE_HOUR"))
        if env.get("SCHEDULE_MINUTE"):
            cfg["schedule"]["minute"] = int(env.get("SCHEDULE_MINUTE"))
        if env.get("TIMEZONE"):
            cfg["schedule"]["timezone"] = env.get("TIMEZONE")

        # Email keys
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
            v = str(env.get("EMAIL_USE_TLS")).strip().lower()
            cfg["email"]["use_tls"] = v in ("1", "true", "yes", "on")

        return cfg

    @staticmethod
    def _sanitize_config(cfg: dict) -> dict:
        if cfg.get("kites", {}).get("base_url") == "":
            cfg["kites"]["base_url"] = None
        accounts = cfg.get("accounts", []) or []
        for acc in accounts:
            if acc.get("base_url") == "":
                acc["base_url"] = None
        return cfg

    @classmethod
    def load(cls, defaults_path: Optional[str] = None) -> "AppSettings":
        load_dotenv(override=False)
        merged = cls._apply_env_overrides({})

        # Automatically discover accounts from profiles if not manually passed
        if not merged.get("accounts"):
            from .profiles import load_profiles_config
            profiles_cfg = load_profiles_config()
            merged["accounts"] = [
                {"name": p["profile_name"]}
                for p in profiles_cfg.get("profiles", [])
                if p.get("profile_name")
            ]

        sanitized = cls._sanitize_config(merged)
        return cls.model_validate(sanitized)

    @classmethod
    def build_settings_for_account(cls, base: "AppSettings", account: AccountConfig) -> "AppSettings":
        data = base.model_dump()
        data["kites"] = {
            "base_url": str(account.base_url) if account.base_url else (str(base.kites.base_url) if base.kites.base_url else None),
            "username": account.username or base.kites.username,
            "password": account.password or base.kites.password,
            "api_key": account.api_key or base.kites.api_key,
            "client_id": account.client_id or base.kites.client_id,
            "client_secret": account.client_secret or base.kites.client_secret,
        }
        if account.email_to:
            data["email"]["email_to"] = account.email_to
        return cls.model_validate(data)


@dataclass
class RuntimeContext:
    settings: AppSettings
