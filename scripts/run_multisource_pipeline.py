#!/usr/bin/env python3
"""
Multi-source intelligence pipeline.

Collects/imports from registered providers → normalize → cross-source dedupe →
NLP → reviews_master SQLite → analytics CSV exports.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from collectors.multisource.dedupe_cross import cross_source_dedupe
from collectors.multisource.nlp_platform import analyze_platform_review
from collectors.normalize.text import (
    infer_city_province,
    is_spam_or_empty,
    normalize_branch_name,
    normalize_city,
    normalize_date,
    normalize_persian,
    normalize_province,
    normalize_rating,
)
from collectors.providers import build_provider, list_providers
from collectors.providers.base import UnifiedReview

BRANDS = ["Tipax", "Iran Post", "Chapar", "AloPeyk", "Mahex"]
NULL = "NULL"


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS reviews_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            brand TEXT NOT NULL,
            branch TEXT NOT NULL DEFAULT '',
            province TEXT NOT NULL DEFAULT '',
            city TEXT NOT NULL DEFAULT '',
            latitude REAL,
            longitude REAL,
            rating REAL,
            review TEXT NOT NULL DEFAULT '',
            review_date TEXT NOT NULL DEFAULT '',
            reviewer TEXT NOT NULL DEFAULT '',
            reply TEXT NOT NULL DEFAULT '',
            reply_date TEXT NOT NULL DEFAULT '',
            photos_count INTEGER,
            url TEXT NOT NULL DEFAULT '',
            scraped_at TEXT NOT NULL DEFAULT '',
            external_id TEXT NOT NULL DEFAULT '',
            app_version TEXT NOT NULL DEFAULT '',
            total_votes INTEGER,
            sentiment TEXT,
            emotion TEXT,
            complaint_category TEXT,
            complaint_subcategory TEXT,
            urgency TEXT,
            confidence_score INTEGER,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(source, brand, branch, review, review_date, reviewer)
        );
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            finished_at TEXT,
            stats_json TEXT
        );
        CREATE TABLE IF NOT EXISTS pipeline_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            kind TEXT,
            detail TEXT,
            created_at TEXT
        );
        """
    )
    conn.commit()


def normalize_row(r: UnifiedReview) -> UnifiedReview | None:
    r.brand = normalize_persian(r.brand) or r.brand
    # canonicalize brand labels
    brand_map = {
        "تیپاکس": "Tipax",
        "tipax": "Tipax",
        "چاپار": "Chapar",
        "chapar": "Chapar",
        "پست": "Iran Post",
        "پست ایران": "Iran Post",
        "post": "Iran Post",
        "iran post": "Iran Post",
        "ماهکس": "Mahex",
        "mahex": "Mahex",
        "الوپیک": "AloPeyk",
        "alopeyk": "AloPeyk",
    }
    r.brand = brand_map.get(r.brand.casefold(), brand_map.get(r.brand, r.brand))
    r.branch = normalize_branch_name(r.branch) or normalize_persian(r.branch)
    addr = str((r.metadata or {}).get("address") or "")
    city, prov = infer_city_province(addr, r.city, r.province)
    r.city = normalize_city(city or r.city)
    r.province = normalize_province(prov or r.province)
    r.review = normalize_persian(r.review)
    r.reviewer = normalize_persian(r.reviewer)
    r.reply = normalize_persian(r.reply)
    r.review_date = normalize_date(r.review_date)
    r.reply_date = normalize_date(r.reply_date)
    r.rating = normalize_rating(r.rating)
    if is_spam_or_empty(r.review, r.rating):
        return None
    return r


def cell(v):
    if v is None or v == "":
        return NULL
    return v


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({h: cell(row.get(h)) for h in headers})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/multisource_master.db")
    parser.add_argument("--out-dir", default="/opt/cursor/artifacts/multisource_platform")
    parser.add_argument("--brands", nargs="*", default=BRANDS)
    parser.add_argument(
        "--sources",
        nargs="*",
        default=["google_maps", "neshan", "balad", "cafebazaar", "myket"],
    )
    args = parser.parse_args()

    started = datetime.now(timezone.utc).isoformat()
    stats = {
        "failed_requests": 0,
        "missing_branches": 0,
        "invalid_reviews": 0,
        "duplicate_reviews": 0,
        "collected_by_source": {},
        "providers": list_providers(),
    }
    issues: list[dict] = []

    raw: list[UnifiedReview] = []
    for source in args.sources:
        try:
            provider = build_provider(source)
        except Exception as exc:  # noqa: BLE001
            stats["failed_requests"] += 1
            issues.append({"kind": "provider_init", "detail": f"{source}: {exc}"})
            continue
        health = provider.healthcheck()
        if not health.get("ready") and source != "google_maps":
            issues.append({"kind": "provider_not_ready", "detail": json.dumps(health, ensure_ascii=False)})
        for brand in args.brands:
            try:
                rows = provider.collect(brand)
            except Exception as exc:  # noqa: BLE001
                stats["failed_requests"] += 1
                issues.append({"kind": "collect_failed", "detail": f"{source}/{brand}: {exc}"})
                continue
            stats["collected_by_source"][source] = stats["collected_by_source"].get(source, 0) + len(rows)
            raw.extend(rows)

    # Normalize + drop invalid
    normalized: list[UnifiedReview] = []
    for r in raw:
        n = normalize_row(r)
        if n is None:
            stats["invalid_reviews"] += 1
            issues.append({"kind": "invalid_review", "detail": f"{r.source}|{r.brand}|{r.branch}"})
            continue
        if not n.branch:
            stats["missing_branches"] += 1
            n.branch = "UNKNOWN"
        normalized.append(n)

    deduped, dropped = cross_source_dedupe(normalized, text_threshold=0.90)
    stats["duplicate_reviews"] = dropped

    # Persist
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    ensure_schema(conn)
    conn.execute("DELETE FROM reviews_master")
    enriched_rows = []
    for r in deduped:
        nlp = analyze_platform_review(r.review, r.rating, source=r.source)
        meta = dict(r.metadata or {})
        conn.execute(
            """
            INSERT OR REPLACE INTO reviews_master(
              source, brand, branch, province, city, latitude, longitude, rating,
              review, review_date, reviewer, reply, reply_date, photos_count, url,
              scraped_at, external_id, app_version, total_votes,
              sentiment, emotion, complaint_category, complaint_subcategory,
              urgency, confidence_score, metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                r.source,
                r.brand,
                r.branch,
                r.province,
                r.city,
                r.latitude,
                r.longitude,
                r.rating,
                r.review,
                r.review_date,
                r.reviewer,
                r.reply,
                r.reply_date,
                r.photos_count,
                r.url,
                r.scraped_at,
                r.external_id,
                r.app_version,
                r.total_votes,
                nlp.sentiment,
                nlp.emotion,
                nlp.complaint_category,
                nlp.complaint_subcategory,
                nlp.urgency,
                nlp.confidence_score,
                json.dumps(meta, ensure_ascii=False),
            ),
        )
        enriched_rows.append(
            {
                "source": r.source,
                "brand": r.brand,
                "branch": r.branch,
                "province": r.province,
                "city": r.city,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "rating": r.rating,
                "review": r.review,
                "review_date": r.review_date,
                "reviewer": r.reviewer,
                "reply": r.reply,
                "reply_date": r.reply_date,
                "photos_count": r.photos_count,
                "url": r.url,
                "scraped_at": r.scraped_at,
                "app_version": r.app_version,
                "total_votes": r.total_votes,
                "sentiment": nlp.sentiment,
                "emotion": nlp.emotion,
                "complaint_category": nlp.complaint_category,
                "complaint_subcategory": nlp.complaint_subcategory,
                "urgency": nlp.urgency,
                "confidence_score": nlp.confidence_score,
            }
        )
    finished = datetime.now(timezone.utc).isoformat()
    stats.update(
        {
            "started_at": started,
            "finished_at": finished,
            "raw_count": len(raw),
            "normalized_count": len(normalized),
            "final_count": len(deduped),
            "brands": sorted({r.brand for r in deduped}),
            "sources_present": sorted({r.source for r in deduped}),
        }
    )
    cur = conn.execute(
        "INSERT INTO pipeline_runs(started_at, finished_at, stats_json) VALUES (?,?,?)",
        (started, finished, json.dumps(stats, ensure_ascii=False)),
    )
    run_id = cur.lastrowid
    for issue in issues[:500]:
        conn.execute(
            "INSERT INTO pipeline_issues(run_id, kind, detail, created_at) VALUES (?,?,?,?)",
            (run_id, issue["kind"], issue["detail"], finished),
        )
    conn.commit()

    # ---- CSV exports ----
    out = Path(args.out_dir)
    docs = Path("docs/multisource_platform")
    for folder in (out, docs):
        folder.mkdir(parents=True, exist_ok=True)

    reviews_master = []
    for i, r in enumerate(enriched_rows, start=1):
        reviews_master.append({"id": i, **r})

    write_csv(
        out / "reviews_master.csv",
        [
            "id",
            "source",
            "brand",
            "branch",
            "province",
            "city",
            "latitude",
            "longitude",
            "rating",
            "review",
            "review_date",
            "reviewer",
            "reply",
            "reply_date",
            "photos_count",
            "url",
            "scraped_at",
        ],
        reviews_master,
    )
    write_csv(
        out / "reviews_multisource.csv",
        [
            "id",
            "source",
            "brand",
            "branch",
            "city",
            "province",
            "rating",
            "sentiment",
            "emotion",
            "complaint_category",
            "urgency",
            "confidence_score",
            "review_date",
        ],
        reviews_master,
    )

    # branches
    by_branch = defaultdict(list)
    for r in enriched_rows:
        by_branch[(r["brand"], r["branch"], r["city"], r["province"])].append(r)
    branch_rows = []
    for (brand, branch, city, prov), rs in by_branch.items():
        ratings = [float(x["rating"]) for x in rs if x.get("rating") is not None]
        sentiments = Counter(x["sentiment"] for x in rs)
        complaints = Counter(
            x["complaint_category"] for x in rs if x.get("sentiment") == "Negative"
        )
        dates = [x["review_date"] for x in rs if x.get("review_date")]
        branch_rows.append(
            {
                "brand": brand,
                "branch": branch,
                "city": city,
                "province": prov,
                "average_rating": round(sum(ratings) / len(ratings), 4) if ratings else None,
                "total_reviews": len(rs),
                "complaint_count": sum(1 for x in rs if x["sentiment"] == "Negative"),
                "complaint_distribution": json.dumps(dict(complaints), ensure_ascii=False),
                "sentiment_distribution": json.dumps(dict(sentiments), ensure_ascii=False),
                "last_review_date": max(dates) if dates else None,
                "sources": ",".join(sorted({x["source"] for x in rs})),
            }
        )
    write_csv(
        out / "branches.csv",
        [
            "brand",
            "branch",
            "city",
            "province",
            "average_rating",
            "total_reviews",
            "complaint_count",
            "complaint_distribution",
            "sentiment_distribution",
            "last_review_date",
            "sources",
        ],
        branch_rows,
    )

    # brands
    brand_rows = []
    for brand in sorted({r["brand"] for r in enriched_rows}):
        rs = [r for r in enriched_rows if r["brand"] == brand]
        ratings = [float(x["rating"]) for x in rs if x.get("rating") is not None]
        pos = sum(1 for x in rs if x["sentiment"] == "Positive")
        neg = sum(1 for x in rs if x["sentiment"] == "Negative")
        n = len(rs) or 1
        complaints = Counter(x["complaint_category"] for x in rs if x["sentiment"] == "Negative")
        prov_map = defaultdict(list)
        city_map = defaultdict(list)
        for x in rs:
            if x.get("province"):
                prov_map[x["province"]].append(x)
            if x.get("city"):
                city_map[x["city"]].append(x)

        def rank_avg(mp):
            scored = []
            for k, grp in mp.items():
                rts = [float(g["rating"]) for g in grp if g.get("rating") is not None]
                if rts:
                    scored.append((k, round(sum(rts) / len(rts), 3), len(grp)))
            return sorted(scored, key=lambda t: (-t[1], -t[2]))[:5]

        b_branches = [b for b in branch_rows if b["brand"] == brand and b["average_rating"] is not None]
        best = sorted(b_branches, key=lambda b: (-b["average_rating"], -b["total_reviews"]))[:5]
        worst = sorted(b_branches, key=lambda b: (b["average_rating"], -b["total_reviews"]))[:5]
        # monthly trend
        month_map = defaultdict(list)
        for x in rs:
            m = (x.get("review_date") or "")[:7]
            if len(m) == 7 and m[4] == "-":
                month_map[m].append(x)
        monthly = []
        for m in sorted(month_map):
            grp = month_map[m]
            rts = [float(g["rating"]) for g in grp if g.get("rating") is not None]
            monthly.append(
                {
                    "month": m,
                    "reviews": len(grp),
                    "avg_rating": round(sum(rts) / len(rts), 3) if rts else None,
                }
            )
        brand_rows.append(
            {
                "brand": brand,
                "overall_rating": round(sum(ratings) / len(ratings), 4) if ratings else None,
                "total_reviews": len(rs),
                "positive_percent": round(100.0 * pos / n, 2),
                "negative_percent": round(100.0 * neg / n, 2),
                "complaint_distribution": json.dumps(dict(complaints), ensure_ascii=False),
                "province_ranking": json.dumps(rank_avg(prov_map), ensure_ascii=False),
                "city_ranking": json.dumps(rank_avg(city_map), ensure_ascii=False),
                "best_branches": json.dumps(
                    [(b["branch"], b["average_rating"]) for b in best], ensure_ascii=False
                ),
                "worst_branches": json.dumps(
                    [(b["branch"], b["average_rating"]) for b in worst], ensure_ascii=False
                ),
                "monthly_trend": json.dumps(monthly, ensure_ascii=False),
                "review_growth": json.dumps(
                    [
                        {
                            "month": m["month"],
                            "reviews": m["reviews"],
                            "delta": m["reviews"]
                            - (monthly[i - 1]["reviews"] if i else 0),
                        }
                        for i, m in enumerate(monthly)
                    ],
                    ensure_ascii=False,
                ),
            }
        )
    write_csv(
        out / "brands.csv",
        [
            "brand",
            "overall_rating",
            "total_reviews",
            "positive_percent",
            "negative_percent",
            "complaint_distribution",
            "province_ranking",
            "city_ranking",
            "best_branches",
            "worst_branches",
            "monthly_trend",
            "review_growth",
        ],
        brand_rows,
    )

    complaints = [
        {
            "brand": r["brand"],
            "branch": r["branch"],
            "source": r["source"],
            "city": r["city"],
            "complaint_category": r["complaint_category"],
            "complaint_subcategory": r["complaint_subcategory"],
            "urgency": r["urgency"],
            "sentiment": r["sentiment"],
            "rating": r["rating"],
            "review": r["review"],
            "review_date": r["review_date"],
        }
        for r in enriched_rows
        if r["sentiment"] == "Negative"
    ]
    write_csv(
        out / "complaints.csv",
        [
            "brand",
            "branch",
            "source",
            "city",
            "complaint_category",
            "complaint_subcategory",
            "urgency",
            "sentiment",
            "rating",
            "review",
            "review_date",
        ],
        complaints,
    )

    def summary_counter(key):
        c = Counter(r[key] for r in enriched_rows if r.get(key))
        total = sum(c.values()) or 1
        return [
            {"key": k, "count": v, "percent": round(100.0 * v / total, 2)}
            for k, v in c.most_common()
        ]

    write_csv(
        out / "complaint_summary.csv",
        ["key", "count", "percent"],
        summary_counter("complaint_category"),
    )
    write_csv(
        out / "sentiment_summary.csv",
        ["key", "count", "percent"],
        summary_counter("sentiment"),
    )

    # summaries
    prov_rows = []
    prov_map_all = defaultdict(list)
    for r in enriched_rows:
        if r.get("province"):
            prov_map_all[r["province"]].append(r)
    for p, grp in sorted(prov_map_all.items()):
        rts = [float(x["rating"]) for x in grp if x.get("rating") is not None]
        prov_rows.append(
            {
                "province": p,
                "reviews": len(grp),
                "avg_rating": round(sum(rts) / len(rts), 4) if rts else None,
                "brands": len({x["brand"] for x in grp}),
            }
        )
    write_csv(out / "province_summary.csv", ["province", "reviews", "avg_rating", "brands"], prov_rows)

    city_rows = []
    city_map_all = defaultdict(list)
    for r in enriched_rows:
        if r.get("city"):
            city_map_all[r["city"]].append(r)
    for cname, grp in sorted(city_map_all.items()):
        rts = [float(x["rating"]) for x in grp if x.get("rating") is not None]
        city_rows.append(
            {
                "city": cname,
                "reviews": len(grp),
                "avg_rating": round(sum(rts) / len(rts), 4) if rts else None,
                "brands": len({x["brand"] for x in grp}),
            }
        )
    write_csv(out / "city_summary.csv", ["city", "reviews", "avg_rating", "brands"], city_rows)

    src_rows = []
    src_map = defaultdict(list)
    for r in enriched_rows:
        src_map[r["source"]].append(r)
    for s, grp in sorted(src_map.items()):
        rts = [float(x["rating"]) for x in grp if x.get("rating") is not None]
        src_rows.append(
            {
                "source": s,
                "reviews": len(grp),
                "avg_rating": round(sum(rts) / len(rts), 4) if rts else None,
                "brands": len({x["brand"] for x in grp}),
            }
        )
    write_csv(out / "source_summary.csv", ["source", "reviews", "avg_rating", "brands"], src_rows)

    app_rows = [
        r
        for r in enriched_rows
        if r["source"] in {"cafebazaar", "myket"}
    ]
    write_csv(
        out / "appstore_reviews.csv",
        [
            "source",
            "brand",
            "branch",
            "rating",
            "review",
            "review_date",
            "reviewer",
            "reply",
            "reply_date",
            "app_version",
            "total_votes",
            "url",
        ],
        app_rows,
    )

    # coverage + stats
    n = len(enriched_rows) or 1
    coverage = {
        "branch_count": len(by_branch),
        "review_count": len(enriched_rows),
        "city_count": len(city_map_all),
        "province_count": len(prov_map_all),
        "pct_with_coordinates": round(
            100.0
            * sum(1 for r in enriched_rows if r.get("latitude") is not None and r.get("longitude") is not None)
            / n,
            2,
        ),
        "pct_with_date": round(100.0 * sum(1 for r in enriched_rows if r.get("review_date")) / n, 2),
        "pct_with_company_reply": round(
            100.0 * sum(1 for r in enriched_rows if (r.get("reply") or "").strip()) / n, 2
        ),
        "brands": sorted({r["brand"] for r in enriched_rows}),
        "sources": sorted({r["source"] for r in enriched_rows}),
    }
    stats["coverage"] = coverage
    (out / "execution_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "coverage_statistics.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # mirror to docs + zip
    import shutil
    import zipfile

    for p in out.glob("*.csv"):
        shutil.copy(p, docs / p.name)
    for p in out.glob("*.json"):
        shutil.copy(p, docs / p.name)
    zpath = Path("BrandMonitor_Multisource_Platform.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out.glob("*")):
            zf.write(p, arcname=p.name)
    shutil.copy(zpath, "/opt/cursor/artifacts/BrandMonitor_Multisource_Platform.zip")

    conn.close()
    print(json.dumps({"stats": stats, "coverage": coverage, "out_dir": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
