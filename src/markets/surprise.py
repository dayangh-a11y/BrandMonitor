"""SURPRISE MARKET — dark / hidden / improved / underrated / overrated."""

from __future__ import annotations

from src.markets.answer import MarketAnswer, confidence_band, data_quality_label
from src.markets.scoring import RunnerContext, public_perception_score
from src.markets.win import win_strength


def analyze_surprise_market(field: list[RunnerContext]) -> MarketAnswer:
    if not field:
        return MarketAnswer(
            market="SURPRISE",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Empty field"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="Surprise Market",
        )

    rows = []
    for r in field:
        model = win_strength(r)
        perception = public_perception_score(r, field)
        gap = (model - perception) if perception is not None else None
        rows.append(
            {
                "horse": r.horse_name,
                "horse_id": r.horse_id,
                "model": round(model, 3),
                "perception": round(perception, 3) if perception is not None else None,
                "gap": round(gap, 3) if gap is not None else None,
                "improvement_trend": r.improvement_trend,
                "form_score_5": r.form_score_5,
                "starts": r.starts,
                "source_rating": r.source_rating,
            }
        )

    with_gap = [x for x in rows if x["gap"] is not None]
    underrated = sorted(with_gap, key=lambda x: x["gap"], reverse=True)
    overrated = sorted(with_gap, key=lambda x: x["gap"])
    improved = sorted(
        [x for x in rows if x["improvement_trend"] is not None],
        key=lambda x: x["improvement_trend"] or 0,
        reverse=True,
    )
    # Dark horse: solid model, low perception / low rating, limited spotlight
    dark = sorted(
        with_gap,
        key=lambda x: (x["gap"], -(x["perception"] or 0)),
        reverse=True,
    )
    # Hidden: improving + not favorite perception
    hidden = [
        x
        for x in rows
        if (x["improvement_trend"] or 0) > 0
        and (x["perception"] is None or x["perception"] < 55)
    ]
    hidden = sorted(hidden, key=lambda x: x["improvement_trend"] or 0, reverse=True)

    sample = sum(r.starts for r in field)
    dq = data_quality_label(
        missing_rate=1.0 - len(with_gap) / max(1, len(field)), sample_size=sample
    )
    conf = 45.0 + min(35.0, len(with_gap) * 4.0)

    prediction = {
        "dark_horse": dark[0] if dark else None,
        "hidden_horse": hidden[0] if hidden else (dark[1] if len(dark) > 1 else None),
        "most_improved_horse": improved[0] if improved else None,
        "most_underrated_horse": underrated[0] if underrated else None,
        "most_overrated_horse": overrated[0] if overrated else None,
    }

    return MarketAnswer(
        market="SURPRISE",
        prediction=prediction,
        confidence=confidence_band(conf),
        confidence_score=conf,
        reasons=[
            "Dark/underrated: high model−perception gap",
            "Overrated: high perception relative to model strength",
            "Most improved: highest improvement_trend",
            "Hidden: improving with low public perception",
            "Does not reuse Season Best ranking",
        ],
        metrics_used=[
            "win_strength",
            "public_perception",
            "improvement_trend",
            "form_score_5",
            "source_rating",
            "odds",
        ],
        sample_size=sample,
        data_quality=dq,
        applicable_market="Surprise Market",
    )
