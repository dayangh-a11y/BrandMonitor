"""Load and maintain the dedicated Iran Post official profile."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROFILE_PATH = Path(
    os.getenv("IRAN_POST_PROFILE_PATH", "config/iran_post/official_profile.yaml")
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_official_profile(path: str | Path | None = None) -> dict[str, Any]:
    profile_path = Path(path or DEFAULT_PROFILE_PATH)
    if not profile_path.exists():
        raise FileNotFoundError(f"Iran Post profile not found: {profile_path}")
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    data["_loaded_from"] = str(profile_path)
    data["_loaded_at"] = utcnow()
    data["role"] = data.get("role") or "national_postal_operator"
    data["treat_as_regular_carrier"] = bool(
        (data.get("comparison_policy") or {}).get("treat_as_regular_carrier", False)
    )
    return data


def profile_public_view(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalized public structure maintained by the Iran Post module."""
    p = profile or load_official_profile()
    return {
        "slug": p.get("slug") or "post",
        "role": p.get("role"),
        "name": p.get("name") or "Iran Post",
        "name_fa": p.get("name_fa") or "",
        "website": p.get("website"),
        "official_services": p.get("official_services") or [],
        "official_pricing": p.get("official_pricing") or {},
        "official_delivery_estimates": p.get("official_delivery_estimates") or {},
        "service_coverage": p.get("service_coverage") or {},
        "weight_limits": p.get("weight_limits") or {},
        "size_limits": p.get("size_limits") or {},
        "insurance_rules": p.get("insurance_rules") or {},
        "tracking": p.get("tracking") or {},
        "working_hours": p.get("working_hours") or {},
        "customer_support": p.get("customer_support") or {},
        "comparison_policy": p.get("comparison_policy") or {},
        "meta": {
            "loaded_from": p.get("_loaded_from"),
            "loaded_at": p.get("_loaded_at"),
            "treat_as_regular_carrier": p.get("treat_as_regular_carrier", False),
        },
    }
