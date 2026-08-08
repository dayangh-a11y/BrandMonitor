"""
Racecourse registry — expandable without database redesign.

Enable/disable which tracks the crawler collects via settings
(`CRAWL_ALLOWED_RACECOURSES`). Codes are stable; aliases absorb
Persian spelling variants from the source site.

Default crawl scope is nationwide (``*``). Pass an explicit comma list
to restrict collection (e.g. Golestan triad).
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


# Historical Golestan triad — still available for scoped crawls.
GOLESTAN_CODES: tuple[str, ...] = (
    "gonbad-kavous",
    "aq-qala",
    "bandar-torkaman",
)

# Backward-compatible alias (older docs/tests referred to DEFAULT_ALLOWED_CODES).
DEFAULT_ALLOWED_CODES: tuple[str, ...] = GOLESTAN_CODES

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
            "شهدای بندرترکمن",
            "شهدای بندر ترکمن",
            "bandar torkaman",
            "bandar-torkaman",
            "torkaman",
        ),
        latitude=36.9017,
        longitude=54.0739,
        timezone="Asia/Tehran",
    ),
    Racecourse(
        code="tehran",
        name_en="Tehran",
        name_fa="تهران",
        aliases=(
            "تهران",
            "طهران",
            "نوروزآباد تهران",
            "نوروز آباد تهران",
            "نوروزآباد",
            "نوروز آباد",
            "tehran",
            "teheran",
        ),
        latitude=35.6892,
        longitude=51.3890,
        timezone="Asia/Tehran",
    ),
    Racecourse(
        code="yazd",
        name_en="Yazd",
        name_fa="یزد",
        aliases=("یزد", "يزد", "صفائیه یزد", "صفائیه", "yazd"),
        latitude=31.8974,
        longitude=54.3569,
        timezone="Asia/Tehran",
    ),
    Racecourse(
        code="ahvaz",
        name_en="Ahvaz",
        name_fa="اهواز",
        aliases=("اهواز", "اهواز ", "نیرو اهواز", "ahvaz", "ahwaz"),
        latitude=31.3183,
        longitude=48.6706,
        timezone="Asia/Tehran",
    ),
    Racecourse(
        code="kish",
        name_en="Kish",
        name_fa="کیش",
        aliases=("کیش", "كيش", "کيش", "kish"),
        latitude=26.5578,
        longitude=53.9912,
        timezone="Asia/Tehran",
    ),
    Racecourse(
        code="anbar-alum",
        name_en="Anbar Alum",
        name_fa="انبارآلوم",
        aliases=(
            "انبارآلوم",
            "انبار آلوم",
            "انبارالوم",
            "anbar alum",
            "anbar-alum",
            "anbaralum",
        ),
        latitude=37.1300,
        longitude=54.6200,
        timezone="Asia/Tehran",
    ),
    Racecourse(
        code="mashhad",
        name_en="Mashhad",
        name_fa="مشهد",
        aliases=("مشهد", "ثامن مشهد", "ثامن", "mashhad", "mashad"),
        latitude=36.2605,
        longitude=59.6168,
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


def synthesize_racecourse(raw_name: str) -> Racecourse:
    """
    Build a stable synthetic registry entry for an unregistered track.

    Used in nationwide mode so newly appearing cities still ingest with a
    deterministic ``racecourse_code`` (without inventing coordinates).
    """
    import hashlib

    key = normalize_track_key(raw_name) or "unknown"
    # Prefer a short latin-safe code; fall back to stable hex of the key.
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", key.encode("ascii", "ignore").decode() or "")
    ascii_slug = ascii_slug.strip("-")[:40]
    if not ascii_slug:
        ascii_slug = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    code = f"ir-{ascii_slug}"
    name = str(raw_name).strip() or code
    return Racecourse(
        code=code,
        name_en=name,
        name_fa=name,
        aliases=(name,),
    )


def ensure_racecourse(raw_name: str | None) -> Racecourse:
    """Resolve a known course or synthesize one for nationwide ingest."""
    if not raw_name or not str(raw_name).strip():
        raise ValueError("Racecourse name is required")
    return resolve_racecourse(raw_name) or synthesize_racecourse(str(raw_name).strip())


def parse_allowed_codes(raw: str | None) -> frozenset[str] | None:
    """
    Parse CRAWL_ALLOWED_RACECOURSES.

    - ``*`` / empty / None → None (nationwide — all locations)
    - comma-separated codes → frozenset restrict list
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text == "*":
        return None
    codes = {part.strip() for part in text.split(",") if part.strip()}
    return frozenset(codes) if codes else None


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
