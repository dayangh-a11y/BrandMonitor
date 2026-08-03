"""Google Maps reviews for Iran Post offices (from warehouse only)."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any


def collect_post_office_reviews(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    limit: int = 200,
) -> dict[str, Any]:
    """Collect Maps-derived reviews already stored for Iran Post branches.

    Does not scrape private surfaces — only warehouse `pi_reviews` rows
    (typically source=google_maps).
    """
    sentiments: Counter[str] = Counter()
    complaints: Counter[str] = Counter()
    ratings: list[float] = []
    recent: list[dict[str, Any]] = []

    rows = conn.execute(
        """
        SELECT r.id, r.branch_id, r.author, r.rating, r.text, r.published_at,
               r.collected_at, r.sentiment, r.complaint_category, r.source,
               b.name AS branch_name, b.city, b.province, b.address
        FROM pi_reviews r
        LEFT JOIN pi_branches b ON b.id = r.branch_id
        WHERE r.company_id = ?
        ORDER BY COALESCE(r.published_at, r.collected_at) DESC
        """,
        (company_id,),
    ).fetchall()

    for r in rows:
        d = dict(r)
        sentiments[str(d.get("sentiment") or "Neutral")] += 1
        if str(d.get("sentiment") or "") == "Negative":
            complaints[str(d.get("complaint_category") or "other")] += 1
        if d.get("rating") is not None:
            try:
                ratings.append(float(d["rating"]))
            except (TypeError, ValueError):
                pass
        if len(recent) < limit:
            recent.append(
                {
                    "id": d.get("id"),
                    "branch_id": d.get("branch_id"),
                    "branch_name": d.get("branch_name"),
                    "city": d.get("city"),
                    "province": d.get("province"),
                    "rating": d.get("rating"),
                    "sentiment": d.get("sentiment"),
                    "complaint_category": d.get("complaint_category"),
                    "text": (d.get("text") or "")[:300],
                    "published_at": d.get("published_at"),
                    "source": d.get("source") or "google_maps",
                }
            )

    # branch directory summary from Maps-observed offices
    offices = []
    for b in conn.execute(
        """
        SELECT b.id, b.name, b.city, b.province, b.address, b.latitude, b.longitude,
               b.google_rating, bi.branch_score, bi.review_count, bi.last_activity
        FROM pi_branches b
        LEFT JOIN pi_branch_intelligence bi ON bi.branch_id = b.id
        WHERE b.company_id = ?
        ORDER BY COALESCE(bi.review_count, 0) DESC, b.name
        """,
        (company_id,),
    ):
        offices.append(dict(b))

    return {
        "review_count": len(rows),
        "avg_rating": round(sum(ratings) / len(ratings), 3) if ratings else None,
        "sentiments": dict(sentiments),
        "complaints": dict(complaints),
        "recent_reviews": recent,
        "post_offices_observed": offices,
        "post_office_count_observed": len(offices),
        "source_policy": "warehouse_google_maps_only",
    }


def dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
