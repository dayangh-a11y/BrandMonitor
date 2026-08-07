"""Jalali-default date helpers for Iranian horse racing."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import jdatetime
import pytest

from src.utils.jalali import (
    TEHRAN_TZ,
    combine_tehran,
    display_dates,
    format_both,
    format_gregorian,
    format_jalali,
    jalali_year_bounds_gregorian,
    parse_user_date,
    query_date_range,
    query_jalali_year,
    to_gregorian,
    to_jalali,
)


def test_tehran_timezone_constant() -> None:
    assert TEHRAN_TZ == ZoneInfo("Asia/Tehran")


def test_jalali_string_to_gregorian_for_db() -> None:
    # 1403/05/16 ≈ 2024-08-06
    assert parse_user_date("1403/05/16") == date(2024, 8, 6)
    assert to_gregorian("1403-05-16") == date(2024, 8, 6)


def test_bare_year_is_jalali_not_single_day() -> None:
    with pytest.raises(ValueError, match="Jalali year"):
        parse_user_date(1403)
    with pytest.raises(ValueError, match="Jalali year"):
        parse_user_date("1403")

    start, end = query_jalali_year(1403)
    assert start == date(2024, 3, 20)
    assert end == date(2025, 3, 20)
    assert jalali_year_bounds_gregorian(1403) == (start, end)


def test_display_defaults_to_jalali() -> None:
    g = date(2024, 8, 6)
    assert format_jalali(g) == "1403/05/16"
    assert format_gregorian(g) == "2024-08-06"
    assert format_both(g) == "1403/05/16 (2024-08-06)"
    assert display_dates([g, date(2025, 2, 28)]) == ["1403/05/16", "1403/12/10"]


def test_explicit_iso_gregorian_accepted_for_queries() -> None:
    assert parse_user_date("2024-08-06") == date(2024, 8, 6)


def test_query_date_range_jalali_inputs() -> None:
    start, end = query_date_range("1403/01/01", "1403/12/29")
    assert start == date(2024, 3, 20)
    # 1403 is leap → 12/30 exists; 12/29 is day before
    assert end == jdatetime.date(1403, 12, 29).togregorian()


def test_roundtrip_jdatetime() -> None:
    jd = jdatetime.date(1402, 11, 18)
    assert to_gregorian(jd) == jd.togregorian()
    assert to_jalali(jd.togregorian()) == jd


def test_combine_tehran() -> None:
    dt = combine_tehran(date(2024, 8, 6))
    assert dt.tzinfo == TEHRAN_TZ
    assert isinstance(dt, datetime)
