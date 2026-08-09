"""Telegram bot configuration (env only — never hardcode tokens)."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramBotSettings(BaseSettings):
    """Reads TELEGRAM_BOT_TOKEN, API_BASE_URL, etc. from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    telegram_bot_token: str = ""
    api_base_url: str = "http://localhost:8000"
    request_timeout_seconds: float = 10.0
    telegram_admin_ids: str = ""
    telegram_session_ttl_seconds: int = 1800
    telegram_default_price_per_combination: int = 10_000
    telegram_races_page_size: int = 10

    @field_validator("api_base_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return (v or "").rstrip("/")

    def admin_id_set(self) -> set[int]:
        out: set[int] = set()
        for part in self.telegram_admin_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.add(int(part))
            except ValueError:
                continue
        return out

    def require_token(self) -> str:
        token = (self.telegram_bot_token or "").strip()
        if not token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is missing. Set it in the environment or .env "
                "(never commit the real token)."
            )
        return token


def get_telegram_settings() -> TelegramBotSettings:
    return TelegramBotSettings()
