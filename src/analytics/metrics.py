"""Pure metric helpers for the analytics layer (no DB I/O)."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import mean, pstdev
from typing import Any


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def safe_rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return num / den


def parse_time_seconds(raw: str | None) -> float | None:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if ":" in text:
            parts = text.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(text)
    except ValueError:
        return None


def parse_prize_map(prize_json: Any) -> dict[int, float]:
    if not prize_json:
        return {}
    obj = prize_json
    if isinstance(prize_json, str):
        import json

        try:
            obj = json.loads(prize_json)
        except json.JSONDecodeError:
            return {}
    out: dict[int, float] = {}
    for p in (obj or {}).get("prizes") or []:
        rank = p.get("rank")
        val = p.get("prize")
        if rank is not None and isinstance(val, (int, float)):
            out[int(rank)] = float(val)
    return out


CLASS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"گروه\s*1(?:\s|$|[^و0-9])"), "group1"),
    (re.compile(r"گروه\s*1\s*و\s*2"), "group1_2"),
    (re.compile(r"گروه\s*2"), "group2"),
    (re.compile(r"گروه\s*3"), "group3"),
    (re.compile(r"\(G1\)|G1\b", re.I), "g1"),
    (re.compile(r"\(G2\)|G2\b", re.I), "g2"),
    (re.compile(r"\(G3\)|G3\b", re.I), "g3"),
    (re.compile(r"کلاس\s*([0-9]{1,2})"), "class"),
    (re.compile(r"مبتدی|نبرده"), "maiden"),
    (re.compile(r"میدن"), "maiden"),
    (re.compile(r"برنده"), "winner"),
    (re.compile(r"ایران\s*کاپ"), "iran_cup"),
]


def parse_race_class(name: str | None) -> str:
    if not name:
        return "unknown"
    text = str(name)
    for pat, label in CLASS_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if label == "class":
            return f"class{m.group(1)}"
        return label
    # Handicap band
    if re.search(r"از\s*\d+\s*تا\s*\d+", text):
        return "handicap_band"
    return "other"


def distance_bucket(distance: int | None) -> str:
    if distance is None:
        return "unknown"
    d = int(distance)
    if d < 1200:
        return "sprint"  # <1200
    if d < 1600:
        return "mile"  # 1200-1599
    if d < 2000:
        return "mid"  # 1600-1999
    return "staying"  # 2000+


def age_years(birthdate: date | None, on: date | None) -> float | None:
    if birthdate is None or on is None:
        return None
    days = (on - birthdate).days
    if days < 0:
        return None
    return round(days / 365.25, 2)


def age_band(years: float | None) -> str:
    if years is None:
        return "unknown"
    if years < 3:
        return "2yo"
    if years < 4:
        return "3yo"
    if years < 5:
        return "4yo"
    if years < 7:
        return "5-6yo"
    return "7yo+"


def form_score(finishes_newest_first: list[int], window: int) -> float | None:
    """
    Form score 0..100 from recent finishes (1=best).

    Uses exponential decay so newer races weigh more.
    """
    vals = [f for f in finishes_newest_first[:window] if f and f > 0]
    if not vals:
        return None
    total_w = 0.0
    acc = 0.0
    for i, pos in enumerate(vals):
        w = 0.75**i
        # Position quality: 1st→100, 2nd→80, 3rd→65, then decays
        quality = clamp(120.0 - 20.0 * pos, 0.0, 100.0)
        acc += w * quality
        total_w += w
    return round(acc / total_w, 3) if total_w else None


def consistency_score(finishes: list[int]) -> float | None:
    """Higher when finish positions are stable (low dispersion)."""
    vals = [f for f in finishes if f and f > 0]
    if len(vals) < 2:
        return 100.0 if len(vals) == 1 else None
    sd = pstdev(vals)
    # sd of 0 → 100; sd of ~4 → ~20
    return round(clamp(100.0 * math.exp(-sd / 2.5)), 3)


def trend_slope(finishes_newest_first: list[int], window: int = 5) -> float | None:
    """
    Positive slope => improving (finishing better recently).

    Uses oldest→newest position quality regression.
    """
    vals = [f for f in finishes_newest_first[:window] if f and f > 0]
    if len(vals) < 3:
        return None
    # reverse to chronological
    chrono = list(reversed(vals))
    qualities = [clamp(120.0 - 20.0 * p, 0.0, 100.0) for p in chrono]
    n = len(qualities)
    xs = list(range(n))
    x_bar = mean(xs)
    y_bar = mean(qualities)
    num = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, qualities))
    den = sum((x - x_bar) ** 2 for x in xs) or 1.0
    return round(num / den, 4)


def fatigue_score(
    *,
    days_since_last: int | None,
    starts_last_30d: int,
) -> float | None:
    """
    0 = fresh, 100 = heavily raced / short turnaround.

    International handicapping often flags <7 day turnarounds and dense campaigns.
    """
    if days_since_last is None and starts_last_30d <= 0:
        return None
    turnaround = 0.0
    if days_since_last is not None:
        if days_since_last <= 3:
            turnaround = 90.0
        elif days_since_last <= 7:
            turnaround = 70.0
        elif days_since_last <= 14:
            turnaround = 40.0
        elif days_since_last <= 28:
            turnaround = 20.0
        else:
            turnaround = 5.0
    density = clamp(starts_last_30d * 18.0)
    return round(clamp(0.6 * turnaround + 0.4 * density), 3)


def speed_index_for_run(
    *,
    time_s: float | None,
    distance: int | None,
    field_times: list[float],
) -> float | None:
    """
    Relative speed vs field: 100 = field average, higher = faster.

    Uses lengths-per-second style: distance/time vs mean field.
    """
    if time_s is None or time_s <= 0 or not distance:
        return None
    horse_mps = distance / time_s
    field = [distance / t for t in field_times if t and t > 0]
    if not field:
        return 100.0
    avg = mean(field)
    if avg <= 0:
        return None
    return round(clamp(100.0 * (horse_mps / avg), 50.0, 150.0), 3)


def difficulty_index(
    *,
    field_ratings: list[float],
    field_size: int,
    race_class: str,
) -> float:
    """Opponent quality proxy 0..100."""
    ratings = [r for r in field_ratings if r and r > 0]
    rating_component = mean(ratings) if ratings else 40.0
    # Normalize typical IR ratings ~40-120 into 0..100-ish
    rating_score = clamp((rating_component - 30.0) * 1.1)
    size_score = clamp(field_size * 6.0)
    class_boost = {
        "group1": 25,
        "g1": 25,
        "group1_2": 18,
        "group2": 15,
        "g2": 15,
        "group3": 10,
        "g3": 10,
        "iran_cup": 12,
        "class1": 12,
        "class2": 8,
    }.get(race_class, 0)
    return round(clamp(0.55 * rating_score + 0.25 * size_score + class_boost), 3)


def performance_rating(
    *,
    win_rate: float | None = None,
    place_rate: float | None = None,
    avg_finish: float | None = None,
    consistency: float | None = None,
    speed_index: float | None = None,
    earnings_index: float | None = None,
    difficulty_index: float | None = None,
    starts: int | None = None,
    wins: int | None = None,
    seconds: int | None = None,
    thirds: int | None = None,
    form_score: float | None = None,
    include_earnings: bool = False,
) -> float | None:
    """
    Composite 0..100 racing Performance Rating (Season Best).

    Earnings are excluded by default (Rule 3/4) — use only as an external
    tie-breaker when sorting. Optional ``include_earnings`` keeps a tiny
    legacy path for experiments (weight ≤ 3%).
    """
    n = int(starts or 0)
    parts: list[tuple[float, float]] = []

    # Wins / seconds / thirds rates (racing outcomes)
    if n > 0 and wins is not None:
        parts.append((18.0, clamp(100.0 * float(wins) / n)))
    elif win_rate is not None:
        parts.append((18.0, win_rate * 100.0))

    if n > 0 and seconds is not None:
        parts.append((8.0, clamp(100.0 * float(seconds) / n)))
    if n > 0 and thirds is not None:
        parts.append((5.0, clamp(100.0 * float(thirds) / n)))

    # Podium rate (wins+seconds+thirds) preferred over generic place_rate
    if n > 0 and wins is not None and seconds is not None and thirds is not None:
        podium = (float(wins) + float(seconds) + float(thirds)) / n
        parts.append((15.0, clamp(podium * 100.0)))
    elif place_rate is not None:
        parts.append((15.0, place_rate * 100.0))

    if avg_finish is not None:
        parts.append((15.0, clamp(120.0 - 12.5 * avg_finish)))

    # Consistency only meaningful with multiple starts
    if consistency is not None and n >= 3:
        parts.append((12.0, consistency))
    elif consistency is not None and n >= 2:
        parts.append((6.0, consistency))

    if difficulty_index is not None:
        parts.append((12.0, difficulty_index))

    form_v = form_score
    if form_v is not None:
        parts.append((10.0, clamp(form_v)))

    if speed_index is not None:
        parts.append((5.0, clamp(speed_index)))

    # Rule 3: prize money must never dominate — default off
    if include_earnings and earnings_index is not None:
        parts.append((3.0, earnings_index * 100.0))

    if not parts:
        return None
    wsum = sum(w for w, _ in parts)
    return round(sum(w * v for w, v in parts) / wsum, 3)


def preference_from_buckets(
    buckets: dict[str, list[int]],
) -> tuple[str | None, float | None]:
    best_key = None
    best_score = None
    for key, finishes in buckets.items():
        if not finishes:
            continue
        wins = sum(1 for f in finishes if f == 1)
        wr = wins / len(finishes)
        score = wr * (1.0 - 0.5 / (len(finishes) + 0.5))
        if best_score is None or score > best_score:
            best_score = score
            best_key = key
    return best_key, (round(best_score, 4) if best_score is not None else None)


def combo_score(pairs: dict[str, list[int]]) -> tuple[str | None, float | None]:
    return preference_from_buckets(pairs)


@dataclass
class StartRec:
    horse_id: int
    horse_name: str
    race_id: int
    race_date: date | None
    racecourse_code: str | None
    breed: str | None
    distance: int | None
    race_name: str | None
    finish: int
    time_raw: str | None
    source_rating: float | None
    prize: float
    jockey: str | None
    trainer: str | None
    owner: str | None
    sire: str | None
    birthdate: date | None
    weather_category: str | None = None
    track_condition: str | None = None
    field_times: list[float] = field(default_factory=list)
    field_ratings: list[float] = field(default_factory=list)
    field_size: int = 0


def as_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
