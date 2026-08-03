"""Manual CSV/JSON import adapter — safe fallback when no official API exists."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from collectors.providers.base import ProviderMode, UnifiedReview


def _row_get(row: dict, *keys: str, default: str = "") -> Any:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
        # case-insensitive
        for rk, rv in row.items():
            if str(rk).casefold() == k.casefold() and rv not in (None, ""):
                return rv
    return default


def load_unified_from_csv(path: Path, *, source: str, default_brand: str = "") -> list[UnifiedReview]:
    rows: list[UnifiedReview] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            brand = str(_row_get(row, "brand", "brand_name", default=default_brand) or default_brand)
            review = UnifiedReview(
                source=source,
                brand=brand,
                branch=str(_row_get(row, "branch", "branch_name", "app_name")),
                province=str(_row_get(row, "province")),
                city=str(_row_get(row, "city")),
                latitude=_float_or_none(_row_get(row, "latitude", "lat", default=None)),
                longitude=_float_or_none(_row_get(row, "longitude", "lng", "lon", default=None)),
                rating=_float_or_none(_row_get(row, "rating", "app_rating", default=None)),
                review=str(_row_get(row, "review", "review_text", "text")),
                review_date=str(_row_get(row, "review_date", "date", "published_at")),
                reviewer=str(_row_get(row, "reviewer", "reviewer_name", "author")),
                reply=str(_row_get(row, "reply", "company_reply", "developer_reply", "owner_response")),
                reply_date=str(_row_get(row, "reply_date", "owner_response_at")),
                photos_count=_int_or_none(_row_get(row, "photos_count", "photos", default=None)),
                url=str(_row_get(row, "url", "review_url", "maps_url")),
                external_id=str(_row_get(row, "external_id", "review_id", "id")),
                app_version=str(_row_get(row, "app_version", "version")),
                total_votes=_int_or_none(_row_get(row, "total_votes", "votes", default=None)),
            )
            rows.append(review)
    return rows


def load_unified_from_json(path: Path, *, source: str, default_brand: str = "") -> list[UnifiedReview]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload if isinstance(payload, list) else payload.get("reviews") or payload.get("items") or []
    tmp = Path(path).with_suffix(".tmp.csv")
    # Normalize via dict path
    out: list[UnifiedReview] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        brand = str(row.get("brand") or row.get("brand_name") or default_brand)
        out.append(
            UnifiedReview(
                source=source,
                brand=brand,
                branch=str(row.get("branch") or row.get("branch_name") or row.get("app_name") or ""),
                province=str(row.get("province") or ""),
                city=str(row.get("city") or ""),
                latitude=_float_or_none(row.get("latitude")),
                longitude=_float_or_none(row.get("longitude")),
                rating=_float_or_none(row.get("rating") if row.get("rating") is not None else row.get("app_rating")),
                review=str(row.get("review") or row.get("review_text") or row.get("text") or ""),
                review_date=str(row.get("review_date") or row.get("date") or row.get("published_at") or ""),
                reviewer=str(row.get("reviewer") or row.get("reviewer_name") or row.get("author") or ""),
                reply=str(row.get("reply") or row.get("developer_reply") or row.get("company_reply") or ""),
                reply_date=str(row.get("reply_date") or ""),
                photos_count=_int_or_none(row.get("photos_count")),
                url=str(row.get("url") or ""),
                external_id=str(row.get("external_id") or row.get("id") or ""),
                app_version=str(row.get("app_version") or row.get("version") or ""),
                total_votes=_int_or_none(row.get("total_votes")),
                metadata={k: v for k, v in row.items() if k.startswith("meta_")},
            )
        )
    _ = tmp  # unused
    return out


def _float_or_none(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int_or_none(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class ManualImportProvider:
    """Import-only provider used by Neshan/Balad/CafeBazaar/Myket until official APIs exist."""

    def __init__(
        self,
        source_id: str,
        display_name: str,
        *,
        dataset_dir: str | Path | None = None,
        mode: ProviderMode = "manual_import",
    ):
        self.source_id = source_id
        self.display_name = display_name
        self.mode: ProviderMode = mode
        self.dataset_dir = Path(dataset_dir or f"data/imports/{source_id}")

    def healthcheck(self) -> dict[str, Any]:
        exists = self.dataset_dir.exists()
        files = list(self.dataset_dir.glob("*.csv")) + list(self.dataset_dir.glob("*.json")) if exists else []
        return {
            "source_id": self.source_id,
            "mode": self.mode,
            "dataset_dir": str(self.dataset_dir),
            "ready": bool(files),
            "files": [p.name for p in files],
            "notes": (
                "No official stable public review API wired. "
                "Use manual_import datasets or replace this adapter with official_api later."
            ),
        }

    def collect(self, brand: str, **kwargs: Any) -> list[UnifiedReview]:
        if self.mode == "official_api":
            raise RuntimeError(
                f"{self.source_id}: official_api mode is not configured. "
                "Set credentials/endpoints or use manual_import datasets."
            )
        path = kwargs.get("path")
        paths: list[Path] = []
        if path:
            paths.append(Path(path))
        else:
            if not self.dataset_dir.exists():
                return []
            paths.extend(sorted(self.dataset_dir.glob("*.csv")))
            paths.extend(sorted(self.dataset_dir.glob("*.json")))
        out: list[UnifiedReview] = []
        brand_key = (brand or "").casefold()
        for p in paths:
            if p.suffix.lower() == ".csv":
                rows = load_unified_from_csv(p, source=self.source_id, default_brand=brand)
            else:
                rows = load_unified_from_json(p, source=self.source_id, default_brand=brand)
            for r in rows:
                if brand_key and r.brand and r.brand.casefold() not in {brand_key, brand_key.replace(" ", "")}:
                    # allow FA brand labels in fixtures
                    if brand_key not in r.brand.casefold() and r.brand.casefold() not in brand_key:
                        # still keep if file is brand-specific by name
                        if brand_key not in p.stem.casefold():
                            continue
                r.source = self.source_id
                if not r.brand:
                    r.brand = brand
                out.append(r)
        return out
