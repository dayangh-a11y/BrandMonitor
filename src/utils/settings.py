"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    browser_headless: bool = True
    browser_timeout_ms: int = 45_000
    browser_navigation_timeout_ms: int = 45_000
    max_retries: int = 3
    retry_wait_seconds: float = 2.0

    output_dir: Path = Path("output")
    log_dir: Path = Path("logs")
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/horse_racing"
    )
    database_echo: bool = False

    default_datasource: str = "asbdavani"


def get_settings() -> Settings:
    return Settings()
