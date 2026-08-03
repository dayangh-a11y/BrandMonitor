"""Google Maps provider adapter wrapping the existing Playwright collector output / DB export."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from collectors.providers.base import ProviderMode, UnifiedReview


class GoogleMapsProvider:
    """
    Reads already-collected Google Maps reviews from BrandMonitor SQLite DBs.

    Live crawling remains in collectors.google_maps (unchanged). This adapter
    projects those rows into UnifiedReview for the multi-source pipeline.
    """

    source_id = "google_maps"
    display_name = "Google Maps"
    mode: ProviderMode = "live_maps"

    def __init__(self, db_paths: list[str] | None = None):
        self.db_paths = [
            Path(p)
            for p in (
                db_paths
                or [
                    "data/phase11_multisource.db",
                    "data/tipax_iran.db",
                    "data/analytics_demo.db",
                ]
            )
        ]

    def healthcheck(self) -> dict[str, Any]:
        existing = [str(p) for p in self.db_paths if p.exists()]
        return {
            "source_id": self.source_id,
            "mode": self.mode,
            "ready": bool(existing),
            "db_paths": existing,
            "notes": "Live crawl via collectors.google_maps.*; this adapter unifies DB rows.",
        }

    def collect(self, brand: str, **kwargs: Any) -> list[UnifiedReview]:
        brand_aliases = {
            "tipax": {"tipax", "تیپاکس"},
            "chapar": {"chapar", "چاپار"},
            "post": {"post", "iran post", "پست", "پست ایران"},
            "mahex": {"mahex", "ماهکس"},
            "alopeyk": {"alopeyk", "الو پیک", "الوپیک"},
        }
        key = brand.casefold().strip()
        aliases = brand_aliases.get(key, {key, brand})
        out: list[UnifiedReview] = []
        for path in self.db_paths:
            if not path.exists():
                continue
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            try:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"companies", "branches", "reviews"} <= tables:
                    continue
                cols_b = {r[1] for r in conn.execute("pragma table_info(branches)")}
                cols_r = {r[1] for r in conn.execute("pragma table_info(reviews)")}
                bdel = "COALESCE(b.is_deleted,0)=0" if "is_deleted" in cols_b else "1=1"
                rdel = "COALESCE(r.is_deleted,0)=0" if "is_deleted" in cols_r else "1=1"
                sql = f"""
                SELECT co.name AS brand, b.name AS branch, COALESCE(b.city,'') city,
                       COALESCE(b.province,'') province, COALESCE(b.address,'') address,
                       {"b.latitude" if "latitude" in cols_b else "NULL"} AS latitude,
                       {"b.longitude" if "longitude" in cols_b else "NULL"} AS longitude,
                       COALESCE(b.maps_url,'') AS url,
                       r.rating, COALESCE(r.text,'') AS review,
                       COALESCE(r.published_at,'') AS review_date,
                       COALESCE(r.author,'') AS reviewer,
                       {"COALESCE(r.owner_response,'')" if "owner_response" in cols_r else "''"} AS reply,
                       {"COALESCE(r.owner_response_at,'')" if "owner_response_at" in cols_r else "''"} AS reply_date,
                       COALESCE(r.external_id,'') AS external_id,
                       COALESCE(r.collected_at,'') AS scraped_at,
                       COALESCE(r.source,'google_maps') AS src
                FROM reviews r
                JOIN branches b ON b.id=r.branch_id AND {bdel}
                JOIN companies co ON co.id=b.company_id
                WHERE {rdel}
                """
                for row in conn.execute(sql):
                    bname = (row["brand"] or "").casefold()
                    if bname not in aliases and not any(a in bname for a in aliases):
                        # map Iran Post naming
                        if key == "post" and "post" in bname:
                            pass
                        else:
                            continue
                    out.append(
                        UnifiedReview(
                            source="google_maps",
                            brand=self._canon_brand(row["brand"]),
                            branch=row["branch"] or "",
                            province=row["province"] or "",
                            city=row["city"] or "",
                            latitude=row["latitude"],
                            longitude=row["longitude"],
                            rating=row["rating"],
                            review=row["review"] or "",
                            review_date=row["review_date"] or "",
                            reviewer=row["reviewer"] or "",
                            reply=row["reply"] or "",
                            reply_date=row["reply_date"] or "",
                            photos_count=None,
                            url=row["url"] or "",
                            scraped_at=row["scraped_at"] or "",
                            external_id=row["external_id"] or "",
                            metadata={"address": row["address"] or "", "db": str(path)},
                        )
                    )
            finally:
                conn.close()
        return out

    @staticmethod
    def _canon_brand(name: str) -> str:
        n = (name or "").strip()
        mapping = {
            "تیپاکس": "Tipax",
            "Tipax": "Tipax",
            "چاپار": "Chapar",
            "Chapar": "Chapar",
            "پست": "Iran Post",
            "پست ایران": "Iran Post",
            "Post": "Iran Post",
            "ماهکس": "Mahex",
            "Mahex": "Mahex",
            "الوپیک": "AloPeyk",
            "AloPeyk": "AloPeyk",
        }
        return mapping.get(n, n)
