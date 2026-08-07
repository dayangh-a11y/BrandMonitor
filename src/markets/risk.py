"""RISK MARKET — risk, reliability, variance, consistency, volatility."""

from __future__ import annotations

from src.markets.answer import MarketAnswer, confidence_band, data_quality_label
from src.markets.scoring import RunnerContext, reliability_from_consistency


def risk_profile(runner: RunnerContext) -> dict:
    consistency = runner.consistency_score
    reliability = reliability_from_consistency(consistency, runner.starts)
    # Variance proxy: inverse consistency
    variance = None if consistency is None else max(0.0, 100.0 - float(consistency))
    # Volatility: form swings + low starts
    volatility = 50.0
    if variance is not None:
        volatility = 0.6 * variance + 0.4 * max(0.0, 40.0 - runner.starts * 4.0)
    risk = 0.5 * (variance or 50.0) + 0.3 * volatility + 0.2 * (100.0 - reliability)
    return {
        "horse": runner.horse_name,
        "horse_id": runner.horse_id,
        "risk_score": round(risk, 3),
        "reliability": round(reliability, 3),
        "variance": round(variance, 3) if variance is not None else None,
        "consistency": consistency,
        "expected_volatility": round(volatility, 3),
        "starts": runner.starts,
    }


def analyze_risk_market(field: list[RunnerContext]) -> MarketAnswer:
    if not field:
        return MarketAnswer(
            market="RISK",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Empty field"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="Risk Market",
        )

    profiles = [risk_profile(r) for r in field]
    safest = sorted(profiles, key=lambda p: p["risk_score"])[0]
    riskiest = sorted(profiles, key=lambda p: p["risk_score"], reverse=True)[0]
    sample = sum(r.starts for r in field)
    missing = sum(1 for r in field if r.consistency_score is None)
    dq = data_quality_label(missing_rate=missing / max(1, len(field)), sample_size=sample)
    conf = 50.0 + min(30.0, sample / 5.0) - missing * 5.0

    return MarketAnswer(
        market="RISK",
        prediction={
            "safest": safest,
            "riskiest": riskiest,
            "field": sorted(profiles, key=lambda p: p["risk_score"]),
        },
        confidence=confidence_band(conf),
        confidence_score=conf,
        reasons=[
            f"Safest: {safest['horse']} (risk={safest['risk_score']})",
            f"Riskiest: {riskiest['horse']} (risk={riskiest['risk_score']})",
            "Risk = 0.5·variance + 0.3·volatility + 0.2·(100−reliability)",
            "Win/Place rankings are not reused for risk scoring",
        ],
        metrics_used=["consistency_score", "starts", "reliability", "variance", "volatility"],
        sample_size=sample,
        data_quality=dq,
        applicable_market="Risk Market",
    )
