from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal


EnvironmentName = Literal["development", "staging", "production"]


@dataclass(frozen=True)
class Settings:
    """Production configuration profiles for BrandMonitor ops."""

    environment: EnvironmentName = "development"
    db_path: str = "data/brandmonitor.db"
    admin_token: str = "dev-admin-token"
    log_level: str = "INFO"
    log_json: bool = False
    crawl_max_attempts: int = 3
    crawl_default_mode: str = "incremental"
    scheduler_tick_seconds: int = 5
    metrics_enabled: bool = True
    backup_dir: str = "backups"
    api_debug: bool = True
    headless: bool = True
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


_PROFILES: dict[EnvironmentName, dict] = {
    "development": {
        "db_path": "data/brandmonitor.db",
        "admin_token": "dev-admin-token",
        "log_level": "DEBUG",
        "log_json": False,
        "api_debug": True,
        "metrics_enabled": True,
        "headless": True,
    },
    "staging": {
        "db_path": "data/staging_brandmonitor.db",
        "admin_token": "staging-admin-token",
        "log_level": "INFO",
        "log_json": True,
        "api_debug": False,
        "metrics_enabled": True,
        "headless": True,
        "crawl_max_attempts": 3,
    },
    "production": {
        "db_path": "data/prod_brandmonitor.db",
        "admin_token": "",  # must be set via ADMIN_TOKEN
        "log_level": "INFO",
        "log_json": True,
        "api_debug": False,
        "metrics_enabled": True,
        "headless": True,
        "crawl_max_attempts": 5,
        "scheduler_tick_seconds": 10,
    },
}


def resolve_environment(name: str | None = None) -> EnvironmentName:
    raw = (name or os.getenv("BRANDMONITOR_ENV") or os.getenv("ENV") or "development").strip().lower()
    if raw in ("dev", "development", "local"):
        return "development"
    if raw in ("stage", "staging"):
        return "staging"
    if raw in ("prod", "production"):
        return "production"
    raise ValueError(f"Unknown environment: {raw!r}. Use development|staging|production")


def load_settings(environment: str | None = None) -> Settings:
    env = resolve_environment(environment)
    base = dict(_PROFILES[env])
    settings = Settings(
        environment=env,
        db_path=os.getenv("DB_PATH", base["db_path"]),
        admin_token=os.getenv("ADMIN_TOKEN", base["admin_token"]),
        log_level=os.getenv("LOG_LEVEL", base["log_level"]),
        log_json=_as_bool(os.getenv("LOG_JSON"), default=bool(base["log_json"])),
        crawl_max_attempts=int(os.getenv("CRAWL_MAX_ATTEMPTS", base.get("crawl_max_attempts", 3))),
        crawl_default_mode=os.getenv("CRAWL_DEFAULT_MODE", "incremental"),
        scheduler_tick_seconds=int(
            os.getenv("SCHEDULER_TICK_SECONDS", base.get("scheduler_tick_seconds", 5))
        ),
        metrics_enabled=_as_bool(os.getenv("METRICS_ENABLED"), default=bool(base["metrics_enabled"])),
        backup_dir=os.getenv("BACKUP_DIR", "backups"),
        api_debug=_as_bool(os.getenv("API_DEBUG"), default=bool(base["api_debug"])),
        headless=_as_bool(os.getenv("HEADLESS"), default=bool(base["headless"])),
    )
    if settings.is_production and not settings.admin_token:
        raise ValueError("ADMIN_TOKEN is required in production")
    return settings


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
