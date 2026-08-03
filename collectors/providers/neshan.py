"""Neshan provider — interface + manual import (no fragile scraping)."""

from __future__ import annotations

from typing import Any

from collectors.providers.base import ProviderMode, UnifiedReview
from collectors.providers.import_adapter import ManualImportProvider


class NeshanProvider(ManualImportProvider):
    def __init__(self, *, dataset_dir: str | None = None, mode: ProviderMode = "manual_import"):
        super().__init__(
            "neshan",
            "نشان",
            dataset_dir=dataset_dir or "data/imports/neshan",
            mode=mode,
        )

    def collect(self, brand: str, **kwargs: Any) -> list[UnifiedReview]:
        rows = super().collect(brand, **kwargs)
        for r in rows:
            r.source = "neshan"
        return rows
