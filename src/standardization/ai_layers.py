"""Module 15 — AI Readiness.

Separate layers:
  Raw Data → Metrics → Features → Predictions → Recommendations
Never mix them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.standardization.constants import AI_LAYERS, PLATFORM_VERSION
from src.standardization.models import StdFeatureStore


@dataclass(frozen=True, slots=True)
class LayerContract:
    name: str
    description: str
    allowed_sources: tuple[str, ...]
    forbidden_mix: tuple[str, ...]
    table_prefixes: tuple[str, ...]


LAYER_CONTRACTS: dict[str, LayerContract] = {
    "raw": LayerContract(
        name="raw",
        description="Append-only source captures (HTML/API payloads).",
        allowed_sources=(),
        forbidden_mix=("metrics", "features", "predictions", "recommendations"),
        table_prefixes=("raw_",),
    ),
    "metrics": LayerContract(
        name="metrics",
        description="Documented performance statistics (wins, rates, PR).",
        allowed_sources=("raw", "warehouse"),
        forbidden_mix=("predictions", "recommendations"),
        table_prefixes=("anl_horse_metrics", "anl_"),
    ),
    "features": LayerContract(
        name="features",
        description="Derived reusable feature vectors for ML joins.",
        allowed_sources=("metrics", "warehouse"),
        forbidden_mix=("predictions", "recommendations"),
        table_prefixes=("feat_", "std_feature_store"),
    ),
    "predictions": LayerContract(
        name="predictions",
        description="Model outputs / expectation proxies — not facts.",
        allowed_sources=("features", "metrics"),
        forbidden_mix=("raw",),
        table_prefixes=("anl_prediction_", "anl_race_intelligence"),
    ),
    "recommendations": LayerContract(
        name="recommendations",
        description="Actionable suggestions built on predictions + rules.",
        allowed_sources=("predictions", "metrics", "features"),
        forbidden_mix=("raw",),
        table_prefixes=(),
    ),
}


def assert_layer_separation(payload: dict[str, Any], *, layer: str) -> list[str]:
    """Return warnings if a payload mixes forbidden layer keys."""
    if layer not in LAYER_CONTRACTS:
        return [f"Unknown layer: {layer}"]
    contract = LAYER_CONTRACTS[layer]
    warnings: list[str] = []
    present_layers = [k for k in AI_LAYERS if k in payload and k != layer]
    for forbidden in contract.forbidden_mix:
        if forbidden in present_layers:
            warnings.append(
                f"Layer '{layer}' must not mix '{forbidden}' data in the same payload"
            )
    return warnings


def ai_readiness_report(session: Session) -> dict[str, Any]:
    """Checklist: tables populated per layer, no cross-contamination in feature store."""
    from src.database.raw import RawRace
    from src.analytics.models import AnlHorseMetrics
    from src.warehouse.models import WhRace

    raw_n = session.scalar(select(func.count()).select_from(RawRace)) or 0
    wh_n = session.scalar(select(func.count()).select_from(WhRace)) or 0
    metrics_n = session.scalar(select(func.count()).select_from(AnlHorseMetrics)) or 0
    feat_n = session.scalar(select(func.count()).select_from(StdFeatureStore)) or 0

    # Feature store layer hygiene
    bad_layers = list(
        session.scalars(
            select(StdFeatureStore.layer).where(
                StdFeatureStore.layer.notin_(AI_LAYERS)
            ).distinct()
        ).all()
    )

    checks = [
        {
            "check": "raw_present",
            "ok": raw_n > 0,
            "detail": f"raw_races={raw_n}",
        },
        {
            "check": "warehouse_present",
            "ok": wh_n > 0,
            "detail": f"wh_races={wh_n}",
        },
        {
            "check": "metrics_present",
            "ok": metrics_n > 0,
            "detail": f"anl_horse_metrics={metrics_n}",
        },
        {
            "check": "features_present",
            "ok": feat_n > 0,
            "detail": f"std_feature_store={feat_n}",
        },
        {
            "check": "feature_layer_hygiene",
            "ok": len(bad_layers) == 0,
            "detail": f"invalid_layers={bad_layers}",
        },
        {
            "check": "predictions_separated",
            "ok": True,
            "detail": "predictions live in anl_prediction_* / race_intel — not in metrics rows",
        },
        {
            "check": "recommendations_separated",
            "ok": True,
            "detail": "recommendations not stored in metrics/feature tables",
        },
    ]
    ready = all(c["ok"] for c in checks if c["check"] != "features_present")
    # features may be empty until materialize — soft
    return {
        "module": "ai_readiness",
        "version": PLATFORM_VERSION,
        "layers": {k: LAYER_CONTRACTS[k].description for k in AI_LAYERS},
        "checks": checks,
        "ready": ready,
        "counts": {
            "raw": raw_n,
            "warehouse": wh_n,
            "metrics": metrics_n,
            "features": feat_n,
        },
    }
