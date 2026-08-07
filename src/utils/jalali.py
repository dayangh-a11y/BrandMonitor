"""Jalali (Shamsi) date helpers for Iranian horse racing.

Policy:
- Jalali is the default calendar for user-facing Iranian racing dates.
- Convert Jalali → Gregorian before querying the database (DB stores Gregorian).
- Display results in Jalali unless Gregorian is explicitly requested.
- Bare years like 1403 are Jalali years.
- Timezone for "today" / now: Asia/Tehran.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Iterable
from zoneinfo import ZoneInfo

import jdatetime

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

_JALALI_DATE_RE = re.compile(
    r"^(?P<y>\d{3,4})[/-](?P<m>\d{1,2})[/-](?P<d>\d{1,2})$"
)
_GREGORIAN_ISO_RE = re.compile(
    r"^(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})$"
)


def now_tehran() -> datetime:
    """Current datetime in Asia/Tehran."""
    return datetime.now(TEHRAN_TZ)


def today_jalali() -> jdatetime.date:
    """Today's Jalali date in Asia/Tehran."""
    return jdatetime.date.fromgregorian(date=now_tehran().date())


def today_gregorian() -> date:
    """Today's Gregorian date in Asia/Tehran (for DB filters)."""
    return now_tehran().date()


def jalali_year_bounds_gregorian(jalali_year: int) -> tuple[date, date]:
    """Gregorian [start, end] inclusive for a Jalali calendar year (e.g. 1403)."""
    start_j = jdatetime.date(jalali_year, 1, 1)
    end_day = 30 if start_j.isleap() else 29
    end_j = jdatetime.date(jalali_year, 12, end_day)
    return start_j.togregorian(), end_j.togregorian()


def parse_jalali_date(value: str | date | jdatetime.date | datetime | None) -> jdatetime.date | None:
    """Parse a Jalali date string (YYYY/MM/DD or YYYY-MM-DD) or pass through date-like values."""
    if value is None:
        return None
    if isinstance(value, jdatetime.date) and not isinstance(value, jdatetime.datetime):
        return value
    if isinstance(value, jdatetime.datetime):
        return value.date()
    if isinstance(value, datetime):
        return jdatetime.date.fromgregorian(date=value.date())
    if isinstance(value, date):
        # Ambiguous bare date: treat as Gregorian storage → Jalali view
        return jdatetime.date.fromgregorian(date=value)

    text = str(value).strip().replace(".", "/")
    m = _JALALI_DATE_RE.match(text)
    if not m:
        return None
    y, mo, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
    # Years < 1700 are treated as Jalali; ISO Gregorian years are not accepted here.
    if y >= 1700:
        return None
    try:
        return jdatetime.date(y, mo, d)
    except ValueError:
        return None


def parse_user_date(value: str | int | date | jdatetime.date | datetime | None) -> date | None:
    """Interpret user input as Jalali by default; return Gregorian ``date`` for DB queries.

    - ``1403`` → full Jalali year is not a single day (use ``jalali_year_bounds_gregorian``).
    - ``1403/05/15`` or ``1403-05-15`` → Jalali day → Gregorian.
    - Explicit ISO ``2024-08-07`` is accepted as Gregorian only when year ≥ 1700.
    """
    if value is None:
        return None
    if isinstance(value, int):
        # Year-only is not a single day
        raise ValueError(
            f"Jalali year {value} is not a single date; use jalali_year_bounds_gregorian({value})"
        )
    if isinstance(value, jdatetime.date) and not isinstance(value, jdatetime.datetime):
        return value.togregorian()
    if isinstance(value, jdatetime.datetime):
        return value.date().togregorian()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if re.fullmatch(r"\d{3,4}", text):
        raise ValueError(
            f"Jalali year {text} is not a single date; use jalali_year_bounds_gregorian({text})"
        )

    jd = parse_jalali_date(text)
    if jd is not None:
        return jd.togregorian()

    g = _GREGORIAN_ISO_RE.match(text)
    if g and int(g.group("y")) >= 1700:
        try:
            return date(int(g.group("y")), int(g.group("m")), int(g.group("d")))
        except ValueError:
            return None
    return None


def to_gregorian(value: str | date | jdatetime.date | datetime | None) -> date | None:
    """Convert Jalali (default) or Gregorian ISO input to Gregorian ``date`` for DB use."""
    if value is None:
        return None
    if isinstance(value, jdatetime.datetime):
        return value.date().togregorian()
    if isinstance(value, jdatetime.date):
        return value.togregorian()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        # Gregorian date object from DB / internals
        return value
    return parse_user_date(value)


def to_jalali(value: str | date | jdatetime.date | datetime | None) -> jdatetime.date | None:
    """Convert a Gregorian DB date (or Jalali input) to Jalali ``jdatetime.date``."""
    if value is None:
        return None
    if isinstance(value, jdatetime.date) and not isinstance(value, jdatetime.datetime):
        return value
    if isinstance(value, jdatetime.datetime):
        return value.date()
    if isinstance(value, datetime):
        return jdatetime.date.fromgregorian(date=value.date())
    if isinstance(value, date):
        return jdatetime.date.fromgregorian(date=value)
    text = str(value).strip()
    jd = parse_jalali_date(text)
    if jd is not None:
        return jd
    g = _GREGORIAN_ISO_RE.match(text.replace("/", "-"))
    if g and int(g.group("y")) >= 1700:
        try:
            return jdatetime.date.fromgregorian(
                date=date(int(g.group("y")), int(g.group("m")), int(g.group("d")))
            )
        except ValueError:
            return None
    return None


def format_jalali(
    value: str | date | jdatetime.date | datetime | None,
    *,
    sep: str = "/",
    with_weekday: bool = False,
) -> str | None:
    """Format a date for user display in Jalali (default UI calendar)."""
    jd = to_jalali(value)
    if jd is None:
        return None
    text = f"{jd.year}{sep}{jd.month:02d}{sep}{jd.day:02d}"
    if with_weekday:
        text = f"{jd.j_weekdays_fa[jd.weekday()]} {text}"
    return text


def format_gregorian(value: str | date | jdatetime.date | datetime | None) -> str | None:
    """Format as ISO Gregorian (only when explicitly requested)."""
    if value is None:
        return None
    if isinstance(value, jdatetime.date) and not isinstance(value, jdatetime.datetime):
        g = value.togregorian()
        return g.isoformat()
    if isinstance(value, jdatetime.datetime):
        return value.date().togregorian().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    g = to_gregorian(value)
    return g.isoformat() if g else None


def format_both(value: str | date | jdatetime.date | datetime | None) -> str | None:
    """Show Jalali and Gregorian together when both calendars must appear."""
    j = format_jalali(value)
    g = format_gregorian(value)
    if j is None or g is None:
        return j or g
    return f"{j} ({g})"


def query_date_range(
    start: str | date | jdatetime.date | None,
    end: str | date | jdatetime.date | None,
) -> tuple[date | None, date | None]:
    """Convert a user-facing (Jalali-default) range to Gregorian dates for SQL filters."""
    return to_gregorian(start), to_gregorian(end)


def query_jalali_year(jalali_year: int) -> tuple[date, date]:
    """Gregorian inclusive bounds for a Jalali year mentioned by the user (e.g. 1403)."""
    return jalali_year_bounds_gregorian(jalali_year)


def display_dates(values: Iterable[str | date | jdatetime.date | datetime | None]) -> list[str]:
    """Format many Gregorian DB dates for Jalali display."""
    out: list[str] = []
    for v in values:
        text = format_jalali(v)
        if text is not None:
            out.append(text)
    return out


def combine_tehran(d: date, t: time | None = None) -> datetime:
    """Attach Asia/Tehran tzinfo to a Gregorian date (and optional time)."""
    return datetime.combine(d, t or time.min, tzinfo=TEHRAN_TZ)
