"""Load configurable scoring weights."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_WEIGHTS_PATH = Path("config/scoring_weights.yaml")

REQUIRED_DIMENSIONS = (
    "customer_satisfaction",
    "delivery_speed",
    "service_coverage",
    "pricing",
    "service_variety",
    "transparency",
    "complaint_rate",
    "branch_quality",
)


def load_scoring_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path or DEFAULT_WEIGHTS_PATH)
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    weights = dict(data.get("weights") or {})
    missing = [k for k in REQUIRED_DIMENSIONS if k not in weights]
    if missing:
        raise ValueError(f"scoring weights missing dimensions: {missing}")
    total = sum(float(weights[k]) for k in REQUIRED_DIMENSIONS)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"scoring weights must sum to 1.0, got {total:.6f}")
    return data


def normalized_weights(cfg: dict[str, Any] | None = None) -> dict[str, float]:
    cfg = cfg or load_scoring_config()
    return {k: float(cfg["weights"][k]) for k in REQUIRED_DIMENSIONS}
