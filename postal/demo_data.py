"""Load BrandMonitor Postal Intelligence demo snapshot from SQLite."""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from postal.metric_confidence import metric_confidence_bundle


def default_db_path() -> str:
    return os.getenv("POSTAL_DB_PATH", "data/postal_intelligence.db")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntelDemoData:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or default_db_path()
        self._conn: sqlite3.Connection | None = None
        self._cache: dict[str, Any] | None = None
        self.built_at = utcnow()

    def connect(self) -> None:
        if not Path(self.db_path).exists():
            raise FileNotFoundError(
                f"Postal intelligence DB not found: {self.db_path}. "
                "Run scripts/build_postal_intelligence.py first."
            )
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _c(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._cache is not None and not refresh:
            return self._cache
        self._cache = self._build_snapshot()
        self.built_at = self._cache["meta"]["built_at"]
        return self._cache

    def _build_snapshot(self) -> dict[str, Any]:
        c = self._c()
        companies = [dict(r) for r in c.execute("SELECT * FROM pi_companies ORDER BY name")]
        scores = {}
        for r in c.execute(
            """
            SELECT c.id, c.slug, c.name, c.name_fa, s.score, s.dimensions_json,
                   s.weights_json, s.explanation_json, s.calculated_at, s.algorithm_version
            FROM pi_companies c
            JOIN pi_company_scores s ON s.id=(
              SELECT id FROM pi_company_scores WHERE company_id=c.id ORDER BY id DESC LIMIT 1
            )
            """
        ):
            d = dict(r)
            d["dimensions"] = json.loads(d.pop("dimensions_json") or "{}")
            d["weights"] = json.loads(d.pop("weights_json") or "{}")
            d["explanation"] = json.loads(d.pop("explanation_json") or "{}")
            scores[int(d["id"])] = d

        official = {}
        for r in c.execute("SELECT * FROM pi_official_profiles"):
            row = dict(r)
            official[int(row["company_id"])] = {
                "services": json.loads(row.get("services_json") or "[]"),
                "pricing": json.loads(row.get("pricing_json") or "{}"),
                "delivery_times": json.loads(row.get("delivery_times_json") or "{}"),
                "support": json.loads(row.get("support_json") or "{}"),
                "tracking": json.loads(row.get("tracking_json") or "{}"),
                "insurance": json.loads(row.get("insurance_json") or "{}"),
                "cod": json.loads(row.get("cod_json") or "{}"),
                "working_hours": json.loads(row.get("working_hours_json") or "{}"),
                "branch_count_official": row.get("branch_count_official"),
                "cities_covered_official": row.get("cities_covered_official"),
                "provinces_covered_official": row.get("provinces_covered_official"),
                "data_quality": row.get("data_quality"),
                "profile": json.loads(row.get("profile_json") or "{}"),
            }

        company_cards = []
        for company in companies:
            cid = int(company["id"])
            score = scores.get(cid)
            stats = self._company_review_stats(cid)
            branch_stats = self._company_branch_stats(cid)
            off = official.get(cid) or {}
            # official completeness proxy from stored profile fields
            present = 0
            checks = [
                bool(off.get("services")),
                bool(off.get("tracking")),
                bool(off.get("insurance")),
                bool(off.get("support")),
                bool(off.get("delivery_times")),
                bool(off.get("pricing")),
                bool(off.get("working_hours")),
                bool(off.get("cod")),
            ]
            present = sum(1 for x in checks if x)
            conf = metric_confidence_bundle(
                review_count=stats["review_count"],
                branch_count=branch_stats["branch_count"],
                city_count=branch_stats["city_count"],
                province_count=branch_stats["province_count"],
                official_completeness_ratio=present / max(len(checks), 1),
                official_reachable=True,
            )
            company_cards.append(
                {
                    "id": cid,
                    "slug": company["slug"],
                    "name": company["name"],
                    "name_fa": company.get("name_fa") or "",
                    "website": company.get("website") or "",
                    "description": company.get("description") or "",
                    "score": score["score"] if score else None,
                    "algorithm_version": (score or {}).get("algorithm_version"),
                    "score_calculated_at": (score or {}).get("calculated_at"),
                    "dimensions": (score or {}).get("dimensions") or {},
                    "weights": (score or {}).get("weights") or {},
                    "explanation": (score or {}).get("explanation") or {},
                    "review_count": stats["review_count"],
                    "avg_rating": stats["avg_rating"],
                    "sentiments": stats["sentiments"],
                    "complaints": stats["complaints"],
                    "branch_count": branch_stats["branch_count"],
                    "city_count": branch_stats["city_count"],
                    "province_count": branch_stats["province_count"],
                    "provinces": branch_stats["provinces"],
                    "official": off,
                    "confidence": conf,
                }
            )
        company_cards.sort(key=lambda x: float(x["score"] or 0), reverse=True)
        for i, card in enumerate(company_cards, 1):
            card["rank"] = i

        branches = self._branch_cards()
        comparison = None
        row = c.execute(
            "SELECT payload_json, calculated_at FROM pi_comparisons WHERE comparison_kind='all_companies' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            comparison = json.loads(row["payload_json"])
            comparison["calculated_at"] = row["calculated_at"]

        totals = {
            "companies": len(company_cards),
            "branches": sum(c["branch_count"] for c in company_cards),
            "reviews": sum(c["review_count"] for c in company_cards),
            "avg_confidence": round(
                sum(c["confidence"]["overall_dataset_confidence"] for c in company_cards)
                / max(len(company_cards), 1),
                3,
            ),
        }

        # global trends
        trend = Counter()
        sentiment_trend: dict[str, Counter] = defaultdict(Counter)
        for r in c.execute(
            "SELECT published_at, collected_at, sentiment FROM pi_reviews"
        ):
            day = (r["published_at"] or r["collected_at"] or "")[:7]
            if len(day) < 7:
                continue
            trend[day] += 1
            sentiment_trend[day][str(r["sentiment"] or "Neutral")] += 1

        return {
            "meta": {
                "built_at": utcnow(),
                "db_path": self.db_path,
                "product": "BrandMonitor Postal Intelligence",
                "algorithm_version": "postal_score_v1",
            },
            "totals": totals,
            "companies": company_cards,
            "branches": branches,
            "comparison": comparison,
            "trends": {
                "reviews_by_month": [
                    {"month": m, "count": trend[m]} for m in sorted(trend.keys())
                ],
                "sentiment_by_month": [
                    {
                        "month": m,
                        "Positive": sentiment_trend[m].get("Positive", 0),
                        "Neutral": sentiment_trend[m].get("Neutral", 0),
                        "Negative": sentiment_trend[m].get("Negative", 0),
                    }
                    for m in sorted(sentiment_trend.keys())
                ],
            },
        }

    def _company_review_stats(self, company_id: int) -> dict[str, Any]:
        c = self._c()
        sentiments = {
            r["sentiment"]: r["n"]
            for r in c.execute(
                "SELECT sentiment, COUNT(*) n FROM pi_reviews WHERE company_id=? GROUP BY sentiment",
                (company_id,),
            )
        }
        complaints = {
            r["complaint_category"]: r["n"]
            for r in c.execute(
                """
                SELECT complaint_category, COUNT(*) n FROM pi_reviews
                WHERE company_id=? AND sentiment='Negative'
                GROUP BY complaint_category
                """,
                (company_id,),
            )
        }
        row = c.execute(
            "SELECT AVG(rating) a, COUNT(*) n FROM pi_reviews WHERE company_id=?",
            (company_id,),
        ).fetchone()
        return {
            "sentiments": sentiments,
            "complaints": complaints,
            "avg_rating": round(float(row["a"] or 0), 3),
            "review_count": int(row["n"] or 0),
        }

    def _company_branch_stats(self, company_id: int) -> dict[str, Any]:
        c = self._c()
        rows = [
            dict(r)
            for r in c.execute(
                "SELECT city, province FROM pi_branches WHERE company_id=?",
                (company_id,),
            )
        ]
        cities = { (r.get("city") or "").strip() for r in rows if (r.get("city") or "").strip() }
        provinces = {
            (r.get("province") or "").strip()
            for r in rows
            if (r.get("province") or "").strip()
        }
        return {
            "branch_count": len(rows),
            "city_count": len(cities),
            "province_count": len(provinces),
            "provinces": sorted(provinces),
        }

    def _branch_cards(self, *, limit: int = 500) -> list[dict[str, Any]]:
        c = self._c()
        rows = c.execute(
            """
            SELECT bi.*, b.name AS branch_name, b.city, b.province, b.latitude, b.longitude,
                   b.address, b.google_rating, c.name AS company_name, c.slug AS company_slug,
                   c.id AS company_id
            FROM pi_branch_intelligence bi
            JOIN pi_branches b ON b.id = bi.branch_id
            JOIN pi_companies c ON c.id = bi.company_id
            ORDER BY bi.branch_score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["complaint_categories"] = json.loads(d.pop("complaint_categories_json") or "{}")
            d["sentiment"] = json.loads(d.pop("sentiment_json") or "{}")
            d["review_trend"] = json.loads(d.pop("review_trend_json") or "[]")
            d["explanation"] = json.loads(d.pop("explanation_json") or "{}")
            out.append(d)
        return out

    def company_by_slug(self, slug: str) -> dict[str, Any] | None:
        for c in self.snapshot()["companies"]:
            if c["slug"] == slug or c["name"].casefold() == slug.casefold():
                return c
        return None

    def company_by_id(self, company_id: int) -> dict[str, Any] | None:
        for c in self.snapshot()["companies"]:
            if int(c["id"]) == int(company_id):
                return c
        return None

    def branch_by_id(self, branch_id: int) -> dict[str, Any] | None:
        for b in self.snapshot()["branches"]:
            if int(b["branch_id"]) == int(branch_id):
                return b
        # fetch directly if not in top list
        c = self._c()
        row = c.execute(
            """
            SELECT bi.*, b.name AS branch_name, b.city, b.province, b.latitude, b.longitude,
                   b.address, b.google_rating, c.name AS company_name, c.slug AS company_slug,
                   c.id AS company_id
            FROM pi_branch_intelligence bi
            JOIN pi_branches b ON b.id = bi.branch_id
            JOIN pi_companies c ON c.id = bi.company_id
            WHERE bi.branch_id=?
            """,
            (branch_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["complaint_categories"] = json.loads(d.pop("complaint_categories_json") or "{}")
        d["sentiment"] = json.loads(d.pop("sentiment_json") or "{}")
        d["review_trend"] = json.loads(d.pop("review_trend_json") or "[]")
        d["explanation"] = json.loads(d.pop("explanation_json") or "{}")
        return d

    def branch_reviews(self, branch_id: int, *, limit: int = 40) -> list[dict[str, Any]]:
        c = self._c()
        rows = c.execute(
            """
            SELECT id, author, rating, text, published_at, sentiment, complaint_category,
                   emotion, urgency, collected_at, source
            FROM pi_reviews WHERE branch_id=?
            ORDER BY COALESCE(published_at, collected_at) DESC
            LIMIT ?
            """,
            (branch_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def province_performance(self, company_id: int) -> list[dict[str, Any]]:
        c = self._c()
        # from geo rankings if available
        rows = c.execute(
            """
            SELECT geo_name, rank, score, review_count, branch_count, avg_rating, metrics_json
            FROM pi_geo_rankings
            WHERE geo_level='province' AND company_id=?
            ORDER BY score DESC
            """,
            (company_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d.pop("metrics_json") or "{}")
            out.append(d)
        return out

    def map_points(self, *, limit: int = 800) -> list[dict[str, Any]]:
        points = []
        for b in self.snapshot()["branches"][:limit]:
            if b.get("latitude") is None or b.get("longitude") is None:
                continue
            points.append(
                {
                    "id": b["branch_id"],
                    "name": b["branch_name"],
                    "company": b["company_name"],
                    "slug": b["company_slug"],
                    "score": b["branch_score"],
                    "city": b.get("city"),
                    "lat": b["latitude"],
                    "lng": b["longitude"],
                }
            )
        return points

    def company_trends(self, company_id: int) -> dict[str, Any]:
        c = self._c()
        rating_trend: dict[str, list[float]] = defaultdict(list)
        sentiment_trend: dict[str, Counter] = defaultdict(Counter)
        complaint_trend: dict[str, Counter] = defaultdict(Counter)
        for r in c.execute(
            """
            SELECT published_at, collected_at, rating, sentiment, complaint_category
            FROM pi_reviews WHERE company_id=?
            """,
            (company_id,),
        ):
            day = (r["published_at"] or r["collected_at"] or "")[:7]
            if len(day) < 7:
                continue
            if r["rating"] is not None:
                try:
                    rating_trend[day].append(float(r["rating"]))
                except (TypeError, ValueError):
                    pass
            sentiment_trend[day][str(r["sentiment"] or "Neutral")] += 1
            if str(r["sentiment"] or "") == "Negative":
                complaint_trend[day][str(r["complaint_category"] or "other")] += 1

        months = sorted(set(rating_trend) | set(sentiment_trend) | set(complaint_trend))
        return {
            "rating_by_month": [
                {
                    "month": m,
                    "avg_rating": round(sum(rating_trend[m]) / len(rating_trend[m]), 3)
                    if rating_trend[m]
                    else None,
                    "n": len(rating_trend[m]),
                }
                for m in months
            ],
            "sentiment_by_month": [
                {
                    "month": m,
                    "Positive": sentiment_trend[m].get("Positive", 0),
                    "Neutral": sentiment_trend[m].get("Neutral", 0),
                    "Negative": sentiment_trend[m].get("Negative", 0),
                }
                for m in months
            ],
            "complaints_by_month": [
                {
                    "month": m,
                    "total_negative": sum(complaint_trend[m].values()),
                    "categories": dict(complaint_trend[m]),
                }
                for m in months
            ],
        }

    def top_branches_for_company(
        self, company_id: int, *, limit: int = 12
    ) -> list[dict[str, Any]]:
        return [
            b
            for b in self.snapshot()["branches"]
            if int(b["company_id"]) == int(company_id)
        ][:limit]
