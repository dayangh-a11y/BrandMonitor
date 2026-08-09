"""
HEAD-TO-HEAD / PAIRWISE ENGINE.

For every race: complete pairwise comparison matrix.
Uses historical same-race finishes + current relative strength.
Never substitutes season ranking for pairwise probs.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.markets.answer import MarketAnswer, confidence_band, data_quality_label
from src.markets.scoring import RunnerContext, softmax_probs
from src.markets.win import win_strength
from src.warehouse.models import WhRaceResult


@dataclass
class PairwiseRecord:
    horse_a_id: int
    horse_a_name: str
    horse_b_id: int
    horse_b_name: str
    a_ahead_prob: float
    b_ahead_prob: float
    expected_finish_gap: float  # A finish − B finish expectation (neg ⇒ A better)
    historical_h2h: dict[str, Any]
    distance_h2h: dict[str, Any] | None
    track_h2h: dict[str, Any] | None
    trainer_h2h: dict[str, Any] | None
    jockey_h2h: dict[str, Any] | None
    confidence: float
    win_probability_a: float
    expected_margin: float
    sample_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "horse_a": self.horse_a_name,
            "horse_a_id": self.horse_a_id,
            "horse_b": self.horse_b_name,
            "horse_b_id": self.horse_b_id,
            "a_finishes_ahead_of_b": round(self.a_ahead_prob, 4),
            "b_finishes_ahead_of_a": round(self.b_ahead_prob, 4),
            "expected_finishing_gap": round(self.expected_finish_gap, 4),
            "expected_margin": round(self.expected_margin, 4),
            "win_probability_a_in_pair": round(self.win_probability_a, 4),
            "historical_h2h": self.historical_h2h,
            "distance_h2h": self.distance_h2h,
            "track_h2h": self.track_h2h,
            "trainer_h2h": self.trainer_h2h,
            "jockey_h2h": self.jockey_h2h,
            "confidence": round(self.confidence, 2),
            "sample_size": self.sample_size,
        }


def _h2h_summary(meets: list[tuple[int, int]]) -> dict[str, Any]:
    """meets: list of (finish_a, finish_b) in same races."""
    if not meets:
        return {"meetings": 0, "a_ahead": 0, "b_ahead": 0, "a_ahead_rate": None}
    a_ahead = sum(1 for fa, fb in meets if fa < fb)
    b_ahead = sum(1 for fa, fb in meets if fb < fa)
    ties = len(meets) - a_ahead - b_ahead
    return {
        "meetings": len(meets),
        "a_ahead": a_ahead,
        "b_ahead": b_ahead,
        "ties": ties,
        "a_ahead_rate": round(a_ahead / len(meets), 4) if meets else None,
        "avg_finish_gap": round(
            sum(fa - fb for fa, fb in meets) / len(meets), 4
        ),
    }


def load_historical_pair_meetings(
    session: Session,
    horse_a: int,
    horse_b: int,
    *,
    racecourse_code: str | None = None,
    distance: int | None = None,
    distance_tol: int = 100,
) -> list[tuple[int, int, int | None, str | None]]:
    """
    Return list of (finish_a, finish_b, distance, racecourse_code) for shared races.
    """
    from src.warehouse.models import WhRace

    a_rows = session.scalars(
        select(WhRaceResult).where(
            WhRaceResult.horse_id == horse_a,
            WhRaceResult.finish_position.is_not(None),
            WhRaceResult.finish_position > 0,
        )
    ).all()
    b_by_race = {
        r.race_id: r
        for r in session.scalars(
            select(WhRaceResult).where(
                WhRaceResult.horse_id == horse_b,
                WhRaceResult.finish_position.is_not(None),
                WhRaceResult.finish_position > 0,
            )
        ).all()
    }
    races = {
        r.id: r
        for r in session.scalars(
            select(WhRace).where(
                WhRace.id.in_(list({x.race_id for x in a_rows}) or [-1])
            )
        ).all()
    } if a_rows else {}
    out: list[tuple[int, int, int | None, str | None]] = []
    for ar in a_rows:
        br = b_by_race.get(ar.race_id)
        if br is None:
            continue
        race = races.get(ar.race_id)
        code = race.racecourse_code if race else None
        dist = race.distance if race else None
        if racecourse_code and code != racecourse_code:
            continue
        if distance is not None and dist is not None:
            if abs(dist - distance) > distance_tol:
                continue
        out.append((int(ar.finish_position), int(br.finish_position), dist, code))
    return out


def pairwise_compare(
    a: RunnerContext,
    b: RunnerContext,
    *,
    historical: list[tuple[int, int, int | None, str | None]] | None = None,
    race_distance: int | None = None,
    race_track: str | None = None,
) -> PairwiseRecord:
    hist = historical or []
    all_meets = [(fa, fb) for fa, fb, _, _ in hist]
    hist_sum = _h2h_summary(all_meets)

    dist_meets = [
        (fa, fb)
        for fa, fb, d, _ in hist
        if race_distance is not None and d is not None and abs(d - race_distance) <= 100
    ]
    track_meets = [
        (fa, fb) for fa, fb, _, c in hist if race_track and c == race_track
    ]

    # Model prior from relative win strengths (pair-normalized)
    sa, sb = win_strength(a), win_strength(b)
    pair_probs = softmax_probs({a.horse_id: sa, b.horse_id: sb}, temperature=8.0)
    model_a = pair_probs[a.horse_id]

    # Blend with historical H2H when available
    if hist_sum["meetings"] and hist_sum["a_ahead_rate"] is not None:
        w_hist = min(0.55, 0.15 + 0.08 * hist_sum["meetings"])
        a_ahead = (1 - w_hist) * model_a + w_hist * float(hist_sum["a_ahead_rate"])
    else:
        a_ahead = model_a
        w_hist = 0.0

    # Distance / track tilts
    for meets, weight in ((dist_meets, 0.08), (track_meets, 0.08)):
        if len(meets) >= 2:
            rate = sum(1 for fa, fb in meets if fa < fb) / len(meets)
            a_ahead = (1 - weight) * a_ahead + weight * rate

    a_ahead = max(0.02, min(0.98, a_ahead))
    b_ahead = 1.0 - a_ahead

    # Expected finish gap: negative ⇒ A finishes ahead
    # Use historical avg gap when present else model differential
    if hist_sum["meetings"]:
        exp_gap = float(hist_sum["avg_finish_gap"])
    else:
        exp_gap = (sb - sa) / 20.0  # rough positions

    conf = 35.0 + 40.0 * abs(a_ahead - 0.5) * 2 + min(25.0, hist_sum["meetings"] * 5.0)

    trainer_h2h = None
    if a.trainer and b.trainer and a.trainer == b.trainer:
        trainer_h2h = {"same_trainer": True, "trainer": a.trainer}
    elif a.trainer or b.trainer:
        trainer_h2h = {"same_trainer": False, "a": a.trainer, "b": b.trainer}

    jockey_h2h = None
    if a.jockey and b.jockey and a.jockey == b.jockey:
        jockey_h2h = {"same_jockey": True, "jockey": a.jockey}
    elif a.jockey or b.jockey:
        jockey_h2h = {"same_jockey": False, "a": a.jockey, "b": b.jockey}

    return PairwiseRecord(
        horse_a_id=a.horse_id,
        horse_a_name=a.horse_name,
        horse_b_id=b.horse_id,
        horse_b_name=b.horse_name,
        a_ahead_prob=a_ahead,
        b_ahead_prob=b_ahead,
        expected_finish_gap=exp_gap,
        historical_h2h=hist_sum,
        distance_h2h=_h2h_summary(dist_meets) if dist_meets else None,
        track_h2h=_h2h_summary(track_meets) if track_meets else None,
        trainer_h2h=trainer_h2h,
        jockey_h2h=jockey_h2h,
        confidence=conf,
        win_probability_a=a_ahead,
        expected_margin=abs(exp_gap),
        sample_size=hist_sum["meetings"],
    )


def build_pairwise_matrix(
    field: list[RunnerContext],
    *,
    session: Session | None = None,
    race_distance: int | None = None,
    race_track: str | None = None,
) -> list[PairwiseRecord]:
    pairs: list[PairwiseRecord] = []
    for i, a in enumerate(field):
        for b in field[i + 1 :]:
            hist = None
            if session is not None:
                hist = load_historical_pair_meetings(
                    session,
                    a.horse_id,
                    b.horse_id,
                    racecourse_code=None,
                    distance=race_distance,
                )
            pairs.append(
                pairwise_compare(
                    a,
                    b,
                    historical=hist,
                    race_distance=race_distance,
                    race_track=race_track,
                )
            )
    return pairs


def analyze_h2h_market(
    field: list[RunnerContext],
    *,
    session: Session | None = None,
    race_distance: int | None = None,
    race_track: str | None = None,
) -> MarketAnswer:
    if len(field) < 2:
        return MarketAnswer(
            market="H2H",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Need at least 2 runners for pairwise matrix"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="Head-to-Head Market",
        )

    matrix = build_pairwise_matrix(
        field, session=session, race_distance=race_distance, race_track=race_track
    )
    sample = sum(p.sample_size for p in matrix)
    avg_conf = sum(p.confidence for p in matrix) / len(matrix)
    dq = data_quality_label(
        missing_rate=0.0 if sample > 0 else 0.5,
        sample_size=max(sample, len(field)),
    )

    # Summarize strongest edges
    edges = sorted(matrix, key=lambda p: abs(p.a_ahead_prob - 0.5), reverse=True)[:5]

    return MarketAnswer(
        market="H2H",
        prediction={
            "pairs": len(matrix),
            "matrix": [p.to_dict() for p in matrix],
            "strongest_edges": [p.to_dict() for p in edges],
        },
        confidence=confidence_band(avg_conf),
        confidence_score=avg_conf,
        reasons=[
            f"Built complete pairwise matrix ({len(matrix)} pairs)",
            "Each pair blends relative win-strength with historical same-race H2H",
            "Includes distance/track H2H when sample ≥ 2",
            "Season ranking is not used as pairwise probability",
        ],
        metrics_used=[
            "win_strength",
            "historical_h2h",
            "distance_h2h",
            "track_h2h",
            "trainer",
            "jockey",
        ],
        sample_size=sample,
        data_quality=dq,
        applicable_market="Head-to-Head Market",
    )
