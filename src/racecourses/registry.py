"""
Racecourse registry — expandable without database redesign.

Enable/disable which tracks the crawler collects via settings
(`CRAWL_ALLOWED_RACECOURSES`). Codes are stable; aliases absorb
Persian spelling variants from the source site.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Racecourse:
    """Canonical racecourse identity."""

    code: str
    name_en: str
    name_fa: str
    aliases: tuple[str, ...] = ()
    # Approximate track/city coordinates for historical weather joins (WGS84).
    latitude: float | None = None
    longitude: float | None = None
    timezone: str = "Asia/Tehran"


# Default project scope: Golestan triad only (not nationwide).
DEFAULT_ALLOWED_CODES: tuple[str, ...] = (
    "gonbad-kavous",
    "aq-qala",
    "bandar-torkaman",
)

RACECOURSES: tuple[Racecourse, ...] = (
    Racecourse(
        code="gonbad-kavous",
        name_en="Gonbad Kavous",
        name_fa="گنبدکاووس",
        aliases=(
            "گنبدکاووس",
            "گنبد کاووس",
            "گنبدكاووس",
            "gonbad kavous",
            "gonbad-kavous",
            "gonbad",
        ),
        latitude=37.2500,
        longitude=55.1672,
        timezone="Asia/Tehran",
    ),
    Racecourse(
        code="aq-qala",
        name_en="Aq Qala",
        name_fa="آق قلا",
        aliases=(
            "آق قلا",
            "آق‌ قلا",
            "آق‌قلا",
            "آققلعه",
            "آق قلعه",
            "اق قلا",
            "aq qala",
            "aq-qala",
            "aqqala",
        ),
        latitude=37.0139,
        longitude=54.4550,
        timezone="Asia/Tehran",
    ),
    Racecourse(
        code="bandar-torkaman",
        name_en="Bandar Torkaman",
        name_fa="بندرترکمن",
        aliases=(
            "بندرترکمن",
            "بندر ترکمن",
            "بندرتركمن",
            "bandar torkaman",
            "bandar-torkaman",
            "torkaman",
        ),
        latitude=36.9017,
        longitude=54.0739,
        timezone="Asia/Tehran",
    ),
)

_BY_CODE: dict[str, Racecourse] = {r.code: r for r in RACECOURSES}


def normalize_track_key(value: str | None) -> str:
    """Normalize a track label for alias matching (ZWNJ/spaces/case)."""
    if not value:
        return ""
    text = str(value)
    text = text.replace("\u200c", "")  # ZWNJ
    text = text.replace("\u200d", "")
    text = text.replace("ك", "ک").replace("ي", "ی")
    text = re.sub(r"\s+", "", text)
    return text.casefold().strip()


def _alias_index() -> dict[str, Racecourse]:
    index: dict[str, Racecourse] = {}
    for course in RACECOURSES:
        keys = {normalize_track_key(course.code), normalize_track_key(course.name_fa)}
        keys.add(normalize_track_key(course.name_en))
        for alias in course.aliases:
            keys.add(normalize_track_key(alias))
        for key in keys:
            if key:
                index[key] = course
    return index


_ALIAS_INDEX = _alias_index()


def get_racecourse(code: str) -> Racecourse | None:
    return _BY_CODE.get(code)


def resolve_racecourse(raw_name: str | None) -> Racecourse | None:
    """Map a source track/location string to a registry entry, if known."""
    key = normalize_track_key(raw_name)
    if not key:
        return None
    return _ALIAS_INDEX.get(key)


def parse_allowed_codes(raw: str | None) -> frozenset[str] | None:
    """
    Parse CRAWL_ALLOWED_RACECOURSES.

    - comma-separated codes → frozenset
    - ``*`` → None (all registered + unknown; nationwide — not default)
    - empty / None → DEFAULT_ALLOWED_CODES
    """
    if raw is None:
        return frozenset(DEFAULT_ALLOWED_CODES)
    text = str(raw).strip()
    if not text:
        return frozenset(DEFAULT_ALLOWED_CODES)
    if text == "*":
        return None
    codes = {part.strip() for part in text.split(",") if part.strip()}
    return frozenset(codes)


def is_racecourse_allowed(
    raw_name: str | None,
    *,
    allowed_codes: frozenset[str] | None,
) -> bool:
    """
    Whether a source location is in crawl scope.

    When ``allowed_codes`` is None (``*``), everything is allowed.
    Unknown locations are rejected when an allowlist is active.
    """
    if allowed_codes is None:
        return True
    course = resolve_racecourse(raw_name)
    if course is None:
        return False
    return course.code in allowed_codes


def is_code_allowed(code: str | None, *, allowed_codes: frozenset[str] | None) -> bool:
    if allowed_codes is None:
        return True
    if not code:
        return False
    return code in allowed_codes
