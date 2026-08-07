"""
MATCHUP ENGINE — direct A vs B.

When user asks «دنزی بوی یا لیدی سانگ؟» do NOT use season ranking.
Build a factor-by-factor matchup with finish-ahead probabilities.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.markets.answer import MarketAnswer, confidence_band, data_quality_label
from src.markets.h2h import load_historical_pair_meetings, pairwise_compare
from src.markets.scoring import RunnerContext
from src.warehouse.fuzzy import normalize_name
from src.warehouse.models import WhHorse


# Factors compared in a direct matchup (each contributes a signed edge for A)
MATCHUP_FACTORS = (
    "recent_form",
    "distance",
    "track",
    "competition_strength",
    "speed",
    "trainer",
    "jockey",
    "rest_days",
    "weight",
    "age",
    "sex",
    "field_strength",
    "opponent_strength",
)


def _edge(a: float | None, b: float | None, *, higher_better: bool = True) -> float | None:
    if a is None or b is None:
        return None
    diff = float(a) - float(b)
    return diff if higher_better else -diff


def factor_comparison(a: RunnerContext, b: RunnerContext) -> list[dict[str, Any]]:
    factors: list[dict[str, Any]] = []

    def add(name: str, a_val, b_val, edge: float | None, note: str) -> None:
        factors.append(
            {
                "factor": name,
                "a": a_val,
                "b": b_val,
                "edge_for_a": round(edge, 4) if edge is not None else None,
                "note": note,
            }
        )

    add(
        "recent_form",
        a.form_score_5,
        b.form_score_5,
        _edge(a.form_score_5, b.form_score_5),
        "Higher form_score_5 is better",
    )
    add(
        "distance",
        a.meta.get("distance_pref_score"),
        b.meta.get("distance_pref_score"),
        _edge(a.meta.get("distance_pref_score"), b.meta.get("distance_pref_score")),
        "Distance preference strength at today's trip",
    )
    add(
        "track",
        a.meta.get("track_pref_score"),
        b.meta.get("track_pref_score"),
        _edge(a.meta.get("track_pref_score"), b.meta.get("track_pref_score")),
        "Track preference strength",
    )
    add(
        "competition_strength",
        a.difficulty_index,
        b.difficulty_index,
        _edge(a.difficulty_index, b.difficulty_index),
        "Has faced tougher fields historically",
    )
    add(
        "speed",
        a.speed_index,
        b.speed_index,
        _edge(a.speed_index, b.speed_index),
        "Higher speed_index is better",
    )
    # Trainer / jockey: binary presence comparison via combo scores in meta
    add(
        "trainer",
        a.trainer,
        b.trainer,
        _edge(a.meta.get("trainer_score"), b.meta.get("trainer_score")),
        f"Trainer combo scores ({a.trainer} vs {b.trainer})",
    )
    add(
        "jockey",
        a.jockey,
        b.jockey,
        _edge(a.meta.get("jockey_score"), b.meta.get("jockey_score")),
        f"Jockey combo scores ({a.jockey} vs {b.jockey})",
    )
    add(
        "rest_days",
        a.rest_days,
        b.rest_days,
        # Ideal rest ~10–21 days; simple: closer to 14 is better
        None
        if a.rest_days is None or b.rest_days is None
        else -(abs((a.rest_days or 14) - 14) - abs((b.rest_days or 14) - 14)),
        "Rest closer to ~14 days preferred",
    )
    add(
        "weight",
        a.weight,
        b.weight,
        _edge(a.weight, b.weight, higher_better=False),
        "Lower weight is an advantage when known",
    )
    add(
        "age",
        a.age_years,
        b.age_years,
        # Prefer prime 4–6yo lightly
        None
        if a.age_years is None or b.age_years is None
        else -(abs((a.age_years or 5) - 5) - abs((b.age_years or 5) - 5)),
        "Age nearer prime (~5yo) preferred",
    )
    # Sex: use sex-adjusted PR differential as proxy (already sex-aware)
    add(
        "sex",
        a.sex,
        b.sex,
        _edge(a.sex_adjusted_pr or a.performance_rating, b.sex_adjusted_pr or b.performance_rating),
        "Compared via sex-adjusted performance when available",
    )
    add(
        "field_strength",
        a.meta.get("field_strength"),
        b.meta.get("field_strength"),
        _edge(a.meta.get("field_strength"), b.meta.get("field_strength")),
        "Ability vs typical field strength faced",
    )
    add(
        "opponent_strength",
        a.difficulty_index,
        b.difficulty_index,
        _edge(a.difficulty_index, b.difficulty_index),
        "Opponent quality faced (difficulty_index)",
    )
    return factors


def analyze_matchup(
    a: RunnerContext,
    b: RunnerContext,
    *,
    session: Session | None = None,
    race_distance: int | None = None,
    race_track: str | None = None,
) -> MarketAnswer:
    hist = None
    if session is not None:
        hist = load_historical_pair_meetings(
            session, a.horse_id, b.horse_id, distance=race_distance
        )
    pair = pairwise_compare(
        a, b, historical=hist, race_distance=race_distance, race_track=race_track
    )
    factors = factor_comparison(a, b)
    usable = [f for f in factors if f["edge_for_a"] is not None]
    factor_edge = sum(f["edge_for_a"] for f in usable) / max(1, len(usable)) if usable else 0.0
    # Blend pairwise ahead-prob with factor vote
    factor_prob_a = 0.5 + max(-0.45, min(0.45, factor_edge / 80.0))
    p_a = 0.65 * pair.a_ahead_prob + 0.35 * factor_prob_a
    p_a = max(0.02, min(0.98, p_a))
    p_b = 1.0 - p_a

    favoring = [f for f in usable if (f["edge_for_a"] or 0) > 0]
    against = [f for f in usable if (f["edge_for_a"] or 0) < 0]
    reasons = [
        f"{a.horse_name} finishes ahead probability {p_a:.1%}",
        f"{b.horse_name} finishes ahead probability {p_b:.1%}",
        f"Historical H2H meetings: {pair.historical_h2h.get('meetings', 0)}",
        f"Factors favoring {a.horse_name}: "
        + (", ".join(f["factor"] for f in favoring[:6]) or "none clear"),
        f"Factors favoring {b.horse_name}: "
        + (", ".join(f["factor"] for f in against[:6]) or "none clear"),
        "Season ranking was NOT used for this matchup",
    ]

    sample = pair.sample_size + a.starts + b.starts
    conf = 0.5 * pair.confidence + 0.5 * (40.0 + len(usable) * 4.0)
    dq = data_quality_label(
        missing_rate=1.0 - len(usable) / max(1, len(factors)),
        sample_size=sample,
    )

    return MarketAnswer(
        market="MATCHUP",
        prediction={
            "horse_a": a.horse_name,
            "horse_b": b.horse_name,
            "probability_a_finishes_ahead": round(p_a, 4),
            "probability_b_finishes_ahead": round(p_b, 4),
            "expected_margin": round(pair.expected_margin, 4),
            "factors": factors,
            "pairwise": pair.to_dict(),
        },
        confidence=confidence_band(conf),
        confidence_score=conf,
        reasons=reasons,
        metrics_used=list(MATCHUP_FACTORS) + ["historical_h2h", "win_strength"],
        sample_size=sample,
        data_quality=dq,
        applicable_market="Direct Matchup",
        details={"factor_edge_for_a": round(factor_edge, 4)},
    )


_YA_SPLIT = re.compile(
    r"\s+(?:یا|or|vs\.?|versus)\s+",
    re.IGNORECASE,
)


def parse_matchup_query(text: str) -> tuple[str, str] | None:
    """Parse «A یا B» / «A vs B» into two name fragments."""
    if not text or not text.strip():
        return None
    parts = _YA_SPLIT.split(text.strip())
    if len(parts) != 2:
        return None
    left, right = parts[0].strip(" ؟?"), parts[1].strip(" ؟?")
    if not left or not right:
        return None
    return left, right


def resolve_horse_by_name(session: Session, name: str) -> WhHorse | None:
    from src.warehouse.fuzzy import similarity

    target = normalize_name(name)
    horses = list(session.scalars(select(WhHorse)).all())
    # Exact normalized
    for h in horses:
        if normalize_name(h.name) == target:
            return h
    # Best fuzzy
    best: WhHorse | None = None
    best_score = 0.0
    for h in horses:
        sc = similarity(h.name, name)
        if sc > best_score:
            best_score = sc
            best = h
    if best is not None and best_score >= 0.72:
        return best
    return None
