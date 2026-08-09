"""WIN MARKET — distinct scoring model (not reused for place/H2H/etc.)."""

from __future__ import annotations

from typing import Any

from src.markets.answer import MarketAnswer, confidence_band, data_quality_label
from src.markets.scoring import RunnerContext, softmax_probs, top_k_probability


def win_strength(runner: RunnerContext) -> float:
    """Win-market score: emphasizes win rate, form, PR, speed — not place."""
    parts: list[tuple[float, float]] = []
    pr = runner.sex_adjusted_pr if runner.sex_adjusted_pr is not None else runner.performance_rating
    if pr is not None:
        parts.append((0.28, float(pr)))
    if runner.win_rate is not None:
        parts.append((0.32, float(runner.win_rate) * 100.0))
    if runner.form_score_5 is not None:
        parts.append((0.22, float(runner.form_score_5)))
    if runner.speed_index is not None:
        parts.append((0.10, max(0.0, float(runner.speed_index) - 50.0)))
    if runner.source_rating is not None and runner.source_rating > 0:
        parts.append((0.08, min(100.0, (float(runner.source_rating) - 20.0) * 0.9)))
    if not parts:
        return 35.0
    tw = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / tw


def analyze_win_market(field: list[RunnerContext]) -> MarketAnswer:
    if not field:
        return MarketAnswer(
            market="WIN",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Empty field"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="Win Market",
            warnings=["No runners"],
        )

    scores = {r.horse_id: win_strength(r) for r in field}
    win_probs = softmax_probs(scores, temperature=10.0)
    top3_probs = top_k_probability(win_probs, 3)
    by_id = {r.horse_id: r for r in field}

    ranked = sorted(field, key=lambda r: win_probs[r.horse_id], reverse=True)
    winner = ranked[0]
    top3 = ranked[:3]

    missing = sum(
        1
        for r in field
        if r.performance_rating is None and r.win_rate is None and r.form_score_5 is None
    )
    sample = sum(r.starts for r in field)
    dq = data_quality_label(missing_rate=missing / max(1, len(field)), sample_size=sample)
    conf_score = 40.0 + 40.0 * win_probs[winner.horse_id] + min(20.0, sample / 10.0)
    if dq in {"poor", "insufficient"}:
        conf_score *= 0.6

    prediction = {
        "winner": {
            "horse_id": winner.horse_id,
            "horse": winner.horse_name,
            "winning_probability": round(win_probs[winner.horse_id], 4),
            "win_strength": round(scores[winner.horse_id], 3),
        },
        "top_3": [
            {
                "horse_id": r.horse_id,
                "horse": r.horse_name,
                "winning_probability": round(win_probs[r.horse_id], 4),
                "top3_probability": round(top3_probs[r.horse_id], 4),
            }
            for r in top3
        ],
        "winning_confidence": confidence_band(conf_score),
        "field_probabilities": {
            by_id[hid].horse_name: round(p, 4) for hid, p in win_probs.items()
        },
    }

    return MarketAnswer(
        market="WIN",
        prediction=prediction,
        confidence=confidence_band(conf_score),
        confidence_score=conf_score,
        reasons=[
            f"Win model favors {winner.horse_name} "
            f"(p_win={win_probs[winner.horse_id]:.1%}, strength={scores[winner.horse_id]:.1f})",
            "Scoring weights: win_rate 32%, PR 28%, form5 22%, speed 10%, rating 8%",
            "Place-rate and earnings are intentionally excluded from the Win model",
        ],
        metrics_used=["win_rate", "performance_rating", "form_score_5", "speed_index", "source_rating"],
        sample_size=sample,
        data_quality=dq,
        applicable_market="Win Market",
        warnings=["Sparse metrics for some runners"] if missing else [],
        details={"scores": {by_id[k].horse_name: round(v, 3) for k, v in scores.items()}},
    )
