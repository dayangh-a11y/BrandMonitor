"""Official company dataset loader (separate from reviews)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_OFFICIAL_PATH = Path("config/official_companies.yaml")


def load_official_companies(path: str | Path | None = None) -> list[dict[str, Any]]:
    cfg_path = Path(path or DEFAULT_OFFICIAL_PATH)
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    companies = list(data.get("companies") or [])
    if not companies:
        raise ValueError(f"No companies in {cfg_path}")
    for c in companies:
        for key in ("slug", "name", "services"):
            if key not in c:
                raise ValueError(f"Official company missing `{key}`: {c.get('name')}")
    return companies


def official_by_slug(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    return {c["slug"]: c for c in load_official_companies(path)}


def name_to_slug(name: str) -> str | None:
    mapping = {
        "tipax": "tipax",
        "تیپاکس": "tipax",
        "chapar": "chapar",
        "چاپار": "chapar",
        "post": "post",
        "پست": "post",
        "پست ایران": "post",
        "شرکت ملی پست": "post",
        "mahex": "mahex",
        "ماهکس": "mahex",
        "alopeyk": "alopeyk",
        "الو پیک": "alopeyk",
        "الوپیک": "alopeyk",
        "pishro": "pishro",
        "پیشرو": "pishro",
    }
    key = (name or "").strip().lower()
    if key in mapping:
        return mapping[key]
    # fuzzy contains
    for k, slug in mapping.items():
        if k in key:
            return slug
    return None
