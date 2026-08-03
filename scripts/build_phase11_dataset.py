#!/usr/bin/env python3
"""
Phase 11 — build clean multi-source datasets (CSV only, no dashboards/charts).

Reads collected SQLite DBs + optional live rows, applies NLP + >90% dedupe,
writes:
  brand_summary.csv, branch_summary.csv, reviews_clean.csv,
  entities.csv, complaints.csv, dashboard_dataset.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from collectors.phase11.dedupe_similarity import dedupe_reviews
from collectors.phase11.nlp import analyze_review

NULL = "NULL"

BRANDS_PHASE11 = ("Chapar", "Post", "Mahex", "AloPeyk")

CITY_HINTS = {
    "تهران": "تهران",
    "tehran": "تهران",
    "کرج": "کرج",
    "اصفهان": "اصفهان",
    "شیراز": "شیراز",
    "مشهد": "مشهد",
    "تبریز": "تبریز",
    "اهواز": "اهواز",
    "رشت": "رشت",
}


def connect(path: str) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def has_col(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return col in {r[1] for r in conn.execute(f"pragma table_info({table})")}


def load_from_db(path: str, brand_allow: set[str] | None = None) -> list[dict]:
    if not Path(path).exists():
        return []
    conn = connect(path)
    if not table_exists(conn, "reviews") or not table_exists(conn, "branches"):
        return []
    bdel = "COALESCE(b.is_deleted,0)=0" if has_col(conn, "branches", "is_deleted") else "1=1"
    rdel = "COALESCE(r.is_deleted,0)=0" if has_col(conn, "reviews", "is_deleted") else "1=1"
    has_owner = has_col(conn, "reviews", "owner_response")
    has_owner_at = has_col(conn, "reviews", "owner_response_at")
    has_lat = has_col(conn, "branches", "latitude")
    sql = f"""
    SELECT
      co.name AS brand,
      b.name AS branch_name,
      COALESCE(b.city,'') AS city,
      COALESCE(b.province,'') AS province,
      COALESCE(b.address,'') AS full_address,
      {"b.latitude" if has_lat else "NULL"} AS latitude,
      {"b.longitude" if has_lat else "NULL"} AS longitude,
      COALESCE(b.maps_url,'') AS maps_url,
      COALESCE(b.place_id,'') AS place_id,
      r.id AS rid,
      COALESCE(r.external_id,'') AS external_id,
      COALESCE(r.author,'') AS reviewer_name,
      r.rating AS rating,
      COALESCE(r.text,'') AS review_text,
      COALESCE(r.published_at,'') AS review_date,
      COALESCE(r.source,'google_maps') AS review_source,
      {"COALESCE(r.owner_response,'')" if has_owner else "''"} AS company_reply,
      {"COALESCE(r.owner_response_at,'')" if has_owner_at else "''"} AS reply_date
    FROM reviews r
    JOIN branches b ON b.id = r.branch_id AND {bdel}
    JOIN companies co ON co.id = b.company_id
    WHERE {rdel}
    """
    rows = []
    for r in conn.execute(sql):
        brand = r["brand"]
        # Normalize FA names
        brand_norm = {
            "تیپاکس": "Tipax",
            "چاپار": "Chapar",
            "پست": "Post",
            "پست ایران": "Post",
            "ماهکس": "Mahex",
            "الوپیک": "AloPeyk",
        }.get(brand, brand)
        if brand_allow and brand_norm not in brand_allow and brand not in brand_allow:
            continue
        reply = (r["company_reply"] or "").strip()
        rid_src = r["external_id"] or f"{path}:{r['rid']}"
        review_id = hashlib.sha256(
            f"{brand_norm}|{r['place_id']}|{rid_src}|{r['review_text'][:80]}".encode()
        ).hexdigest()[:16]
        rows.append(
            {
                "review_id": review_id,
                "brand": brand_norm,
                "branch_name": r["branch_name"] or "",
                "province": r["province"] or "",
                "city": r["city"] or "",
                "full_address": r["full_address"] or "",
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "review_date": r["review_date"] or "",
                "review_text": r["review_text"] or "",
                "rating": float(r["rating"] or 0),
                "review_source": r["review_source"] or "google_maps",
                "review_url": r["maps_url"] or "",
                "reviewer_name": r["reviewer_name"] or "",
                "likes_count": None,
                "reply_exists": bool(reply),
                "company_reply": reply,
                "reply_date": r["reply_date"] or "",
                "place_id": r["place_id"] or "",
                "_db": path,
            }
        )
    conn.close()
    return rows


def enrich(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        nlp = analyze_review(r.get("review_text") or "", r.get("rating"))
        # fill city from address if empty
        city = r.get("city") or ""
        if not city:
            addr = f"{r.get('full_address','')} {r.get('branch_name','')}"
            for needle, fa in CITY_HINTS.items():
                if needle in addr.casefold() or needle in addr:
                    city = fa
                    break
        ent = dict(nlp.entities)
        if r.get("branch_name"):
            ent.setdefault("branch_name_mentioned", r["branch_name"])
        if city:
            ent.setdefault("city", city)
        if r.get("province"):
            ent.setdefault("province", r["province"])
        row = {
            **r,
            "city": city,
            "sentiment": nlp.sentiment,
            "emotion": nlp.emotion,
            "complaint_category": nlp.complaint_category,
            "urgency": nlp.urgency,
            "confidence_score": nlp.confidence_score,
            "entities_json": json.dumps(ent, ensure_ascii=False),
            "entities": ent,
        }
        out.append(row)
    return out


def cell(v):
    if v is None or v == "":
        return NULL
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({h: cell(row.get(h)) for h in headers})


def build_tables(reviews: list[dict]) -> dict[str, tuple[list[str], list[dict]]]:
    # Branch quality
    by_branch: dict[tuple, list[dict]] = defaultdict(list)
    for r in reviews:
        key = (r["brand"], r["branch_name"], r.get("city") or "", r.get("province") or "")
        by_branch[key].append(r)

    branch_rows = []
    for (brand, bname, city, prov), rs in by_branch.items():
        ratings = [float(x["rating"]) for x in rs if x.get("rating") is not None]
        n = len(rs)
        pos = sum(1 for x in rs if x.get("sentiment") == "Positive")
        neg = sum(1 for x in rs if x.get("sentiment") == "Negative")
        complaints = sum(1 for x in rs if x.get("sentiment") == "Negative")
        avg = round(sum(ratings) / len(ratings), 4) if ratings else None
        # sentiment_score 0-100: positive-weighted
        sent_score = round(100.0 * pos / n, 2) if n else None
        confs = [int(x.get("confidence_score") or 0) for x in rs]
        avg_conf = sum(confs) / len(confs) if confs else 0
        if avg_conf >= 70 and n >= 5:
            data_conf = "زیاد"
        elif avg_conf >= 45 and n >= 2:
            data_conf = "متوسط"
        else:
            data_conf = "کم"
        coords = any(x.get("latitude") not in (None, "", NULL) for x in rs)
        branch_rows.append(
            {
                "brand_name": brand,
                "branch_name": bname,
                "city": city or None,
                "province": prov or None,
                "review_count": n,
                "average_rating": avg,
                "sentiment_score": sent_score,
                "complaint_rate": round(100.0 * complaints / n, 2) if n else None,
                "positive_rate": round(100.0 * pos / n, 2) if n else None,
                "negative_rate": round(100.0 * neg / n, 2) if n else None,
                "data_confidence": data_conf,
                "has_coords": coords,
            }
        )

    # Brand summary
    brands = sorted({r["brand"] for r in reviews})
    brand_rows = []
    for brand in brands:
        rs = [r for r in reviews if r["brand"] == brand]
        ratings = [float(x["rating"]) for x in rs if x.get("rating") is not None]
        pos = sum(1 for x in rs if x.get("sentiment") == "Positive")
        neu = sum(1 for x in rs if x.get("sentiment") == "Neutral")
        neg = sum(1 for x in rs if x.get("sentiment") == "Negative")
        n = len(rs)
        brand_rows.append(
            {
                "brand_name": brand,
                "total_reviews": n,
                "average_rating": round(sum(ratings) / len(ratings), 4) if ratings else None,
                "positive_reviews": pos,
                "neutral_reviews": neu,
                "negative_reviews": neg,
                "positive_percent": round(100.0 * pos / n, 2) if n else None,
                "negative_percent": round(100.0 * neg / n, 2) if n else None,
                "branch_count": len({r["branch_name"] for r in rs}),
            }
        )

    reviews_clean = []
    for r in reviews:
        reviews_clean.append(
            {
                "review_id": r["review_id"],
                "brand": r["brand"],
                "branch_name": r["branch_name"],
                "province": r.get("province") or None,
                "city": r.get("city") or None,
                "full_address": r.get("full_address") or None,
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "review_date": r.get("review_date") or None,
                "review_text": r.get("review_text") or None,
                "rating": r.get("rating"),
                "review_source": r.get("review_source") or None,
                "review_url": r.get("review_url") or None,
                "reviewer_name": r.get("reviewer_name") or None,
                "likes_count": r.get("likes_count"),
                "reply_exists": r.get("reply_exists"),
                "company_reply": r.get("company_reply") or None,
                "reply_date": r.get("reply_date") or None,
                "sentiment": r.get("sentiment"),
                "emotion": r.get("emotion"),
                "complaint_category": r.get("complaint_category"),
                "urgency": r.get("urgency"),
                "confidence_score": r.get("confidence_score"),
            }
        )

    entities_rows = []
    for r in reviews:
        ent = r.get("entities") or {}
        if not ent:
            entities_rows.append(
                {
                    "review_id": r["review_id"],
                    "brand": r["brand"],
                    "branch_name": r["branch_name"],
                    "entity_type": None,
                    "entity_value": None,
                }
            )
            continue
        for k, v in ent.items():
            entities_rows.append(
                {
                    "review_id": r["review_id"],
                    "brand": r["brand"],
                    "branch_name": r["branch_name"],
                    "entity_type": k,
                    "entity_value": v,
                }
            )

    complaints = []
    for r in reviews:
        if r.get("sentiment") != "Negative":
            continue
        complaints.append(
            {
                "review_id": r["review_id"],
                "brand": r["brand"],
                "branch_name": r["branch_name"],
                "city": r.get("city") or None,
                "complaint_category": r.get("complaint_category"),
                "urgency": r.get("urgency"),
                "rating": r.get("rating"),
                "review_text": r.get("review_text") or None,
                "confidence_score": r.get("confidence_score"),
            }
        )

    # dashboard_dataset = denormalized analytics-ready flat file
    dashboard = []
    branch_lookup = {
        (b["brand_name"], b["branch_name"], b.get("city") or ""): b for b in branch_rows
    }
    for r in reviews:
        bmeta = branch_lookup.get((r["brand"], r["branch_name"], r.get("city") or ""), {})
        dashboard.append(
            {
                "review_id": r["review_id"],
                "brand": r["brand"],
                "branch_name": r["branch_name"],
                "city": r.get("city") or None,
                "province": r.get("province") or None,
                "rating": r.get("rating"),
                "sentiment": r.get("sentiment"),
                "emotion": r.get("emotion"),
                "complaint_category": r.get("complaint_category"),
                "urgency": r.get("urgency"),
                "confidence_score": r.get("confidence_score"),
                "review_source": r.get("review_source"),
                "review_date": r.get("review_date") or None,
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "branch_review_count": bmeta.get("review_count"),
                "branch_average_rating": bmeta.get("average_rating"),
                "branch_sentiment_score": bmeta.get("sentiment_score"),
                "branch_complaint_rate": bmeta.get("complaint_rate"),
                "branch_data_confidence": bmeta.get("data_confidence"),
            }
        )

    return {
        "brand_summary": (
            [
                "brand_name",
                "total_reviews",
                "average_rating",
                "positive_reviews",
                "neutral_reviews",
                "negative_reviews",
                "positive_percent",
                "negative_percent",
                "branch_count",
            ],
            brand_rows,
        ),
        "branch_summary": (
            [
                "brand_name",
                "branch_name",
                "city",
                "province",
                "review_count",
                "average_rating",
                "sentiment_score",
                "complaint_rate",
                "positive_rate",
                "negative_rate",
                "data_confidence",
            ],
            branch_rows,
        ),
        "reviews_clean": (
            [
                "review_id",
                "brand",
                "branch_name",
                "province",
                "city",
                "full_address",
                "latitude",
                "longitude",
                "review_date",
                "review_text",
                "rating",
                "review_source",
                "review_url",
                "reviewer_name",
                "likes_count",
                "reply_exists",
                "company_reply",
                "reply_date",
                "sentiment",
                "emotion",
                "complaint_category",
                "urgency",
                "confidence_score",
            ],
            reviews_clean,
        ),
        "entities": (
            ["review_id", "brand", "branch_name", "entity_type", "entity_value"],
            entities_rows,
        ),
        "complaints": (
            [
                "review_id",
                "brand",
                "branch_name",
                "city",
                "complaint_category",
                "urgency",
                "rating",
                "review_text",
                "confidence_score",
            ],
            complaints,
        ),
        "dashboard_dataset": (
            [
                "review_id",
                "brand",
                "branch_name",
                "city",
                "province",
                "rating",
                "sentiment",
                "emotion",
                "complaint_category",
                "urgency",
                "confidence_score",
                "review_source",
                "review_date",
                "latitude",
                "longitude",
                "branch_review_count",
                "branch_average_rating",
                "branch_sentiment_score",
                "branch_complaint_rate",
                "branch_data_confidence",
            ],
            dashboard,
        ),
    }


def coverage_report(reviews: list[dict]) -> dict:
    branches = {(r["brand"], r["branch_name"]) for r in reviews}
    cities = {r.get("city") for r in reviews if r.get("city")}
    provinces = {r.get("province") for r in reviews if r.get("province")}
    n = len(reviews) or 1
    with_coords = sum(
        1
        for r in reviews
        if r.get("latitude") not in (None, "", NULL) and r.get("longitude") not in (None, "", NULL)
    )
    with_date = sum(1 for r in reviews if (r.get("review_date") or "").strip())
    with_reply = sum(1 for r in reviews if r.get("reply_exists") or (r.get("company_reply") or "").strip())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brands": sorted({r["brand"] for r in reviews}),
        "branch_count": len(branches),
        "review_count": len(reviews),
        "city_count": len(cities),
        "province_count": len(provinces),
        "pct_with_coordinates": round(100.0 * with_coords / n, 2),
        "pct_with_date": round(100.0 * with_date / n, 2),
        "pct_with_company_reply": round(100.0 * with_reply / n, 2),
        "sources": sorted({r.get("review_source") or "unknown" for r in reviews}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 11 clean dataset builder")
    parser.add_argument(
        "--dbs",
        nargs="*",
        default=[
            "data/phase11_multisource.db",
            "data/analytics_demo.db",
            "data/tipax_iran.db",
        ],
    )
    parser.add_argument(
        "--brands",
        nargs="*",
        default=list(BRANDS_PHASE11),
        help="Brands to include (default: Chapar Post Mahex AloPeyk)",
    )
    parser.add_argument(
        "--include-tipax",
        action="store_true",
        help="Also include Tipax from tipax_iran.db",
    )
    parser.add_argument("--out-dir", default="/opt/cursor/artifacts/phase11_dataset")
    parser.add_argument("--also-docs", action="store_true", default=True)
    args = parser.parse_args()

    allow = set(args.brands)
    if args.include_tipax:
        allow.add("Tipax")

    raw: list[dict] = []
    for db in args.dbs:
        raw.extend(load_from_db(db, brand_allow=allow))

    # Cross-db exact id dedupe first
    by_id = {}
    for r in raw:
        by_id[r["review_id"]] = r
    merged = list(by_id.values())

    enriched = enrich(merged)
    cleaned, dropped = dedupe_reviews(enriched, threshold=0.90)

    tables = build_tables(cleaned)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, (headers, rows) in tables.items():
        write_csv(out / f"{name}.csv", headers, rows)

    report = coverage_report(cleaned)
    report["duplicates_dropped"] = dropped
    report["input_rows_before_dedupe"] = len(enriched)
    (out / "coverage_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if args.also_docs:
        docs = Path("docs/phase11_dataset")
        docs.mkdir(parents=True, exist_ok=True)
        for name, (headers, rows) in tables.items():
            write_csv(docs / f"{name}.csv", headers, rows)
        (docs / "coverage_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # project-root convenience zip
        import zipfile

        zpath = Path("BrandMonitor_Phase11_Dataset.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in tables:
                zf.write(out / f"{name}.csv", arcname=f"{name}.csv")
            zf.write(out / "coverage_report.json", arcname="coverage_report.json")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
