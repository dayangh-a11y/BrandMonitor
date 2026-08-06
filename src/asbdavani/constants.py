"""asbdavani.app constants and helpers (site-specific, isolated)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

BASE_URL = "https://asbdavani.app"
RACECARDS_PATH = "/racecards"
HORSE_PERF_PATH = "/performance/horses"

SEX_MAP = {
    "MALE": "نر",
    "FEMALE": "ماده",
    "GELDING": "اخته",
}

BLOOD_SURFACE_HINT = {
    "TURKMEN": "ترکمن",
    "ARAB": "عرب",
    "DOKHOON": "دوخون",
    "THORUGHBREAD": "تروبرد",
    "THOROUGHBRED": "تروبرد",
}


def absolute_url(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return urljoin(BASE_URL, path_or_url)


def horse_profile_url(horse_id: str) -> str:
    return absolute_url(f"{HORSE_PERF_PATH}/{horse_id}")


def parse_race_url(url: str) -> tuple[str | None, int | None]:
    """
    Extract week id and optional round from a racecards URL.

    Examples:
      /racecards/{weekId}?round=1
      /racecards/{weekId}
    """
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    week_id: str | None = None
    if len(parts) >= 2 and parts[0] == "racecards":
        week_id = parts[1]
    qs = parse_qs(parsed.query)
    round_raw = qs.get("round", [None])[0]
    race_round = int(round_raw) if round_raw and str(round_raw).isdigit() else None
    return week_id, race_round


def parse_horse_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    m = re.search(r"/performance/horses/([^/]+)", parsed.path)
    return m.group(1) if m else None


def format_race_time(raw: Any) -> str | float | None:
    """
    Site stores finish time as integer milliseconds (e.g. 72424 -> 1:12.424).
    Return a human-readable mm:ss.mmm string when possible.
    """
    if raw is None or raw == "" or raw == 0:
        return None
    try:
        millis = int(raw)
    except (TypeError, ValueError):
        return str(raw)
    if millis <= 0:
        return None
    total_seconds = millis / 1000.0
    minutes = int(total_seconds // 60)
    seconds = total_seconds - minutes * 60
    if minutes > 0:
        return f"{minutes}:{seconds:06.3f}"
    return f"{seconds:.3f}"


def compute_age(birthdate: str | datetime | date | None, on: date | None = None) -> int | None:
    if not birthdate:
        return None
    if isinstance(birthdate, str):
        try:
            birth = datetime.fromisoformat(birthdate.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    elif isinstance(birthdate, datetime):
        birth = birthdate.date()
    else:
        birth = birthdate
    ref = on or date.today()
    years = ref.year - birth.year - ((ref.month, ref.day) < (birth.month, birth.day))
    return years if years >= 0 else None


def normalize_sex(value: str | None) -> str | None:
    if not value:
        return None
    return SEX_MAP.get(value.upper(), value)


def location_from_week_and_leagues(
    week: dict[str, Any],
    leagues: list[dict[str, Any]] | None = None,
) -> str | None:
    """Resolve track/province name from week + leagues payload when available."""
    league_id = week.get("leagueId")
    if leagues and league_id:
        for league in leagues:
            if league.get("id") == league_id:
                loc = (league.get("location") or {}).get("name")
                if loc:
                    return loc
    # Fallback: parse from week name e.g. "هفته 1 مشهد 1405"
    name = week.get("name") or ""
    m = re.search(
        r"هفته\s+\d+\s+(.+?)\s+\d{4}",
        name,
    )
    if m:
        return m.group(1).strip()
    return None


def prize_summary(prize_obj: dict[str, Any] | None) -> dict[str, Any] | None:
    if not prize_obj:
        return None
    prizes = prize_obj.get("prizes") or []
    return {
        "name": prize_obj.get("name"),
        "prizes": prizes,
        "total": sum((p.get("prize") or 0) for p in prizes),
    }
