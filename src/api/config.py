"""API settings (CORS + freeze-backed dataset paths)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.utils.settings import Settings as AppSettings


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_title: str = "Horse Racing Prediction API"
    api_version: str = "0.1.0"
    # Comma-separated origins; use "*" only for local/dev.
    api_cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000")
    api_cors_allow_credentials: bool = False

    prediction_dataset_path: Path = Path(
        "data/prediction_foundation/datasets/observations.jsonl.gz"
    )
    prediction_freeze_path: Path = Path("data/prediction_foundation/freezes/LATEST.json")
    # When true, refuse to load a dataset whose sha256 != freeze metadata.
    prediction_verify_freeze: bool = True
    prediction_default_baseline: str = "A"

    def cors_origins_list(self) -> list[str]:
        raw = [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]
        return raw or ["http://localhost:3000"]


def get_api_settings() -> APISettings:
    return APISettings()


def get_app_settings() -> AppSettings:
    return AppSettings()
