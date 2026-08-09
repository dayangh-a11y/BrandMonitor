"""Race Intelligence — post-race surprise / crowd / over-under ratings."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any


@dataclass(frozen=True, slots=True)
class RunnerIntel:
    horse_id: int
    horse_name: str
    finish: int
    rating: float | None
    expected_rank: int
    residual: float  # expected_rank - finish (>0 finished better than expected)
    cloth: int | None = None


@dataclass(frozen=True, slots=True)
class RaceIntelligence:
    race_id: int
    difficulty_stars: int
    difficulty_label: str
    crowd_accuracy_pct: float
    biggest_surprise_horse: str | None
    biggest_surprise_horse_id: int | None
    most_overrated_horse: str | None
    most_overrated_horse_id: int | None
    most_underrated_horse: str | None
    most_underrated_horse_id: int | None
    shock_score: float
    prediction_confidence: str  # High|Medium|Low
    expectation_source: str  # rating|mixed|none
    field_size: int
    favorite_name: str | None
    favorite_finish: int | None
    winner_name: str | None
    winner_expected_rank: int | None
    runners: list[RunnerIntel]
    explain_json: dict[str, Any]

    def as_report(self) -> str:
        stars = "★" * self.difficulty_stars + "☆" * (5 - self.difficulty_stars)
        return "\n".join(
            [
                "Race Intelligence",
                "",
                f"Difficulty:",
                stars,
                "",
                "Crowd Accuracy:",
                f"{self.crowd_accuracy_pct:.0f}%",
                "",
                "Biggest Surprise:",
                self.biggest_surprise_horse or "—",
                "",
                "Most Overrated Horse:",
                self.most_overrated_horse or "—",
                "",
                "Most Underrated Horse:",
                self.most_underrated_horse or "—",
                "",
                "Shock Score:",
                f"{self.shock_score:.0f}/100",
                "",
                "Prediction Confidence:",
                self.prediction_confidence,
            ]
        )


def _expected_ranks(ratings: list[float | None]) -> list[int]:
    """
    Rank runners by pre-race expectation (higher rating = better expected finish).

    Ties share average rank space via stable sort; missing/zero ratings sink to bottom.
    """
    indexed = list(enumerate(ratings))

    def sort_key(item: tuple[int, float | None]) -> tuple[int, float, int]:
        i, r = item
        missing = 1 if r is None or r <= 0 else 0
        val = float(r) if r is not None else 0.0
        return (missing, -val, i)

    ordered = sorted(indexed, key=sort_key)
    ranks = [0] * len(ratings)
    for exp_rank, (i, _) in enumerate(ordered, start=1):
        ranks[i] = exp_rank
    return ranks


def spearman_accuracy(expected: list[int], actual: list[int]) -> float:
    """Map Spearman correlation of rankings to 0..100 crowd-accuracy style score."""
    n = len(expected)
    if n < 2:
        return 100.0
    # Spearman rho via rank differences
    d2 = sum((e - a) ** 2 for e, a in zip(expected, actual))
    rho = 1.0 - (6.0 * d2) / (n * (n * n - 1))
    # rho -1..1 → 0..100
    return max(0.0, min(100.0, (rho + 1.0) * 50.0))


def difficulty_stars(
    *,
    field_size: int,
    ratings: list[float],
    race_class_boost: float = 0.0,
) -> tuple[int, str]:
    """
    1–5 stars: competitive fields with tight ratings score higher difficulty.
    """
    if field_size <= 1:
        return 1, "Trivial"
    positive = [r for r in ratings if r > 0]
    spread = pstdev(positive) if len(positive) >= 2 else 0.0
    # Tight spread ⇒ hard to separate ⇒ harder race
    tightness = max(0.0, 1.0 - min(spread, 40.0) / 40.0)
    size = min(1.0, field_size / 12.0)
    score = 100.0 * (0.55 * tightness + 0.30 * size + 0.15 * min(1.0, race_class_boost))
    if score >= 80:
        return 5, "Extreme"
    if score >= 65:
        return 4, "Very Hard"
    if score >= 45:
        return 3, "Hard"
    if score >= 25:
        return 2, "Moderate"
    return 1, "Easy"


def shock_score(
    *,
    favorite_finish: int | None,
    winner_expected_rank: int | None,
    field_size: int,
    crowd_accuracy_pct: float,
) -> float:
    """0..100 — higher means more shocking outcome."""
    parts: list[float] = []
    if favorite_finish is not None:
        # Favorite win ⇒ low shock; favorite last ⇒ high
        parts.append(min(100.0, max(0.0, (favorite_finish - 1) * (100.0 / max(field_size - 1, 1)))))
    if winner_expected_rank is not None:
        parts.append(min(100.0, max(0.0, (winner_expected_rank - 1) * (100.0 / max(field_size - 1, 1)))))
    # Invert crowd accuracy contribution
    parts.append(100.0 - crowd_accuracy_pct)
    return round(mean(parts), 1) if parts else 0.0


def prediction_confidence(
    *,
    ratings: list[float],
    shock: float,
    expectation_usable: bool,
) -> str:
    if not expectation_usable:
        return "Low"
    positive = sorted([r for r in ratings if r > 0], reverse=True)
    gap = (positive[0] - positive[1]) if len(positive) >= 2 else 0.0
    if gap >= 12 and shock < 35:
        return "High"
    if gap >= 6 and shock < 55:
        return "Medium"
    if shock >= 70 or gap < 3:
        return "Low"
    return "Medium"


def compute_race_intelligence(
    *,
    race_id: int,
    runners: list[dict[str, Any]],
    race_class: str | None = None,
) -> RaceIntelligence | None:
    """
    ``runners`` items: horse_id, horse_name, finish, rating, cloth(optional).

    Expectation proxy: ``source_rating`` (IOR/odds unavailable in warehouse).
    """
    usable = [
        r
        for r in runners
        if r.get("finish") is not None and int(r["finish"]) > 0 and r.get("horse_id") is not None
    ]
    if len(usable) < 2:
        return None

    ratings = [
        float(r["rating"]) if r.get("rating") is not None else None for r in usable
    ]
    expected = _expected_ranks(ratings)
    actual = [int(r["finish"]) for r in usable]
    field_size = len(usable)

    intel_runners: list[RunnerIntel] = []
    for r, exp in zip(usable, expected):
        fin = int(r["finish"])
        rating = float(r["rating"]) if r.get("rating") is not None else None
        intel_runners.append(
            RunnerIntel(
                horse_id=int(r["horse_id"]),
                horse_name=str(r.get("horse_name") or f"#{r['horse_id']}"),
                finish=fin,
                rating=rating,
                expected_rank=exp,
                residual=float(exp - fin),
                cloth=r.get("cloth"),
            )
        )

    usable_ratings = [r for r in ratings if r is not None and r > 0]
    expectation_source = "rating" if len(usable_ratings) >= max(2, field_size // 2) else (
        "mixed" if usable_ratings else "none"
    )

    crowd = spearman_accuracy(expected, actual) if expectation_source != "none" else 0.0

    # Favorite = expected rank 1
    favorite = next((x for x in intel_runners if x.expected_rank == 1), None)
    winner = next((x for x in intel_runners if x.finish == 1), None)

    # Biggest surprise: largest positive residual (finished way above expectation)
    surprise = max(intel_runners, key=lambda x: (x.residual, -x.finish))
    # Most underrated: among bottom half of expectations, best residual
    half = field_size // 2 + 1
    underrated_pool = [x for x in intel_runners if x.expected_rank >= half] or intel_runners
    underrated = max(underrated_pool, key=lambda x: (x.residual, -x.finish))
    # Most overrated: among top half expectations, worst residual (finished worse)
    over_pool = [x for x in intel_runners if x.expected_rank <= half] or intel_runners
    overrated = min(over_pool, key=lambda x: (x.residual, -x.expected_rank))

    class_boost = 0.0
    if race_class:
        class_boost = {
            "group1": 1.0,
            "g1": 1.0,
            "group2": 0.7,
            "g2": 0.7,
            "group3": 0.4,
            "class1": 0.5,
            "class2": 0.35,
        }.get(race_class, 0.15)

    stars, diff_label = difficulty_stars(
        field_size=field_size,
        ratings=[float(r or 0) for r in ratings],
        race_class_boost=class_boost,
    )
    shock = shock_score(
        favorite_finish=favorite.finish if favorite else None,
        winner_expected_rank=winner.expected_rank if winner else None,
        field_size=field_size,
        crowd_accuracy_pct=crowd,
    )
    conf = prediction_confidence(
        ratings=[float(r or 0) for r in ratings],
        shock=shock,
        expectation_usable=expectation_source == "rating",
    )

    explain = {
        "expectation_source": expectation_source,
        "note": (
            "Pre-race expectation uses source_rating (entrance rating) because "
            "wh_race_results.odds / IOR is not available."
            if expectation_source != "none"
            else "No usable ratings — intelligence degraded."
        ),
        "favorite": {
            "name": favorite.horse_name if favorite else None,
            "rating": favorite.rating if favorite else None,
            "finish": favorite.finish if favorite else None,
        },
        "winner": {
            "name": winner.horse_name if winner else None,
            "expected_rank": winner.expected_rank if winner else None,
            "rating": winner.rating if winner else None,
        },
        "biggest_surprise": {
            "name": surprise.horse_name,
            "expected_rank": surprise.expected_rank,
            "finish": surprise.finish,
            "residual": surprise.residual,
        },
        "most_overrated": {
            "name": overrated.horse_name,
            "expected_rank": overrated.expected_rank,
            "finish": overrated.finish,
            "residual": overrated.residual,
        },
        "most_underrated": {
            "name": underrated.horse_name,
            "expected_rank": underrated.expected_rank,
            "finish": underrated.finish,
            "residual": underrated.residual,
        },
        "crowd_accuracy_pct": crowd,
        "shock_score": shock,
        "difficulty_stars": stars,
        "difficulty_label": diff_label,
        "prediction_confidence": conf,
    }

    return RaceIntelligence(
        race_id=race_id,
        difficulty_stars=stars,
        difficulty_label=diff_label,
        crowd_accuracy_pct=round(crowd, 1),
        biggest_surprise_horse=surprise.horse_name,
        biggest_surprise_horse_id=surprise.horse_id,
        most_overrated_horse=overrated.horse_name,
        most_overrated_horse_id=overrated.horse_id,
        most_underrated_horse=underrated.horse_name,
        most_underrated_horse_id=underrated.horse_id,
        shock_score=shock,
        prediction_confidence=conf,
        expectation_source=expectation_source,
        field_size=field_size,
        favorite_name=favorite.horse_name if favorite else None,
        favorite_finish=favorite.finish if favorite else None,
        winner_name=winner.horse_name if winner else None,
        winner_expected_rank=winner.expected_rank if winner else None,
        runners=intel_runners,
        explain_json=explain,
    )
