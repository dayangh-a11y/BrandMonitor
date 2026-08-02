from __future__ import annotations

from ai.adapters.base import ModelAdapter
from ai.adapters.fake import FakeAdapter
from ai.adapters.openai_adapter import OpenAIAdapter
from ai.accounting import CostLedger
from core.config import Settings, load_settings


def build_adapter(settings: Settings | None = None) -> ModelAdapter:
    """
    Factory for analysis adapters.

    AI_PROVIDER=fake|openai (default: fake if no key, else openai when configured)
    """
    settings = settings or load_settings()
    provider = (settings.ai_provider or "fake").strip().lower()
    if provider == "fake":
        return FakeAdapter()
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        return OpenAIAdapter(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.openai_timeout_seconds,
            max_attempts=settings.openai_max_attempts,
            min_interval_seconds=settings.openai_min_interval_seconds,
            ledger=CostLedger(model=settings.openai_model),
        )
    raise ValueError(f"Unknown AI_PROVIDER={provider!r}; use fake|openai")
