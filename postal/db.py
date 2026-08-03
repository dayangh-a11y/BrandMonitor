"""Postal Intelligence SQLite access layer."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from postal.schema import SCHEMA_SQL


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostalIntelligenceDB:
    def __init__(self, path: str = "data/postal_intelligence.db"):
        self.path = path
        self.conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def _c(self) -> sqlite3.Connection:
        assert self.conn is not None
        return self.conn

    def set_meta(self, key: str, value: str) -> None:
        self._c().execute(
            "INSERT INTO pi_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def upsert_company(self, slug: str, name: str, **fields: Any) -> int:
        now = utcnow()
        cur = self._c().execute(
            """
            INSERT INTO pi_companies(slug, name, name_fa, website, founded_year,
                headquarters, ownership, description, description_fa, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name,
                name_fa=excluded.name_fa,
                website=excluded.website,
                founded_year=excluded.founded_year,
                headquarters=excluded.headquarters,
                ownership=excluded.ownership,
                description=excluded.description,
                description_fa=excluded.description_fa,
                updated_at=excluded.updated_at
            """,
            (
                slug,
                name,
                fields.get("name_fa") or "",
                fields.get("website") or "",
                fields.get("founded_year"),
                fields.get("headquarters") or "",
                fields.get("ownership") or "",
                fields.get("description") or "",
                fields.get("description_fa") or "",
                now,
                now,
            ),
        )
        self._c().commit()
        row = self._c().execute("SELECT id FROM pi_companies WHERE slug=?", (slug,)).fetchone()
        return int(row["id"])

    def upsert_official_profile(self, company_id: int, official: dict[str, Any]) -> None:
        now = utcnow()
        self._c().execute(
            """
            INSERT INTO pi_official_profiles(
                company_id, profile_json, services_json, domestic_services_json,
                international_json, insurance_json, cod_json, tracking_json,
                packaging_json, working_hours_json, support_json,
                branch_count_official, cities_covered_official, provinces_covered_official,
                pricing_json, delivery_times_json, weight_limits_json, size_limits_json,
                data_quality, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(company_id) DO UPDATE SET
                profile_json=excluded.profile_json,
                services_json=excluded.services_json,
                domestic_services_json=excluded.domestic_services_json,
                international_json=excluded.international_json,
                insurance_json=excluded.insurance_json,
                cod_json=excluded.cod_json,
                tracking_json=excluded.tracking_json,
                packaging_json=excluded.packaging_json,
                working_hours_json=excluded.working_hours_json,
                support_json=excluded.support_json,
                branch_count_official=excluded.branch_count_official,
                cities_covered_official=excluded.cities_covered_official,
                provinces_covered_official=excluded.provinces_covered_official,
                pricing_json=excluded.pricing_json,
                delivery_times_json=excluded.delivery_times_json,
                weight_limits_json=excluded.weight_limits_json,
                size_limits_json=excluded.size_limits_json,
                data_quality=excluded.data_quality,
                updated_at=excluded.updated_at
            """,
            (
                company_id,
                json.dumps(official, ensure_ascii=False),
                json.dumps(official.get("services") or [], ensure_ascii=False),
                json.dumps(official.get("domestic_services") or [], ensure_ascii=False),
                json.dumps(official.get("international_services") or {}, ensure_ascii=False),
                json.dumps(official.get("insurance") or {}, ensure_ascii=False),
                json.dumps(official.get("cod") or {}, ensure_ascii=False),
                json.dumps(official.get("tracking") or {}, ensure_ascii=False),
                json.dumps(official.get("packaging") or {}, ensure_ascii=False),
                json.dumps(official.get("working_hours") or {}, ensure_ascii=False),
                json.dumps(official.get("customer_support") or {}, ensure_ascii=False),
                int(official.get("branch_count_official") or 0),
                int(official.get("cities_covered_official") or 0),
                int(official.get("provinces_covered_official") or 0),
                json.dumps(official.get("official_pricing") or {}, ensure_ascii=False),
                json.dumps(official.get("official_delivery_times") or {}, ensure_ascii=False),
                json.dumps(official.get("weight_limits") or {}, ensure_ascii=False),
                json.dumps(official.get("size_limits") or {}, ensure_ascii=False),
                str(official.get("data_quality") or "curated_v1"),
                now,
            ),
        )
        self._c().commit()

    def upsert_branch(self, company_id: int, branch: dict[str, Any]) -> int:
        self._c().execute(
            """
            INSERT INTO pi_branches(
                company_id, external_key, name, address, city, province,
                latitude, longitude, phone, maps_url, place_id,
                source_db, source_branch_id, google_rating, google_review_count
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(company_id, name, address) DO UPDATE SET
                city=excluded.city,
                province=excluded.province,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                phone=excluded.phone,
                maps_url=excluded.maps_url,
                place_id=excluded.place_id,
                google_rating=excluded.google_rating,
                google_review_count=excluded.google_review_count,
                source_db=excluded.source_db,
                source_branch_id=excluded.source_branch_id
            """,
            (
                company_id,
                branch.get("external_key") or "",
                branch["name"],
                branch.get("address") or "",
                branch.get("city") or "",
                branch.get("province") or "",
                branch.get("latitude"),
                branch.get("longitude"),
                branch.get("phone") or "",
                branch.get("maps_url") or "",
                branch.get("place_id") or "",
                branch.get("source_db") or "",
                branch.get("source_branch_id"),
                float(branch.get("google_rating") or 0),
                int(branch.get("google_review_count") or 0),
            ),
        )
        self._c().commit()
        row = self._c().execute(
            "SELECT id FROM pi_branches WHERE company_id=? AND name=? AND address=?",
            (company_id, branch["name"], branch.get("address") or ""),
        ).fetchone()
        return int(row["id"])

    def upsert_review(self, branch_id: int, company_id: int, review: dict[str, Any]) -> None:
        self._c().execute(
            """
            INSERT INTO pi_reviews(
                branch_id, company_id, author, rating, text, published_at, source,
                external_id, sentiment, complaint_category, emotion, urgency,
                nlp_confidence, collected_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(branch_id, external_id) DO UPDATE SET
                rating=excluded.rating,
                text=excluded.text,
                sentiment=excluded.sentiment,
                complaint_category=excluded.complaint_category,
                emotion=excluded.emotion,
                urgency=excluded.urgency,
                nlp_confidence=excluded.nlp_confidence
            """,
            (
                branch_id,
                company_id,
                review.get("author") or "",
                float(review.get("rating") or 0),
                review.get("text") or "",
                review.get("published_at") or "",
                review.get("source") or "google_maps",
                review.get("external_id") or f"auto-{branch_id}-{hash(review.get('text') or '') % 10_000_000}",
                review.get("sentiment") or "Neutral",
                review.get("complaint_category") or "other",
                review.get("emotion") or "",
                review.get("urgency") or "Low",
                int(review.get("nlp_confidence") or 0),
                review.get("collected_at") or utcnow(),
            ),
        )

    def commit(self) -> None:
        self._c().commit()

    def insert_company_score(self, company_id: int, breakdown: dict[str, Any]) -> None:
        self._c().execute(
            """
            INSERT INTO pi_company_scores(
                company_id, score, dimensions_json, weights_json, explanation_json,
                algorithm_version, calculated_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                company_id,
                float(breakdown["score"]),
                json.dumps(breakdown.get("dimensions") or {}, ensure_ascii=False),
                json.dumps(breakdown.get("weights") or {}, ensure_ascii=False),
                json.dumps(
                    {
                        "why": breakdown.get("why") or [],
                        "weighted_contribution": breakdown.get("weighted_contribution") or {},
                    },
                    ensure_ascii=False,
                ),
                breakdown.get("algorithm_version") or "postal_score_v1",
                utcnow(),
            ),
        )
        self._c().commit()

    def upsert_branch_intelligence(self, branch_id: int, company_id: int, payload: dict[str, Any]) -> None:
        self._c().execute(
            """
            INSERT INTO pi_branch_intelligence(
                branch_id, company_id, overall_rating, review_count,
                complaint_categories_json, sentiment_json, review_trend_json,
                last_activity, branch_score, explanation_json, algorithm_version, calculated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(branch_id) DO UPDATE SET
                overall_rating=excluded.overall_rating,
                review_count=excluded.review_count,
                complaint_categories_json=excluded.complaint_categories_json,
                sentiment_json=excluded.sentiment_json,
                review_trend_json=excluded.review_trend_json,
                last_activity=excluded.last_activity,
                branch_score=excluded.branch_score,
                explanation_json=excluded.explanation_json,
                algorithm_version=excluded.algorithm_version,
                calculated_at=excluded.calculated_at
            """,
            (
                branch_id,
                company_id,
                float(payload.get("overall_rating") or 0),
                int(payload.get("review_count") or 0),
                json.dumps(payload.get("complaint_categories") or {}, ensure_ascii=False),
                json.dumps(payload.get("sentiment") or {}, ensure_ascii=False),
                json.dumps(payload.get("review_trend") or [], ensure_ascii=False),
                payload.get("last_activity") or "",
                float(payload.get("branch_score") or 0),
                json.dumps(payload.get("explanation") or {}, ensure_ascii=False),
                payload.get("algorithm_version") or "postal_score_v1",
                utcnow(),
            ),
        )
        self._c().commit()

    def clear_geo_rankings(self) -> None:
        self._c().execute("DELETE FROM pi_geo_rankings")
        self._c().commit()

    def insert_geo_ranking(self, row: dict[str, Any]) -> None:
        self._c().execute(
            """
            INSERT INTO pi_geo_rankings(
                geo_level, geo_name, province, company_id, company_name, rank,
                score, review_count, branch_count, avg_rating, metrics_json, calculated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["geo_level"],
                row["geo_name"],
                row.get("province") or "",
                row["company_id"],
                row["company_name"],
                row["rank"],
                row["score"],
                row.get("review_count") or 0,
                row.get("branch_count") or 0,
                row.get("avg_rating") or 0,
                json.dumps(row.get("metrics") or {}, ensure_ascii=False),
                utcnow(),
            ),
        )

    def save_comparison(self, kind: str, payload: dict[str, Any]) -> None:
        self._c().execute(
            "INSERT INTO pi_comparisons(comparison_kind, payload_json, calculated_at) VALUES (?,?,?)",
            (kind, json.dumps(payload, ensure_ascii=False), utcnow()),
        )
        self._c().commit()

    def list_companies(self) -> list[dict[str, Any]]:
        rows = self._c().execute("SELECT * FROM pi_companies ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def get_official(self, company_id: int) -> dict[str, Any] | None:
        row = self._c().execute(
            "SELECT * FROM pi_official_profiles WHERE company_id=?", (company_id,)
        ).fetchone()
        return dict(row) if row else None

    def latest_company_scores(self) -> list[dict[str, Any]]:
        rows = self._c().execute(
            """
            SELECT c.id AS company_id, c.slug, c.name, c.name_fa, s.score,
                   s.dimensions_json, s.weights_json, s.explanation_json,
                   s.algorithm_version, s.calculated_at
            FROM pi_companies c
            JOIN pi_company_scores s ON s.id = (
                SELECT id FROM pi_company_scores WHERE company_id=c.id ORDER BY id DESC LIMIT 1
            )
            ORDER BY s.score DESC
            """
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["dimensions"] = json.loads(d.pop("dimensions_json") or "{}")
            d["weights"] = json.loads(d.pop("weights_json") or "{}")
            d["explanation"] = json.loads(d.pop("explanation_json") or "{}")
            out.append(d)
        return out

    def list_branch_intelligence(self, *, limit: int = 5000) -> list[dict[str, Any]]:
        rows = self._c().execute(
            """
            SELECT bi.*, b.name AS branch_name, b.city, b.province, b.latitude, b.longitude,
                   b.google_rating, c.name AS company_name, c.slug AS company_slug
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

    def latest_comparison(self, kind: str = "all_companies") -> dict[str, Any] | None:
        row = self._c().execute(
            """
            SELECT payload_json, calculated_at FROM pi_comparisons
            WHERE comparison_kind=? ORDER BY id DESC LIMIT 1
            """,
            (kind,),
        ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        payload["calculated_at"] = row["calculated_at"]
        return payload

    def list_geo_rankings(self, geo_level: str | None = None) -> list[dict[str, Any]]:
        if geo_level:
            rows = self._c().execute(
                "SELECT * FROM pi_geo_rankings WHERE geo_level=? ORDER BY geo_name, rank",
                (geo_level,),
            ).fetchall()
        else:
            rows = self._c().execute(
                "SELECT * FROM pi_geo_rankings ORDER BY geo_level, geo_name, rank"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d.pop("metrics_json") or "{}")
            out.append(d)
        return out

    def company_review_stats(self, company_id: int) -> dict[str, Any]:
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
            "SELECT AVG(rating) avg_rating, COUNT(*) n FROM pi_reviews WHERE company_id=?",
            (company_id,),
        ).fetchone()
        return {
            "sentiments": sentiments,
            "complaints": complaints,
            "avg_rating": float(row["avg_rating"] or 0),
            "review_count": int(row["n"] or 0),
        }

    def company_branch_stats(self, company_id: int) -> dict[str, Any]:
        c = self._c()
        row = c.execute(
            """
            SELECT COUNT(*) n, AVG(google_rating) avg_r
            FROM pi_branches WHERE company_id=?
            """,
            (company_id,),
        ).fetchone()
        scores = [
            float(r["branch_score"])
            for r in c.execute(
                "SELECT branch_score FROM pi_branch_intelligence WHERE company_id=?",
                (company_id,),
            )
        ]
        return {
            "observed_branch_count": int(row["n"] or 0),
            "avg_google_rating": float(row["avg_r"] or 0),
            "branch_scores": scores,
        }
