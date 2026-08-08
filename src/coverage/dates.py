"""Dual-calendar helpers: Gregorian for DB queries, Jalali for display/storage mirror."""

from __future__ import annotations

from datetime import date

from src.utils.jalali import format_jalali, to_gregorian, to_jalali


def gregorian_for_storage(value: str | date | None) -> date | None:
    """Normalize user/source date to Gregorian ``date`` for internal storage/queries."""
    return to_gregorian(value)


def jalali_string(value: str | date | None, *, sep: str = "/") -> str | None:
    """Jalali display/storage string YYYY/MM/DD."""
    return format_jalali(value, sep=sep)


def dual_dates(value: str | date | None) -> tuple[date | None, str | None]:
    """Return (gregorian_date, jalali_str) for provenance columns."""
    g = gregorian_for_storage(value)
    if g is None:
        # value might already be gregorian date-like string that failed jalali parse
        j = to_jalali(value)
        if j is not None:
            g = j.togregorian()
            return g, format_jalali(g)
        return None, None
    return g, format_jalali(g)
