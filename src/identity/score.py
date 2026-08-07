"""Multi-signal horse identity scoring.

Never rely on exact string matching. Combine fuzzy name + pedigree +
demographics + connections (owner/trainer) + historical race continuity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from src.identity.normalize import name_similarity, normalize_name, normalize_sex
from src.identity.profile import HorseProfile, HorseQuery

# Weights sum to 1.0 — name is necessary but not sufficient.
WEIGHTS = {
    "name": 0.30,
    "sire": 0.12,
    "dam": 0.12,
    "birth_year": 0.10,
    "sex": 0.08,
    "owner": 0.08,
    "trainer": 0.07,
    "continuity": 0.13,
}

# Decision thresholds
AUTO_MERGE_THRESHOLD = 0.88
CANDIDATE_THRESHOLD = 0.72
LOOKUP_THRESHOLD = 0.70


@dataclass
class SignalScore:
    signal: str
    score: float | None  # None = missing on either side
    weight: float
    note: str = ""

    def contribution(self) -> float:
        if self.score is None:
            return 0.0
        return self.weight * self.score

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal,
            "score": None if self.score is None else round(self.score, 4),
            "weight": self.weight,
            "contribution": round(self.contribution(), 4),
            "note": self.note,
        }


@dataclass
class MatchResult:
    left_id: int | None
    right_id: int | None
    total_score: float
    signals: list[SignalScore] = field(default_factory=list)
    method: str = "multi_signal"
    decision: str = "reject"  # auto_merge|candidate|reject

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "total_score": round(self.total_score, 4),
            "method": self.method,
            "decision": self.decision,
            "signals": [s.to_dict() for s in self.signals],
        }


def _best_list_similarity(query: str | None, values: list[str]) -> tuple[float | None, str]:
    nq = normalize_name(query)
    if not nq or not values:
        return None, "missing"
    best = 0.0
    for v in values:
        best = max(best, name_similarity(nq, v))
    if best >= 0.95:
        return best, "strong"
    if best >= 0.80:
        return best, "fuzzy"
    return best, "weak"


def _birth_year_score(a: int | None, b: int | None) -> tuple[float | None, str]:
    if a is None or b is None:
        return None, "missing"
    diff = abs(int(a) - int(b))
    if diff == 0:
        return 1.0, "exact"
    if diff == 1:
        return 0.7, "±1 year"
    if diff == 2:
        return 0.3, "±2 years"
    return 0.0, f"diff={diff}"


def _age_score(a: int | None, b: int | None) -> tuple[float | None, str]:
    """Legacy age proxy — used only when birth_year missing on both sides."""
    if a is None or b is None:
        return None, "missing"
    diff = abs(int(a) - int(b))
    if diff == 0:
        return 1.0, "exact"
    if diff == 1:
        return 0.7, "±1 year"
    if diff == 2:
        return 0.3, "±2 years"
    return 0.0, f"diff={diff}"


def _sex_score(a: str | None, b: str | None) -> tuple[float | None, str]:
    na, nb = normalize_sex(a), normalize_sex(b)
    if not na or not nb or na == "unknown" or nb == "unknown":
        return None, "missing"
    if na == nb:
        return 1.0, "match"
    # male vs gelding soft conflict
    if {na, nb} == {"male", "gelding"}:
        return 0.4, "male/gelding soft"
    return 0.0, "conflict"


def _as_date(value: date | Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _continuity_score(
    left: HorseProfile,
    right: HorseProfile,
) -> tuple[float | None, str, bool]:
    """
    Historical race continuity across cities.

    Returns (score, note, hard_conflict).
    Hard conflict: same calendar day at two different racecourses.
    """
    left_dates = [_as_date(d) for d in left.race_dates]
    right_dates = [_as_date(d) for d in right.race_dates]
    left_dates = [d for d in left_dates if d is not None]
    right_dates = [d for d in right_dates if d is not None]
    if not left_dates or not right_dates:
        return None, "missing", False

    left_by_day = {d: set() for d in left_dates}
    right_by_day = {d: set() for d in right_dates}
    # Attach course codes in parallel order when lengths match; otherwise
    # use unique course membership only for cross-city evidence.
    left_courses = list(left.racecourse_codes or [])
    right_courses = list(right.racecourse_codes or [])

    # Same-day conflict check using date-only sets when course lists are
    # not aligned 1:1 with dates — if both raced on the same day and have
    # disjoint exclusive city sets, treat as soft conflict unless both
    # lists share a course.
    shared_days = set(left_by_day) & set(right_by_day)
    left_only = set(left_courses) - set(right_courses)
    right_only = set(right_courses) - set(left_courses)
    if shared_days and left_only and right_only and not (set(left_courses) & set(right_courses)):
        # Same day appearances with completely disjoint city sets → conflict
        return 0.0, f"same-day disjoint cities days={len(shared_days)}", True

    # Build ordered timelines
    left_sorted = sorted(set(left_dates))
    right_sorted = sorted(set(right_dates))
    all_sorted = sorted(set(left_sorted) | set(right_sorted))
    if len(all_sorted) < 2:
        return 0.55, "single-day sparse", False

    # Gap between careers (min distance between any left/right dates)
    min_gap = min(abs((a - b).days) for a in left_sorted for b in right_sorted)
    span = (all_sorted[-1] - all_sorted[0]).days or 1

    # Interleaved careers without huge separation → continuity support
    # (typical when one warehouse row is Tehran starts and another is Gonbad)
    interleaved = False
    if left_sorted[0] < right_sorted[-1] and right_sorted[0] < left_sorted[-1]:
        interleaved = True
    elif min_gap <= 120:
        interleaved = True

    shared_cities = set(left_courses) & set(right_courses)
    multi_city = bool(left_only or right_only)

    if interleaved and multi_city and min_gap <= 60:
        return 0.95, "interleaved multi-city continuity", False
    if interleaved and min_gap <= 120:
        return 0.85, "adjacent career continuity", False
    if shared_cities and min_gap <= 180:
        return 0.75, "shared city continuity", False
    if min_gap <= 365:
        return 0.60, f"gap={min_gap}d within year", False
    if span > 0 and min_gap > 900:
        return 0.25, f"large career gap={min_gap}d", False
    return 0.45, f"gap={min_gap}d", False


def score_profiles(left: HorseProfile, right: HorseProfile) -> MatchResult:
    """Score two warehouse horse profiles for possible merge."""
    signals: list[SignalScore] = []

    ns = name_similarity(left.name, right.name)
    signals.append(
        SignalScore("name", ns, WEIGHTS["name"], "fuzzy normalized name")
    )

    sire_s, sire_n = _best_list_similarity(left.sire, [right.sire] if right.sire else [])
    signals.append(SignalScore("sire", sire_s, WEIGHTS["sire"], sire_n))

    dam_s, dam_n = _best_list_similarity(left.dam, [right.dam] if right.dam else [])
    signals.append(SignalScore("dam", dam_s, WEIGHTS["dam"], dam_n))

    by_s, by_n = _birth_year_score(left.effective_birth_year(), right.effective_birth_year())
    if by_s is None:
        # Fall back to observed age when birth year unavailable
        by_s, by_n = _age_score(left.age_years, right.age_years)
        if by_s is not None:
            by_n = f"age-proxy:{by_n}"
    signals.append(SignalScore("birth_year", by_s, WEIGHTS["birth_year"], by_n))

    sex_s, sex_n = _sex_score(left.sex, right.sex)
    signals.append(SignalScore("sex", sex_s, WEIGHTS["sex"], sex_n))

    own_s, own_n = _best_list_similarity(left.primary_owner(), right.owners)
    # also try any owner overlap
    if own_s is None and left.owners and right.owners:
        best = 0.0
        for o in left.owners:
            sc, _ = _best_list_similarity(o, right.owners)
            if sc is not None:
                best = max(best, sc)
        own_s, own_n = (best, "overlap") if best > 0 else (None, "missing")
    signals.append(SignalScore("owner", own_s, WEIGHTS["owner"], own_n))

    tr_s, tr_n = _best_list_similarity(left.primary_trainer(), right.trainers)
    if tr_s is None and left.trainers and right.trainers:
        best = 0.0
        for t in left.trainers:
            sc, _ = _best_list_similarity(t, right.trainers)
            if sc is not None:
                best = max(best, sc)
        tr_s, tr_n = (best, "overlap") if best > 0 else (None, "missing")
    signals.append(SignalScore("trainer", tr_s, WEIGHTS["trainer"], tr_n))

    cont_s, cont_n, cont_conflict = _continuity_score(left, right)
    signals.append(SignalScore("continuity", cont_s, WEIGHTS["continuity"], cont_n))

    # Renormalize over available (non-missing) signals so sparse pedigree
    # does not silently dilute name+sex+owner evidence.
    available = [s for s in signals if s.score is not None]
    if not available:
        total = 0.0
    else:
        wsum = sum(s.weight for s in available)
        total = sum(s.weight * s.score for s in available) / wsum if wsum else 0.0

    # Hard vetoes
    if sex_s == 0.0:
        total *= 0.35
    if ns < 0.55:
        total *= 0.5
    if cont_conflict:
        total *= 0.25
    if by_s == 0.0:
        total *= 0.55

    # Source-id exact boost (still not string name matching)
    if (
        left.source_horse_id
        and right.source_horse_id
        and left.source_horse_id == right.source_horse_id
        and left.source == right.source
    ):
        total = max(total, 0.99)
        signals.append(
            SignalScore("source_horse_id", 1.0, 0.0, "identical source id")
        )

    decision = "reject"
    if total >= AUTO_MERGE_THRESHOLD and ns >= 0.80:
        decision = "auto_merge"
    elif total >= CANDIDATE_THRESHOLD and ns >= 0.65:
        decision = "candidate"

    # High-confidence national identity: identical normalized name + matching
    # demographics + historical race continuity. Owner/trainer often drift when
    # the same horse appears in multiple cities — do not keep duplicates.
    if (
        decision != "auto_merge"
        and not cont_conflict
        and ns >= 0.98
        and sex_s == 1.0
        and by_s is not None
        and by_s >= 0.7
        and cont_s is not None
        and cont_s >= 0.75
    ):
        total = max(total, AUTO_MERGE_THRESHOLD)
        decision = "auto_merge"
        signals.append(
            SignalScore(
                "national_continuity_rule",
                1.0,
                0.0,
                "name+sex+birth_year+continuity",
            )
        )

    return MatchResult(
        left_id=left.warehouse_horse_id,
        right_id=right.warehouse_horse_id,
        total_score=total,
        signals=signals,
        decision=decision,
    )


def score_query(query: HorseQuery, profile: HorseProfile) -> MatchResult:
    """Score a race-card query against a known profile."""
    q_profile = HorseProfile(
        warehouse_horse_id=-1,
        name=query.name or "",
        source_horse_id=query.source_horse_id,
        sex=query.sex,
        age_years=query.age,
        birth_year=(
            query.as_of_date.year - query.age
            if query.as_of_date and query.age is not None
            else None
        ),
        sire=query.sire,
        dam=query.dam,
        owners=[query.owner] if query.owner else [],
        trainers=[query.trainer] if query.trainer else [],
    )
    result = score_profiles(q_profile, profile)
    result.left_id = None
    result.right_id = profile.warehouse_horse_id
    result.method = "query_multi_signal"
    if result.total_score >= LOOKUP_THRESHOLD and name_similarity(query.name, profile.name) >= 0.65:
        result.decision = "match" if result.total_score >= AUTO_MERGE_THRESHOLD else "candidate"
    elif result.decision == "auto_merge":
        result.decision = "match"
    return result
