"""Helpers shared by raw ingest and feature pipelines."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def rate(numer: int, denom: int) -> float | None:
    if denom <= 0:
        return None
    return numer / denom
