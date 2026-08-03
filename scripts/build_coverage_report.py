#!/usr/bin/env python3
"""Build DATA_COVERAGE_REPORT.md from Maps DBs + official website harvest.

Does not change postal_score_v1.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.iran_geo import IRAN_PROVINCES
from collectors.official.website_harvester import harvest_all
from postal.metric_confidence import metric_confidence_bundle
from postal.official import name_to_slug

CANON_PROVINCES = {p["en"].casefold(): p["en"] for p in IRAN_PROVINCES}
CANON_PROVINCES.update({p["fa"]: p["en"] for p in IRAN_PROVINCES})

COMPANIES = ["tipax", "chapar", "post", "mahex", "alopeyk", "pishro"]


def normalize_province(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    # strip trailing "Province"
    text2 = re.sub(r"\s+Province$", "", text, flags=re.I).strip()
    key = text2.casefold()
    if key in CANON_PROVINCES:
        return CANON_PROVINCES[key]
    # common aliases
    aliases = {
        "tehran": "Tehran",
        "تهران": "Tehran",
        "alborz": "Alborz",
        "البرز": "Alborz",
        "isfahan": "Isfahan",
        "esfahan": "Isfahan",
        "اصفهان": "Isfahan",
        "razavi khorasan": "Razavi Khorasan",
        "khorasan razavi": "Razavi Khorasan",
        "خراسان رضوی": "Razavi Khorasan",
    }
    if key in aliases:
        return aliases[key]
    if text2 in aliases:
        return aliases[text2]
    return text2


def open_db(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def collect_from_db(conn: sqlite3.Connection, label: str) -> dict[str, dict]:
    """Return slug -> {branches:[{}], reviews:n}."""
    out: dict[str, dict] = defaultdict(lambda: {"branches": [], "reviews": 0, "sources": set()})
    if not table_exists(conn, "companies") or not table_exists(conn, "branches"):
        return {}
    companies = {int(r["id"]): dict(r) for r in conn.execute("SELECT * FROM companies")}
    for b in conn.execute("SELECT * FROM branches"):
        b = dict(b)
        company = companies.get(int(b["company_id"]))
        if not company:
            continue
        slug = name_to_slug(str(company.get("name") or ""))
        if not slug:
            continue
        out[slug]["branches"].append(
            {
                "name": b.get("name") or "",
                "address": b.get("address") or "",
                "city": (b.get("city") or "").strip(),
                "province": normalize_province(b.get("province") or ""),
                "place_id": b.get("place_id") or "",
                "rating": float(b.get("rating") or 0),
                "review_count": int(b.get("review_count") or 0),
            }
        )
        out[slug]["sources"].add(label)
    if table_exists(conn, "reviews"):
        for row in conn.execute(
            """
            SELECT c.name AS company_name, COUNT(r.id) AS n
            FROM reviews r
            JOIN branches b ON b.id=r.branch_id
            JOIN companies c ON c.id=b.company_id
            GROUP BY c.name
            """
        ):
            slug = name_to_slug(str(row["company_name"] or ""))
            if slug:
                out[slug]["reviews"] += int(row["n"] or 0)
                out[slug]["sources"].add(label)
    return out


def merge_branch_sets(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    merged = []
    for b in items:
        key = (b.get("place_id") or "").strip() or f"{b['name'].casefold()}|{b['address'].casefold()}"
        if key in seen:
            continue
        seen.add(key)
        merged.append(b)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harvest", action="store_true", help="Re-run official website harvest")
    parser.add_argument("--out", default="DATA_COVERAGE_REPORT.md")
    args = parser.parse_args()

    if args.harvest or not (ROOT / "data/official_harvest/harvest_summary.json").exists():
        harvest_summary = harvest_all(ROOT / "data/official_harvest")
    else:
        harvest_summary = json.loads(
            (ROOT / "data/official_harvest/harvest_summary.json").read_text(encoding="utf-8")
        )

    source_paths = [
        ROOT / "data/tipax_iran.db",
        ROOT / "data/phase11_multisource.db",
        ROOT / "data/analytics_demo.db",
    ]
    # Expanded Maps coverage DBs (avoid double-counting postal_intelligence which is a rebuild)
    source_paths.extend(sorted((ROOT / "data/coverage_expand").glob("*_coverage.db")))

    per_slug_branches: dict[str, list[dict]] = defaultdict(list)
    per_slug_reviews: dict[str, int] = defaultdict(int)
    per_slug_sources: dict[str, set[str]] = defaultdict(set)

    for path in source_paths:
        conn = open_db(path)
        if not conn:
            continue
        chunk = collect_from_db(conn, path.name)
        conn.close()
        for slug, data in chunk.items():
            # analytics_demo overlaps tipax_iran — skip tipax rows from demo to avoid double count
            if path.name == "analytics_demo.db" and slug == "tipax":
                continue
            per_slug_branches[slug].extend(data["branches"])
            per_slug_reviews[slug] += int(data["reviews"])
            per_slug_sources[slug].update(data["sources"])

    # Load official profiles
    official_profiles = {}
    for slug in COMPANIES:
        p = ROOT / "data/official_harvest" / f"{slug}_official_profile.json"
        if p.exists():
            official_profiles[slug] = json.loads(p.read_text(encoding="utf-8"))

    rows = []
    for slug in COMPANIES:
        branches = merge_branch_sets(per_slug_branches.get(slug, []))
        cities = sorted({b["city"] for b in branches if b.get("city")})
        provinces = sorted({b["province"] for b in branches if b.get("province")})
        # keep only canonical-ish provinces when possible
        provinces_canon = [p for p in provinces if p in {x["en"] for x in IRAN_PROVINCES}]
        if not provinces_canon:
            provinces_canon = provinces
        reviews = per_slug_reviews.get(slug, 0)
        official = official_profiles.get(slug) or {
            "reachable": False,
            "completeness_ratio": 0.0,
            "missing_official_information": [
                "branches",
                "services",
                "coverage",
                "official_delivery_times",
                "official_pricing",
                "weight_limits",
                "size_limits",
                "insurance",
                "tracking",
                "working_hours",
                "customer_support",
            ],
        }
        conf = metric_confidence_bundle(
            review_count=reviews,
            branch_count=len(branches),
            city_count=len(cities),
            province_count=len(provinces_canon),
            official_completeness_ratio=float(official.get("completeness_ratio") or 0),
            official_reachable=bool(official.get("reachable")),
        )
        rows.append(
            {
                "slug": slug,
                "name": slug.title() if slug != "alopeyk" else "AloPeyk",
                "branches": len(branches),
                "cities": len(cities),
                "provinces": len(provinces_canon),
                "province_list": provinces_canon,
                "city_list": cities,
                "reviews": reviews,
                "province_coverage_pct": conf["metrics"]["provinces"]["coverage_pct"],
                "city_coverage_pct": conf["metrics"]["cities"]["coverage_pct"],
                "branch_coverage_vs_target_pct": conf["metrics"]["branches"]["coverage_vs_target_pct"],
                "sources": sorted(per_slug_sources.get(slug, [])),
                "official_missing": official.get("missing_official_information") or [],
                "official_completeness_ratio": official.get("completeness_ratio") or 0,
                "official_reachable": official.get("reachable"),
                "official_services": (official.get("services") or {}).get("value")
                if isinstance(official.get("services"), dict)
                else [],
                "confidence": conf,
            }
        )

    totals = {
        "branches": sum(r["branches"] for r in rows),
        "reviews": sum(r["reviews"] for r in rows),
        "companies": len(rows),
        "avg_overall_confidence": round(
            sum(r["confidence"]["overall_dataset_confidence"] for r in rows) / max(len(rows), 1), 3
        ),
    }

    # Markdown report
    lines = []
    lines.append("# DATA_COVERAGE_REPORT")
    lines.append("")
    lines.append("**Goal:** improve dataset coverage and confidence first; `postal_score_v1` unchanged.")
    lines.append("")
    lines.append(f"**Generated from:** Maps warehouses + `data/coverage_expand/*` + official website harvest.")
    lines.append("")
    lines.append("## Executive totals")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|------:|")
    lines.append(f"| Companies | {totals['companies']} |")
    lines.append(f"| Branches (deduped) | {totals['branches']} |")
    lines.append(f"| Reviews | {totals['reviews']} |")
    lines.append(f"| Avg overall dataset confidence | {totals['avg_overall_confidence']} |")
    lines.append("")
    lines.append("Targets used for confidence: reviews≥100 full, branches≥200, cities≥100, provinces≥31.")
    lines.append("Statistical minimum for review metrics: **n≥30** (strong: n≥100).")
    lines.append("")
    lines.append("## Per-company coverage")
    lines.append("")
    lines.append(
        "| Company | Branches | Cities | Provinces | Reviews | Prov coverage % | Official completeness | Overall dataset confidence | Stats-ready (reviews≥30) |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|:---:|")
    for r in rows:
        ready = "yes" if r["confidence"]["metrics"]["reviews"]["sufficient_for_stats"] else "no"
        lines.append(
            f"| {r['name']} | {r['branches']} | {r['cities']} | {r['provinces']} | {r['reviews']} | "
            f"{r['province_coverage_pct']} | {r['official_completeness_ratio']} | "
            f"{r['confidence']['overall_dataset_confidence']} | {ready} |"
        )
    lines.append("")

    lines.append("## Number of branches / cities / provinces / reviews")
    lines.append("")
    for r in rows:
        lines.append(f"### {r['name']}")
        lines.append("")
        lines.append(f"- Branches covered: **{r['branches']}**")
        lines.append(f"- Cities: **{r['cities']}**")
        lines.append(f"- Provinces: **{r['provinces']}** ({r['province_coverage_pct']}% of 31)")
        lines.append(f"- Reviews: **{r['reviews']}**")
        lines.append(
            f"- Coverage vs branch target (200): **{r['branch_coverage_vs_target_pct']}%**"
        )
        lines.append(f"- Sources: {', '.join(r['sources']) or 'none'}")
        lines.append("")
        lines.append("Metric confidence:")
        lines.append("")
        lines.append("| Metric | Value | Confidence |")
        lines.append("|--------|------:|-----------:|")
        for key, meta in r["confidence"]["metrics"].items():
            val = meta.get("value", meta.get("completeness_ratio", ""))
            lines.append(f"| {key} | {val} | {meta['confidence']} |")
        lines.append(f"| overall | — | {r['confidence']['overall_dataset_confidence']} |")
        lines.append("")

    lines.append("## Missing official information (website harvest)")
    lines.append("")
    lines.append("Harvested from official domains only (`tipaxco.com`, `chaparnet.com`, `mahex.com`, `alopeyk.com`, `pishro.net`, `post.ir`).")
    lines.append("")
    for r in rows:
        off = official_profiles.get(r["slug"], {})
        lines.append(f"### {r['name']}")
        lines.append("")
        if not r["official_reachable"]:
            lines.append(f"- Site reachable: **no** ({(off.get('page_errors') or {})})")
        else:
            lines.append(f"- Site reachable: **yes** ({off.get('pages_ok', 0)} pages OK)")
        lines.append(f"- Completeness ratio: **{r['official_completeness_ratio']}**")
        missing = r["official_missing"] or []
        if missing:
            lines.append(f"- Missing / not extractable from static HTML: {', '.join(missing)}")
        else:
            lines.append("- Missing: none of the tracked topics")
        services = r.get("official_services") or []
        if services:
            lines.append(f"- Services evidenced on site: {', '.join(services)}")
        support = ((off.get("customer_support") or {}).get("value") or {})
        if support.get("phone") or support.get("email"):
            lines.append(
                f"- Support channels found: phones={support.get('phone')} emails={support.get('email')}"
            )
        lines.append("")

    lines.append("## Coverage percentage summary")
    lines.append("")
    lines.append("| Company | Province coverage % | City coverage % (vs target 100) | Branch coverage % (vs target 200) | Review confidence |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['province_coverage_pct']} | {r['city_coverage_pct']} | "
            f"{r['branch_coverage_vs_target_pct']} | {r['confidence']['metrics']['reviews']['confidence']} |"
        )
    lines.append("")

    lines.append("## Confidence improvement opportunities")
    lines.append("")
    lines.append("1. **Pishro:** zero/low Maps evidence and `pishro.net` currently returns maintenance page — need live site or alternate official domain + Maps discovery under additional query variants.")
    lines.append("2. **Post:** `post.ir` connection resets from this environment — retry via alternate hosts/CDN or mirrored official pages; expand Maps queries across all 31 provinces.")
    lines.append("3. **Fixed public tariffs / weight / size limits:** official sites mostly expose calculators, not static tables — capture calculator API responses only if officially documented, or store “calculator_only” with low confidence.")
    lines.append("4. **Raise every company to n≥100 reviews** for strong statistical confidence on satisfaction/complaint metrics.")
    lines.append("5. **Normalize province/city fields** during ingest (already applied in this report) to avoid inflated province counts.")
    lines.append("6. **Branch locator JS apps** (Tipax/Chapar/Mahex agencies pages) need browser rendering to extract full official branch lists.")
    lines.append("7. **Do not change `postal_score_v1` until** review n≥30 for all companies and official completeness ≥0.5 for reachable sites.")
    lines.append("")
    lines.append("## postal_score_v1 status")
    lines.append("")
    lines.append("**Unchanged.** This report and metric confidence layer are dataset quality instruments only.")
    lines.append("")

    report = "\n".join(lines)
    Path(args.out).write_text(report, encoding="utf-8")
    (ROOT / "docs/postal_intelligence/DATA_COVERAGE_REPORT.md").parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/postal_intelligence/DATA_COVERAGE_REPORT.md").write_text(report, encoding="utf-8")

    payload = {"totals": totals, "companies": rows, "harvest_summary": harvest_summary}
    (ROOT / "output/coverage/coverage_snapshot.json").parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "output/coverage/coverage_snapshot.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "docs/postal_intelligence/coverage_snapshot.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(report[:2500])
    print("\n... report written to", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
