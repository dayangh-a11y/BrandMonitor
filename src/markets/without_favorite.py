"""WITHOUT FAVORITE MARKET — exclude strongest favorite, rerank remaining."""

from __future__ import annotations

from src.markets.answer import MarketAnswer, confidence_band, data_quality_label
from src.markets.scoring import RunnerContext, detect_favorite
from src.markets.win import analyze_win_market, win_strength


def analyze_without_favorite(field: list[RunnerContext]) -> MarketAnswer:
    favorite, fav_how = detect_favorite(field)
    if favorite is None or len(field) < 2:
        return MarketAnswer(
            market="WITHOUT_FAVORITE",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Need a detectable favorite and at least 2 runners"],
            metrics_used=["source_rating", "odds", "win_strength"],
            sample_size=sum(r.starts for r in field),
            data_quality="insufficient",
            applicable_market="Without Favorite Market",
            warnings=["Cannot exclude favorite"],
        )

    remaining = [r for r in field if r.horse_id != favorite.horse_id]
    # Re-score with Win model on remaining only (market-specific, not season ranking)
    sub = analyze_win_market(remaining)
    ranked = sorted(remaining, key=lambda r: win_strength(r), reverse=True)
    top = ranked[:3]
    sample = sum(r.starts for r in remaining)
    dq = data_quality_label(missing_rate=0.0, sample_size=sample)

    prediction = {
        "excluded_favorite": {
            "horse": favorite.horse_name,
            "horse_id": favorite.horse_id,
            "detection": fav_how,
            "odds": favorite.odds,
            "source_rating": favorite.source_rating,
        },
        "best_remaining": {
            "horse": top[0].horse_name if top else None,
            "horse_id": top[0].horse_id if top else None,
            "win_strength": round(win_strength(top[0]), 3) if top else None,
        },
        "second_strongest": {
            "horse": top[1].horse_name if len(top) > 1 else None,
            "horse_id": top[1].horse_id if len(top) > 1 else None,
        },
        "third_strongest": {
            "horse": top[2].horse_name if len(top) > 2 else None,
            "horse_id": top[2].horse_id if len(top) > 2 else None,
        },
        "remaining_win_market": sub.prediction,
    }

    conf = max(0.0, sub.confidence_score - 5.0)
    return MarketAnswer(
        market="WITHOUT_FAVORITE",
        prediction=prediction,
        confidence=confidence_band(conf),
        confidence_score=conf,
        reasons=[
            f"Detected favorite {favorite.horse_name} via {fav_how} and excluded them",
            f"Remaining field rescored with Win Market model ({len(remaining)} runners)",
            f"Best remaining: {top[0].horse_name}" if top else "No remaining runners",
        ],
        metrics_used=["odds", "source_rating", "win_strength", *sub.metrics_used],
        sample_size=sample,
        data_quality=dq,
        applicable_market="Without Favorite Market",
        warnings=list(sub.warnings),
        details={"favorite_id": favorite.horse_id},
    )
