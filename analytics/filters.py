from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AnalyticsFilter:
    """Shared filter set for company/branch dashboards and comparisons."""

    date_from: str | None = None
    date_to: str | None = None
    province: str | None = None
    city: str | None = None
    branch_id: int | None = None
    rating_min: float | None = None
    rating_max: float | None = None
    sentiment: str | None = None
    complaint_category: str | None = None
    positive_category: str | None = None
    min_review_count: int | None = None
    trend_grain: str = "weekly"  # daily | weekly | monthly

    def cache_key(self) -> str:
        payload = {k: v for k, v in asdict(self).items() if v not in (None, "", [])}
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> AnalyticsFilter:
        def _f(name: str) -> Any:
            return params.get(name)

        def _float(name: str) -> float | None:
            raw = _f(name)
            if raw is None or raw == "":
                return None
            return float(raw)

        def _int(name: str) -> int | None:
            raw = _f(name)
            if raw is None or raw == "":
                return None
            return int(raw)

        grain = str(_f("trend_grain") or "weekly").lower()
        if grain not in {"daily", "weekly", "monthly"}:
            grain = "weekly"
        return cls(
            date_from=_f("date_from") or None,
            date_to=_f("date_to") or None,
            province=_f("province") or None,
            city=_f("city") or None,
            branch_id=_int("branch_id"),
            rating_min=_float("rating_min"),
            rating_max=_float("rating_max"),
            sentiment=_f("sentiment") or None,
            complaint_category=_f("complaint_category") or None,
            positive_category=_f("positive_category") or None,
            min_review_count=_int("min_review_count"),
            trend_grain=grain,
        )


def row_matches(row: dict[str, Any], filt: AnalyticsFilter) -> bool:
    day = (row.get("event_date") or "")[:10]
    if filt.date_from and day and day < filt.date_from[:10]:
        return False
    if filt.date_to and day and day > filt.date_to[:10]:
        return False
    if filt.province and (row.get("province") or "").lower() != filt.province.lower():
        return False
    if filt.city and (row.get("city") or "").lower() != filt.city.lower():
        return False
    if filt.branch_id is not None and int(row.get("branch_id") or 0) != filt.branch_id:
        return False
    rating = float(row.get("review_rating") or 0)
    if filt.rating_min is not None and rating < filt.rating_min:
        return False
    if filt.rating_max is not None and rating > filt.rating_max:
        return False
    if filt.sentiment and (row.get("sentiment") or "").lower() != filt.sentiment.lower():
        return False
    complaints = row.get("complaint_categories") or []
    positives = row.get("positive_categories") or []
    if filt.complaint_category and filt.complaint_category not in complaints:
        return False
    if filt.positive_category and filt.positive_category not in positives:
        return False
    return True
