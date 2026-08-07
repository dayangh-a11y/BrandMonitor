"""VALUE MARKET — stronger than public perception."""

from __future__ import annotations

from src.markets.answer import MarketAnswer, confidence_band, data_quality_label
from src.markets.scoring import RunnerContext, public_perception_score
from src.markets.win import win_strength


def value_score(runner: RunnerContext, field: list[RunnerContext]) -> tuple[float | None, dict]:
    model = win_strength(runner)
    perception = public_perception_score(runner, field)
    if perception is None:
        return None, {"model_strength": model, "perception": None}
    # Value = model − perception (positive ⇒ underbet / underrated by public)
    gap = model - perception
    return gap, {"model_strength": round(model, 3), "perception": round(perception, 3), "gap": round(gap, 3)}


def analyze_value_market(field: list[RunnerContext]) -> MarketAnswer:
    if not field:
        return MarketAnswer(
            market="VALUE",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Empty field"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="Value Market",
        )

    rows = []
    for r in field:
        score, detail = value_score(r, field)
        rows.append(
            {
                "horse": r.horse_name,
                "horse_id": r.horse_id,
                "value_score": round(score, 3) if score is not None else None,
                "confidence": confidence_band(50 + (score or 0) / 2) if score is not None else "Very Low",
                "reasons": [
                    f"Model strength {detail.get('model_strength')} vs perception {detail.get('perception')}",
                    "Positive value ⇒ model stronger than public rating/odds",
                ]
                if score is not None
                else ["Missing public perception (no odds/rating)"],
                "detail": detail,
            }
        )
    ranked = sorted(
        [x for x in rows if x["value_score"] is not None],
        key=lambda x: x["value_score"],
        reverse=True,
    )
    sample = sum(r.starts for r in field)
    covered = sum(1 for x in rows if x["value_score"] is not None)
    dq = data_quality_label(
        missing_rate=1.0 - covered / max(1, len(field)), sample_size=sample
    )
    best = ranked[0] if ranked else None
    conf = 55.0 + min(30.0, abs(best["value_score"]) if best else 0) if best else 20.0

    return MarketAnswer(
        market="VALUE",
        prediction={
            "top_value": best,
            "ranked": ranked,
        },
        confidence=confidence_band(conf),
        confidence_score=conf,
        reasons=[
            f"Top value: {best['horse']} (score={best['value_score']})"
            if best
            else "No value candidates with perception data",
            "Value Score = Win-model strength − public perception (odds or source_rating)",
            "Season leaderboard is NOT used as the value score",
        ],
        metrics_used=["win_strength", "odds", "source_rating", "form_score_5", "win_rate"],
        sample_size=sample,
        data_quality=dq,
        applicable_market="Value Market",
        warnings=["Perception missing for some runners"] if covered < len(field) else [],
    )
