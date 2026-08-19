"""Time eligibility for live prediction (future races only)."""

from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_UPCOMING_DAYS = 7


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_eligible_for_prediction(
    scheduled_start: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    """A race is eligible only when ``scheduled_start > current_time``.

    Missing scheduled time is never treated as safely future.
    """
    if scheduled_start is None:
        return False
    now_utc = ensure_utc(now or utc_now())
    start = ensure_utc(scheduled_start)
    return start > now_utc


def is_within_upcoming_window(
    scheduled_start: datetime,
    *,
    now: datetime | None = None,
    days: int = DEFAULT_UPCOMING_DAYS,
) -> bool:
    """True when start is in the future and within ``days`` from now."""
    if days < 0:
        return False
    now_utc = ensure_utc(now or utc_now())
    start = ensure_utc(scheduled_start)
    if start <= now_utc:
        return False
    delta = start - now_utc
    return delta.total_seconds() <= float(days) * 86400.0
