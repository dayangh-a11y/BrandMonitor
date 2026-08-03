#!/usr/bin/env python3
"""
Phase 9 — Data Validation & Quality Audit for Tipax production crawl.

Read-only against the existing SQLite dataset. Does not modify crawler,
schema, or UI.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collectors.iran_geo import IRAN_PROVINCES

# Tipax annual report 1403: 1336 contact points / ~1300+ agencies (public claims).
OFFICIAL_BRANCH_ESTIMATE = 1336
OFFICIAL_BRANCH_SOURCE = (
    "Tipax annual report 1403 / public claims: ~1,300+ agencies; "
    "DMBoard summary cites 1,336 contact points (up from 1,132 in 1402)."
)

SUSPICIOUS_REVIEW_COUNT = 320  # recurring Maps parse artifact observed in crawl
EMPTY_TEXT_RE = re.compile(r"^[\s\W_]*$", re.UNICODE)


@dataclass
class QualityScores:
    completeness: float
    consistency: float
    uniqueness: float
    accuracy: float
    freshness: float

    @property
    def overall(self) -> float:
        return round(
            0.25 * self.completeness
            + 0.20 * self.consistency
            + 0.20 * self.uniqueness
            + 0.25 * self.accuracy
            + 0.10 * self.freshness,
            1,
        )


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def _branch_key(row: sqlite3.Row) -> str:
    place = (row["place_id"] or "").strip()
    if place:
        return f"place:{place}"
    return f"nameaddr:{_norm(row['name'])}|{_norm(row['address'])}"


def _detect_language(text: str) -> str:
    if re.search(r"[\u0600-\u06FF]", text or ""):
        return "fa"
    if re.search(r"[A-Za-z]", text or ""):
        return "en"
    return ""


def _looks_like_date(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    if re.search(r"\d{4}-\d{2}-\d{2}", v):
        return True
    if re.search(r"\b(ago|yesterday|week|month|year|روز|هفته|ماه|سال|دیروز)\b", v, re.I):
        return True
    if re.search(r"\d", v):
        return True
    return False


def load_tipax(conn: sqlite3.Connection) -> tuple[int, list[sqlite3.Row], list[sqlite3.Row]]:
    company = conn.execute(
        "SELECT id FROM companies WHERE name = ? ORDER BY id LIMIT 1", ("Tipax",)
    ).fetchone()
    if company is None:
        raise SystemExit("Tipax company not found in database")
    company_id = int(company["id"])
    branches = conn.execute(
        """
        SELECT * FROM branches
        WHERE company_id = ? AND COALESCE(is_deleted, 0) = 0
        ORDER BY id
        """,
        (company_id,),
    ).fetchall()
    reviews = conn.execute(
        """
        SELECT r.*
        FROM reviews r
        JOIN branches b ON b.id = r.branch_id
        WHERE b.company_id = ? AND COALESCE(b.is_deleted, 0) = 0
          AND COALESCE(r.is_deleted, 0) = 0
        ORDER BY r.id
        """,
        (company_id,),
    ).fetchall()
    return company_id, branches, reviews


def audit_branches(branches: list[sqlite3.Row], reviews: list[sqlite3.Row]) -> dict[str, Any]:
    reviews_by_branch: dict[int, int] = Counter(int(r["branch_id"]) for r in reviews)
    stored_count_vs_actual = []

    by_key: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for b in branches:
        by_key[_branch_key(b)].append(b)

    duplicate_groups = {k: rows for k, rows in by_key.items() if len(rows) > 1}
    duplicate_branch_rows = sum(len(v) - 1 for v in duplicate_groups.values())

    missing_coords = [b for b in branches if b["latitude"] is None or b["longitude"] is None]
    missing_phone = [b for b in branches if not (b["phone"] or "").strip()]
    missing_url = [b for b in branches if not (b["maps_url"] or "").strip()]
    zero_reviews = [b for b in branches if reviews_by_branch.get(int(b["id"]), 0) == 0]
    suspicious = []
    for b in branches:
        claimed = int(b["review_count"] or 0)
        actual = reviews_by_branch.get(int(b["id"]), 0)
        reasons = []
        if claimed == SUSPICIOUS_REVIEW_COUNT:
            reasons.append(f"claimed_review_count={SUSPICIOUS_REVIEW_COUNT}_artifact")
        if claimed > 0 and actual == 0:
            reasons.append("claimed_reviews_but_none_collected")
        if claimed >= 50 and actual > 0 and actual <= 10 and claimed >= actual * 5:
            reasons.append("collected_far_below_claimed_count")
        if not (b["name"] or "").strip():
            reasons.append("empty_name")
        if reasons:
            suspicious.append({"branch": b, "reasons": reasons, "actual_reviews": actual})

    # Name-only near-duplicates (same normalized name, different place_id)
    by_name: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for b in branches:
        by_name[_norm(b["name"])].append(b)
    name_dup_groups = {
        k: rows
        for k, rows in by_name.items()
        if k and len(rows) > 1 and len({(r["place_id"] or "") for r in rows}) > 1
    }

    validation_rows = []
    for b in branches:
        bid = int(b["id"])
        actual = reviews_by_branch.get(bid, 0)
        issues = []
        if b["latitude"] is None or b["longitude"] is None:
            issues.append("missing_coordinates")
        if not (b["phone"] or "").strip():
            issues.append("missing_phone")
        if not (b["maps_url"] or "").strip():
            issues.append("missing_maps_url")
        if actual == 0:
            issues.append("zero_reviews_collected")
        if int(b["review_count"] or 0) == SUSPICIOUS_REVIEW_COUNT:
            issues.append("suspicious_review_count_320")
        if not (b["province"] or "").strip():
            issues.append("missing_province")
        if not (b["city"] or "").strip():
            issues.append("missing_city")
        validation_rows.append(
            {
                "branch_id": bid,
                "name": b["name"],
                "place_id": b["place_id"] or "",
                "address": b["address"] or "",
                "city": b["city"] or "",
                "province": b["province"] or "",
                "phone": b["phone"] or "",
                "latitude": b["latitude"],
                "longitude": b["longitude"],
                "maps_url": b["maps_url"] or "",
                "google_rating": b["rating"],
                "claimed_review_count": int(b["review_count"] or 0),
                "collected_review_count": actual,
                "issues": "|".join(issues) if issues else "",
                "needs_manual_verify": "yes" if issues else "no",
            }
        )
        stored_count_vs_actual.append((claimed := int(b["review_count"] or 0), actual))

    return {
        "total_unique_branches": len(branches),
        "duplicate_branch_extra_rows": duplicate_branch_rows,
        "duplicate_place_or_nameaddr_groups": len(duplicate_groups),
        "same_name_different_place_groups": len(name_dup_groups),
        "branches_missing_coordinates": len(missing_coords),
        "branches_missing_phone": len(missing_phone),
        "branches_missing_maps_url": len(missing_url),
        "branches_with_zero_reviews": len(zero_reviews),
        "branches_with_suspicious_review_counts": len(suspicious),
        "duplicate_groups_detail": [
            {
                "key": k,
                "count": len(rows),
                "ids": [int(r["id"]) for r in rows],
                "names": [r["name"] for r in rows],
            }
            for k, rows in sorted(duplicate_groups.items(), key=lambda x: -len(x[1]))
        ],
        "name_dup_groups_detail": [
            {
                "name": k,
                "count": len(rows),
                "ids": [int(r["id"]) for r in rows],
                "place_ids": [r["place_id"] for r in rows],
                "cities": [r["city"] for r in rows],
            }
            for k, rows in sorted(name_dup_groups.items(), key=lambda x: -len(x[1]))[:50]
        ],
        "suspicious_detail": [
            {
                "branch_id": int(s["branch"]["id"]),
                "name": s["branch"]["name"],
                "claimed_review_count": int(s["branch"]["review_count"] or 0),
                "actual_reviews": s["actual_reviews"],
                "reasons": s["reasons"],
            }
            for s in suspicious[:100]
        ],
        "validation_rows": validation_rows,
        "manual_verify_candidates": [
            r for r in validation_rows if r["needs_manual_verify"] == "yes"
        ],
    }


def audit_reviews(reviews: list[sqlite3.Row]) -> dict[str, Any]:
    by_external: dict[str, list[sqlite3.Row]] = defaultdict(list)
    by_content: dict[str, list[sqlite3.Row]] = defaultdict(list)
    issues = Counter()
    malformed = []
    language_errors = []
    impossible_ratings = []
    missing_dates = []
    empty = []

    for r in reviews:
        rid = int(r["id"])
        text = r["text"] or ""
        external = (r["external_id"] or "").strip()
        content_hash = (r["content_hash"] or "").strip()
        if external:
            by_external[f"{r['branch_id']}|{external}"].append(r)
        content_key = content_hash or f"{r['branch_id']}|{_norm(text)}|{r['author']}"
        by_content[content_key].append(r)

        if not text.strip() or EMPTY_TEXT_RE.match(text):
            issues["empty_reviews"] += 1
            empty.append(rid)
        if len(text.strip()) < 3:
            issues["malformed_too_short"] += 1
            malformed.append(rid)
        if text.count("\x00"):
            issues["malformed_null_bytes"] += 1
            malformed.append(rid)

        stored_lang = (r["language"] or "").strip().lower()
        detected = _detect_language(text)
        if stored_lang and detected and stored_lang != detected:
            # fa/en mismatch only when both confident
            if stored_lang in {"fa", "en"} and detected in {"fa", "en"}:
                issues["language_detection_errors"] += 1
                language_errors.append(
                    {"review_id": rid, "stored": stored_lang, "detected": detected}
                )
        if not stored_lang and detected:
            issues["language_missing_but_detectable"] += 1

        try:
            rating = float(r["rating"] or 0)
        except (TypeError, ValueError):
            rating = -1
            issues["impossible_ratings"] += 1
            impossible_ratings.append(rid)
        else:
            if rating < 0 or rating > 5:
                issues["impossible_ratings"] += 1
                impossible_ratings.append(rid)

        published = r["published_at"] or ""
        collected = r["collected_at"] or ""
        if not _looks_like_date(published) and not _looks_like_date(collected):
            issues["missing_dates"] += 1
            missing_dates.append(rid)
        elif not _looks_like_date(published):
            issues["missing_published_at"] += 1

    dup_external = {k: v for k, v in by_external.items() if len(v) > 1}
    dup_content = {k: v for k, v in by_content.items() if len(v) > 1}
    duplicate_review_extras = sum(len(v) - 1 for v in dup_content.values())

    return {
        "total_reviews": len(reviews),
        "duplicate_reviews_extra": duplicate_review_extras,
        "duplicate_external_id_groups": len(dup_external),
        "duplicate_content_groups": len(dup_content),
        "empty_reviews": issues["empty_reviews"],
        "malformed_reviews": len(set(malformed)),
        "language_detection_errors": issues["language_detection_errors"],
        "language_missing_but_detectable": issues["language_missing_but_detectable"],
        "impossible_ratings": issues["impossible_ratings"],
        "missing_dates": issues["missing_dates"],
        "missing_published_at": issues["missing_published_at"],
        "owner_responses_present": sum(
            1 for r in reviews if (r["owner_response"] or "").strip()
        ),
        "language_error_samples": language_errors[:20],
        "duplicate_content_samples": [
            {
                "key": k[:80],
                "count": len(rows),
                "review_ids": [int(x["id"]) for x in rows[:5]],
            }
            for k, rows in sorted(dup_content.items(), key=lambda x: -len(x[1]))[:30]
        ],
    }


def match_province(label: str) -> str | None:
    key = (label or "").strip()
    if not key:
        return None
    low = key.casefold()
    for province in IRAN_PROVINCES:
        if low in {province["fa"].casefold(), province["en"].casefold()}:
            return province["en"]
        if province["fa"] in key or province["en"].casefold() in low:
            return province["en"]
    return None


def audit_geography(branches: list[sqlite3.Row]) -> dict[str, Any]:
    by_province_raw: Counter[str] = Counter()
    by_city: Counter[str] = Counter()
    matched: Counter[str] = Counter()
    unmatched_labels: Counter[str] = Counter()

    for b in branches:
        prov = (b["province"] or "").strip() or "Unknown"
        city = (b["city"] or "").strip() or "Unknown"
        by_province_raw[prov] += 1
        by_city[f"{city}||{prov}"] += 1
        known = match_province(prov)
        if known:
            matched[known] += 1
        else:
            unmatched_labels[prov] += 1

    all_official = [p["en"] for p in IRAN_PROVINCES]
    missing = [p for p in all_official if matched.get(p, 0) == 0]
    counts = [matched.get(p, 0) for p in all_official if matched.get(p, 0) > 0]
    median = sorted(counts)[len(counts) // 2] if counts else 0
    low_threshold = max(1, median // 3) if median else 1
    unusually_low = [
        {"province": p, "branches": matched.get(p, 0)}
        for p in all_official
        if 0 < matched.get(p, 0) <= low_threshold
    ]

    province_rows = []
    for p in IRAN_PROVINCES:
        n = matched.get(p["en"], 0)
        status = "ok"
        if n == 0:
            status = "no_branches"
        elif n <= low_threshold:
            status = "unusually_low"
        province_rows.append(
            {
                "province_en": p["en"],
                "province_fa": p["fa"],
                "branch_count": n,
                "status": status,
            }
        )

    city_rows = []
    for key, n in by_city.most_common():
        city, prov = key.split("||", 1)
        city_rows.append({"city": city, "province": prov, "branch_count": n})

    return {
        "branches_per_province_matched": dict(matched.most_common()),
        "branches_per_province_raw": dict(by_province_raw.most_common()),
        "branches_per_city": city_rows,
        "provinces_with_no_branches": missing,
        "provinces_unusually_low": unusually_low,
        "unmatched_province_labels": dict(unmatched_labels.most_common(30)),
        "province_rows": province_rows,
        "known_provinces_hit": len(matched),
        "known_provinces_total": len(all_official),
        "low_threshold_used": low_threshold,
        "median_province_branch_count": median,
    }


def crawler_vs_network(
    branch_audit: dict[str, Any],
    crawl_stats: dict[str, float] | None,
) -> dict[str, Any]:
    discovered_tasks = int((crawl_stats or {}).get("branches_discovered") or 0)
    unique = branch_audit["total_unique_branches"]
    official = OFFICIAL_BRANCH_ESTIMATE
    network_coverage = round(unique / official, 4) if official else None
    crawler_completion = None
    if discovered_tasks:
        # From prior coverage report semantics: succeeded tasks / discovered
        crawler_completion = 1.0  # validated separately if crawl report present

    return {
        "crawler_completion": {
            "definition": (
                "Share of discovered Google Maps crawl tasks that finished successfully "
                "in the Tipax Iran run (task queue completion). Not official network share."
            ),
            "branches_discovered_tasks": discovered_tasks,
            "unique_branches_stored": unique,
            "note": (
                f"{unique} unique DB rows after place_id dedupe from "
                f"{discovered_tasks or 'N/A'} discovery tasks."
            ),
        },
        "network_coverage": {
            "definition": (
                "Estimated share of Tipax's official agency/contact-point network "
                "represented in Google Maps discoveries."
            ),
            "official_branch_estimate": official,
            "official_source": OFFICIAL_BRANCH_SOURCE,
            "discovered_unique_branches": unique,
            "estimated_network_coverage": network_coverage,
            "estimated_network_coverage_pct": round(100 * network_coverage, 1)
            if network_coverage is not None
            else None,
        },
    }


def score_quality(
    branches: list[sqlite3.Row],
    reviews: list[sqlite3.Row],
    branch_audit: dict[str, Any],
    review_audit: dict[str, Any],
    geo: dict[str, Any],
) -> QualityScores:
    n_b = max(len(branches), 1)
    n_r = max(len(reviews), 1)

    # Completeness: metadata + review presence
    with_coords = n_b - branch_audit["branches_missing_coordinates"]
    with_phone = n_b - branch_audit["branches_missing_phone"]
    with_url = n_b - branch_audit["branches_missing_maps_url"]
    with_reviews = n_b - branch_audit["branches_with_zero_reviews"]
    completeness = 100 * (
        0.25 * (with_coords / n_b)
        + 0.20 * (with_phone / n_b)
        + 0.20 * (with_url / n_b)
        + 0.20 * (with_reviews / n_b)
        + 0.15 * (geo["known_provinces_hit"] / max(geo["known_provinces_total"], 1))
    )

    # Consistency: claimed vs collected, language, ratings
    suspicious_rate = branch_audit["branches_with_suspicious_review_counts"] / n_b
    lang_err = review_audit["language_detection_errors"] / n_r
    bad_rating = review_audit["impossible_ratings"] / n_r
    consistency = 100 * (1.0 - min(1.0, 0.5 * suspicious_rate + 0.3 * lang_err + 0.2 * bad_rating))

    # Uniqueness
    dup_b = branch_audit["duplicate_branch_extra_rows"] / n_b
    dup_r = review_audit["duplicate_reviews_extra"] / n_r
    # Same-name different place is not always bad (chains), mild penalty
    name_dup = min(1.0, branch_audit["same_name_different_place_groups"] / n_b)
    uniqueness = 100 * (1.0 - min(1.0, 0.6 * dup_b + 0.3 * dup_r + 0.1 * name_dup))

    # Accuracy: network coverage proxy + geo match + owner replies gap as soft signal
    network = min(1.0, branch_audit["total_unique_branches"] / OFFICIAL_BRANCH_ESTIMATE)
    geo_acc = geo["known_provinces_hit"] / max(geo["known_provinces_total"], 1)
    # Heavy under-collection vs claimed counts hurts accuracy
    accuracy = 100 * (0.45 * network + 0.35 * geo_acc + 0.20 * (1.0 - suspicious_rate))

    # Freshness: based on collected_at / last_success_at recency
    now = datetime.now(timezone.utc)
    ages = []
    for b in branches:
        stamp = b["last_success_at"] or b["collected_at"] or ""
        try:
            ts = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            ages.append((now - ts.astimezone(timezone.utc)).total_seconds() / 86400.0)
        except Exception:
            continue
    if ages:
        median_age = sorted(ages)[len(ages) // 2]
        # Full score if <= 2 days, decays to 40 by 30 days
        freshness = max(40.0, min(100.0, 100.0 - max(0.0, median_age - 2) * 2.2))
    else:
        freshness = 50.0

    return QualityScores(
        completeness=round(completeness, 1),
        consistency=round(consistency, 1),
        uniqueness=round(uniqueness, 1),
        accuracy=round(accuracy, 1),
        freshness=round(freshness, 1),
    )


def top_branches_by_reviews(
    branches: list[sqlite3.Row], reviews: list[sqlite3.Row], limit: int = 50
) -> list[dict[str, Any]]:
    counts = Counter(int(r["branch_id"]) for r in reviews)
    by_id = {int(b["id"]): b for b in branches}
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]
    out = []
    for rank, (bid, n) in enumerate(ranked, start=1):
        b = by_id.get(bid)
        if not b:
            continue
        out.append(
            {
                "rank": rank,
                "branch_id": bid,
                "name": b["name"],
                "city": b["city"] or "",
                "province": b["province"] or "",
                "collected_reviews": n,
                "claimed_review_count": int(b["review_count"] or 0),
                "google_rating": b["rating"],
                "maps_url": b["maps_url"] or "",
                "phone": b["phone"] or "",
            }
        )
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_crawl_stats(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT metric, SUM(value) AS v
        FROM crawl_stats
        WHERE run_id = (
            SELECT id FROM crawl_runs
            WHERE company_name = 'Tipax' AND status = 'succeeded'
            ORDER BY id ASC LIMIT 1
        )
        GROUP BY metric
        """
    ).fetchall()
    return {r["metric"]: float(r["v"]) for r in rows}


def render_markdown(report: dict[str, Any]) -> str:
    q = report["quality_scores"]
    net = report["crawler_vs_network"]
    b = report["branch_audit"]
    r = report["review_audit"]
    g = report["geography"]
    lines = [
        "# Tipax Data Quality Report (Phase 9)",
        "",
        f"Generated: `{report['generated_at']}`  ",
        f"Database: `{report['db_path']}`  ",
        "",
        "## 1. Executive summary",
        "",
        f"- Unique Tipax branches in DB: **{b['total_unique_branches']}**",
        f"- Reviews stored: **{r['total_reviews']}**",
        f"- Data Quality Score: **{q['overall']}/100**",
        (
            f"- Crawler completion (Maps task queue): **{report['crawler_completion_pct']}%** "
            "(discovered tasks finished)"
        ),
        (
            f"- Estimated network coverage vs official Tipax footprint: "
            f"**{net['network_coverage']['estimated_network_coverage_pct']}%** "
            f"({b['total_unique_branches']} / {net['network_coverage']['official_branch_estimate']})"
        ),
        "",
        "### Crawler Completion vs Network Coverage",
        "",
        "| Concept | Meaning | Value |",
        "|---------|---------|------:|",
        (
            "| **Crawler Completion** | Google Maps crawl tasks succeeded / discovered "
            f"| {report['crawler_completion_pct']}% |"
        ),
        (
            "| **Network Coverage** | Unique Maps branches / official Tipax agencies estimate "
            f"| {net['network_coverage']['estimated_network_coverage_pct']}% |"
        ),
        "",
        f"Official estimate source: {net['network_coverage']['official_source']}",
        "",
        "## 2. Data quality score",
        "",
        "| Dimension | Score |",
        "|-----------|------:|",
        f"| Completeness | {q['completeness']} |",
        f"| Consistency | {q['consistency']} |",
        f"| Uniqueness | {q['uniqueness']} |",
        f"| Accuracy | {q['accuracy']} |",
        f"| Freshness | {q['freshness']} |",
        f"| **Overall** | **{q['overall']}** |",
        "",
        "Weights: completeness 25%, consistency 20%, uniqueness 20%, accuracy 25%, freshness 10%.",
        "",
        "## 3. Branch audit",
        "",
        f"- Total unique branches: **{b['total_unique_branches']}**",
        f"- Duplicate extra rows (same place_id/name+address): **{b['duplicate_branch_extra_rows']}**",
        f"- Same-name different place_id groups: **{b['same_name_different_place_groups']}**",
        f"- Missing coordinates: **{b['branches_missing_coordinates']}**",
        f"- Missing phone: **{b['branches_missing_phone']}**",
        f"- Missing Google Maps URL: **{b['branches_missing_maps_url']}**",
        f"- Zero collected reviews: **{b['branches_with_zero_reviews']}**",
        f"- Suspicious review counts: **{b['branches_with_suspicious_review_counts']}**",
        "",
        "## 4. Review quality",
        "",
        f"- Total reviews: **{r['total_reviews']}**",
        f"- Duplicate extras (content): **{r['duplicate_reviews_extra']}**",
        f"- Empty reviews: **{r['empty_reviews']}**",
        f"- Malformed reviews: **{r['malformed_reviews']}**",
        f"- Language detection errors: **{r['language_detection_errors']}**",
        f"- Impossible ratings: **{r['impossible_ratings']}**",
        f"- Missing dates: **{r['missing_dates']}**",
        f"- Owner responses present: **{r['owner_responses_present']}**",
        "",
        "## 5. Geographic coverage",
        "",
        f"- Known provinces hit: **{g['known_provinces_hit']} / {g['known_provinces_total']}**",
        f"- Provinces with no branches: **{', '.join(g['provinces_with_no_branches']) or 'none'}**",
        f"- Unusually low provinces (≤ {g['low_threshold_used']} branches): "
        + (
            ", ".join(
                f"{x['province']} ({x['branches']})" for x in g["provinces_unusually_low"]
            )
            or "none"
        ),
        "",
        "## 6. Known issues",
        "",
    ]
    for issue in report["known_issues"]:
        lines.append(f"- {issue}")
    lines.extend(
        [
            "",
            "## 7. Recommended fixes",
            "",
        ]
    )
    for fix in report["recommended_fixes"]:
        lines.append(f"- {fix}")
    lines.extend(
        [
            "",
            "## 8. Readiness for next courier company",
            "",
            report["readiness"],
            "",
            "## 9. Top 50 branches by collected reviews",
            "",
            "| Rank | Branch | City | Province | Collected | Claimed | Rating |",
            "|-----:|--------|------|----------|----------:|--------:|-------:|",
        ]
    )
    for row in report["top50_branches"]:
        lines.append(
            f"| {row['rank']} | {row['name']} | {row['city']} | {row['province']} | "
            f"{row['collected_reviews']} | {row['claimed_review_count']} | {row['google_rating']} |"
        )
    lines.extend(
        [
            "",
            "## 10. Artifacts",
            "",
            "- `docs/data_quality_report.md` (this file)",
            "- `docs/branch_validation.csv`",
            "- `docs/province_summary.csv`",
            "- `docs/duplicate_report.csv`",
            "- `docs/top50_branches_by_reviews.csv`",
            "- `docs/manual_verification_queue.csv`",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 9 Tipax data quality audit")
    parser.add_argument("--db", default="data/tipax_iran.db")
    parser.add_argument("--out-dir", default="docs")
    parser.add_argument("--artifact-dir", default="/opt/cursor/artifacts/phase9_quality")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    artifact_dir = Path(args.artifact_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(args.db)
    try:
        _, branches, reviews = load_tipax(conn)
        crawl_stats = load_crawl_stats(conn)
        branch_audit = audit_branches(branches, reviews)
        review_audit = audit_reviews(reviews)
        geo = audit_geography(branches)
        coverage = crawler_vs_network(branch_audit, crawl_stats)
        scores = score_quality(branches, reviews, branch_audit, review_audit, geo)
        top50 = top_branches_by_reviews(branches, reviews, 50)

        # Crawler completion from first succeeded Tipax run tasks if available
        run = conn.execute(
            """
            SELECT id FROM crawl_runs
            WHERE company_name='Tipax' AND status='succeeded'
            ORDER BY id ASC LIMIT 1
            """
        ).fetchone()
        crawler_completion_pct = None
        if run:
            tasks = conn.execute(
                "SELECT status, COUNT(*) AS c FROM crawl_branch_tasks WHERE run_id=? GROUP BY status",
                (int(run["id"]),),
            ).fetchall()
            counts = {t["status"]: int(t["c"]) for t in tasks}
            total_tasks = sum(counts.values()) or 1
            crawler_completion_pct = round(100.0 * counts.get("succeeded", 0) / total_tasks, 1)

        known_issues = [
            (
                f"Network coverage is low vs official Tipax footprint: "
                f"{branch_audit['total_unique_branches']} Maps places vs "
                f"~{OFFICIAL_BRANCH_ESTIMATE} agencies "
                f"({coverage['network_coverage']['estimated_network_coverage_pct']}%)."
            ),
            (
                f"{branch_audit['branches_with_suspicious_review_counts']} branches show suspicious "
                f"claimed review_count patterns (often {SUSPICIOUS_REVIEW_COUNT} or large claimed vs "
                "few collected)."
            ),
            (
                f"{branch_audit['branches_missing_phone']} branches missing phone; "
                f"{branch_audit['branches_missing_coordinates']} missing coordinates."
            ),
            (
                f"{branch_audit['branches_with_zero_reviews']} branches have zero collected reviews "
                "(Maps review pane often blocked / limited)."
            ),
            (
                f"Owner responses present: {review_audit['owner_responses_present']} "
                "(extraction effectively empty in this dataset)."
            ),
            (
                f"Provinces with no matched branches: "
                f"{', '.join(geo['provinces_with_no_branches']) or 'none'}."
            ),
            (
                f"{branch_audit['same_name_different_place_groups']} same-name groups with different "
                "place_id values — may include true multi-location brands or weak identity keys."
            ),
        ]

        recommended_fixes = [
            "Treat Crawler Completion and Network Coverage as separate KPIs in all future reports.",
            "Improve Maps review scrolling / residential sessions to raise reviews per branch and owner replies.",
            "Fix review_count parsing that collapses to the 320 artifact; prefer place-pane counts only.",
            "Normalize province/city labels (FA/EN) into a controlled taxonomy after crawl (no schema change required for reporting).",
            "Add a post-crawl dedupe report for same-name multi place_id clusters before analytics.",
            "Build an official Tipax branch list scraper/compare job (read-only) to measure true network coverage.",
            "Prioritize manual verification queue for missing phone/coords and zero-review high-claim branches.",
        ]

        readiness = (
            f"Readiness for the next courier company: **CONDITIONAL GO**. "
            f"Pipeline/ops completion is strong (crawler completion "
            f"{crawler_completion_pct}% on Tipax Maps tasks; DQ overall {scores.overall}/100), "
            "but Google Maps discovery currently captures only a minority of Tipax's official "
            f"network (~{coverage['network_coverage']['estimated_network_coverage_pct']}%). "
            "Safe to run the same collector for the next courier **for Maps-visible locations**, "
            "while tracking Network Coverage separately and not equating it to Crawler Completion. "
            "Block treating analytics as full-network truth until coverage improves or an official "
            "directory compare exists."
        )

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "db_path": args.db,
            "branch_audit": {
                k: v
                for k, v in branch_audit.items()
                if k
                not in {
                    "validation_rows",
                    "manual_verify_candidates",
                    "duplicate_groups_detail",
                    "name_dup_groups_detail",
                    "suspicious_detail",
                }
            },
            "review_audit": {
                k: v
                for k, v in review_audit.items()
                if k not in {"language_error_samples", "duplicate_content_samples"}
            },
            "geography": {
                k: v
                for k, v in geo.items()
                if k not in {"province_rows", "branches_per_city"}
            },
            "crawler_vs_network": coverage,
            "crawler_completion_pct": crawler_completion_pct,
            "quality_scores": {
                "completeness": scores.completeness,
                "consistency": scores.consistency,
                "uniqueness": scores.uniqueness,
                "accuracy": scores.accuracy,
                "freshness": scores.freshness,
                "overall": scores.overall,
            },
            "known_issues": known_issues,
            "recommended_fixes": recommended_fixes,
            "readiness": readiness,
            "top50_branches": top50,
            "manual_verify_count": len(branch_audit["manual_verify_candidates"]),
        }

        # CSVs
        write_csv(out_dir / "branch_validation.csv", branch_audit["validation_rows"])
        write_csv(out_dir / "province_summary.csv", geo["province_rows"])
        dup_rows = []
        for gdetail in branch_audit["duplicate_groups_detail"]:
            dup_rows.append(
                {
                    "type": "exact_place_or_nameaddr",
                    "key": gdetail["key"],
                    "count": gdetail["count"],
                    "branch_ids": ",".join(map(str, gdetail["ids"])),
                    "names": " | ".join(gdetail["names"]),
                }
            )
        for gdetail in branch_audit["name_dup_groups_detail"]:
            dup_rows.append(
                {
                    "type": "same_name_different_place",
                    "key": gdetail["name"],
                    "count": gdetail["count"],
                    "branch_ids": ",".join(map(str, gdetail["ids"])),
                    "names": gdetail["name"],
                }
            )
        for sample in review_audit["duplicate_content_samples"]:
            dup_rows.append(
                {
                    "type": "duplicate_review_content",
                    "key": sample["key"],
                    "count": sample["count"],
                    "branch_ids": "",
                    "names": f"review_ids={sample['review_ids']}",
                }
            )
        write_csv(
            out_dir / "duplicate_report.csv",
            dup_rows,
            fieldnames=["type", "key", "count", "branch_ids", "names"],
        )
        write_csv(out_dir / "top50_branches_by_reviews.csv", top50)
        write_csv(
            out_dir / "manual_verification_queue.csv",
            branch_audit["manual_verify_candidates"],
        )

        md = render_markdown(report)
        (out_dir / "data_quality_report.md").write_text(md, encoding="utf-8")

        # Artifacts copy
        for name in [
            "data_quality_report.md",
            "branch_validation.csv",
            "province_summary.csv",
            "duplicate_report.csv",
            "top50_branches_by_reviews.csv",
            "manual_verification_queue.csv",
        ]:
            src = out_dir / name
            if src.exists():
                (artifact_dir / name).write_bytes(src.read_bytes())

        (artifact_dir / "data_quality_summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "data_quality_summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(
            json.dumps(
                {
                    "overall_score": scores.overall,
                    "unique_branches": branch_audit["total_unique_branches"],
                    "reviews": review_audit["total_reviews"],
                    "crawler_completion_pct": crawler_completion_pct,
                    "network_coverage_pct": coverage["network_coverage"][
                        "estimated_network_coverage_pct"
                    ],
                    "manual_verify": len(branch_audit["manual_verify_candidates"]),
                    "out_dir": str(out_dir),
                    "artifact_dir": str(artifact_dir),
                },
                indent=2,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
