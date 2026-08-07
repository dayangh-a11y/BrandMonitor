"""PLACE MARKET — distinct scoring model optimized for podium / top-N."""

from __future__ import annotations

from src.markets.answer import MarketAnswer, confidence_band, data_quality_label
from src.markets.scoring import RunnerContext, softmax_probs, top_k_probability


def place_strength(runner: RunnerContext) -> float:
    """Place model: place rate, consistency, avg finish, form — not pure win rate."""
    parts: list[tuple[float, float]] = []
    if runner.place_rate is not None:
        parts.append((0.30, float(runner.place_rate) * 100.0))
    if runner.consistency_score is not None:
        parts.append((0.20, float(runner.consistency_score)))
    if runner.avg_finish is not None:
        # lower finish better → map to 0..100
        parts.append((0.18, max(0.0, 100.0 - 12.0 * (float(runner.avg_finish) - 1.0))))
    if runner.form_score_5 is not None:
        parts.append((0.17, float(runner.form_score_5)))
    pr = runner.sex_adjusted_pr if runner.sex_adjusted_pr is not None else runner.performance_rating
    if pr is not None:
        parts.append((0.10, float(pr)))
    if runner.win_rate is not None:
        parts.append((0.05, float(runner.win_rate) * 100.0))  # minor
    if not parts:
        return 35.0
    tw = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / tw


def analyze_place_market(field: list[RunnerContext]) -> MarketAnswer:
    if not field:
        return MarketAnswer(
            market="PLACE",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Empty field"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="Place Market",
        )

    scores = {r.horse_id: place_strength(r) for r in field}
    base = softmax_probs(scores, temperature=11.0)
    top2 = top_k_probability(base, 2)
    top3 = top_k_probability(base, 3)
    top5 = top_k_probability(base, 5)
    by_id = {r.horse_id: r for r in field}

    ranked = sorted(field, key=lambda r: top3[r.horse_id], reverse=True)
    best = ranked[0]
    sample = sum(r.starts for r in field)
    missing = sum(1 for r in field if r.place_rate is None and r.consistency_score is None)
    dq = data_quality_label(missing_rate=missing / max(1, len(field)), sample_size=sample)
    conf_score = 35.0 + 45.0 * top3[best.horse_id] + min(20.0, sample / 12.0)

    prediction = {
        "best_place_candidate": {
            "horse": best.horse_name,
            "horse_id": best.horse_id,
            "top2_probability": round(top2[best.horse_id], 4),
            "top3_probability": round(top3[best.horse_id], 4),
            "top5_probability": round(top5[best.horse_id], 4),
        },
        "podium_confidence": confidence_band(conf_score),
        "field": [
            {
                "horse": r.horse_name,
                "top2_probability": round(top2[r.horse_id], 4),
                "top3_probability": round(top3[r.horse_id], 4),
                "top5_probability": round(top5[r.horse_id], 4),
                "place_strength": round(scores[r.horse_id], 3),
            }
            for r in ranked
        ],
    }

    return MarketAnswer(
        market="PLACE",
        prediction=prediction,
        confidence=confidence_band(conf_score),
        confidence_score=conf_score,
        reasons=[
            f"Place model tops {best.horse_name} for podium likelihood "
            f"(p_top3={top3[best.horse_id]:.1%})",
            "Weights: place_rate 30%, consistency 20%, avg_finish 18%, form 17%, PR 10%, win_rate 5%",
            "Win Market model is NOT used here",
        ],
        metrics_used=[
            "place_rate",
            "consistency_score",
            "avg_finish",
            "form_score_5",
            "performance_rating",
            "win_rate",
        ],
        sample_size=sample,
        data_quality=dq,
        applicable_market="Place Market",
        details={"scores": {by_id[k].horse_name: round(v, 3) for k, v in scores.items()}},
    )
