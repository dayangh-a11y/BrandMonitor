"""Coverage-first policy and dual-date helpers."""

from __future__ import annotations

from datetime import date

from src.coverage.dates import dual_dates
from src.coverage.policy import BLOCKED_ENRICHMENT, preferred_source


def test_enrichment_blocked_list() -> None:
    assert "pedigree" in BLOCKED_ENRICHMENT
    assert "weather" in BLOCKED_ENRICHMENT
    assert "features" in BLOCKED_ENRICHMENT


def test_source_priority_asbdavani_over_mosharekat() -> None:
    assert preferred_source("asbdavani", "mosharekat") == "asbdavani"


def test_dual_dates() -> None:
    g, j = dual_dates(date(2024, 8, 6))
    assert g == date(2024, 8, 6)
    assert j == "1403/05/16"
