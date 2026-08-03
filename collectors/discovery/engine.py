"""Nationwide multi-level branch discovery engine (coverage-first)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collectors.dedupe import branch_identity_key
from collectors.iran_geo import (
    IRAN_PROVINCES,
    PROVINCE_CITIES,
    DiscoveryQuery,
    build_discovery_queries,
    district_expansion_queries,
)
from core.logging_setup import get_logger
from models.branch import Branch

log = get_logger("discovery")

# Expand to districts when a city-level search yields at least this many cards.
CITY_RESULT_EXPAND_THRESHOLD = 8


@dataclass
class QueryOutcome:
    query: str
    level: str
    province_en: str
    province_fa: str
    city_fa: str
    district_fa: str
    alias: str
    raw_results: int = 0
    new_unique: int = 0
    duplicate_hits: int = 0
    error: str | None = None


@dataclass
class ProvinceCoverage:
    province_en: str
    province_fa: str
    cities_searched: list[str] = field(default_factory=list)
    queries_executed: int = 0
    branches_discovered: int = 0  # unique place keys attributed to this province
    raw_result_hits: int = 0
    duplicate_hits: int = 0
    review_count: int = 0  # sum of Maps review_count on unique branches
    query_outcomes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duplicate_rate(self) -> float:
        denom = self.raw_result_hits
        if denom <= 0:
            return 0.0
        return round(self.duplicate_hits / denom, 4)


@dataclass
class DiscoveryRunResult:
    generated_at: str
    company: str
    queries_planned: int
    queries_executed: int
    unique_branches: int
    new_branches_vs_baseline: int
    baseline_unique: int
    district_expansions: int
    provinces: list[ProvinceCoverage] = field(default_factory=list)
    zero_provinces: list[str] = field(default_factory=list)
    query_outcomes: list[QueryOutcome] = field(default_factory=list)
    branches: list[Branch] = field(default_factory=list)

    def to_report_dict(self) -> dict[str, Any]:
        provinces = []
        for p in self.provinces:
            provinces.append(
                {
                    "province_en": p.province_en,
                    "province_fa": p.province_fa,
                    "cities_searched": sorted(set(p.cities_searched)),
                    "queries_executed": p.queries_executed,
                    "branches_discovered": p.branches_discovered,
                    "raw_result_hits": p.raw_result_hits,
                    "duplicate_hits": p.duplicate_hits,
                    "duplicate_rate": p.duplicate_rate,
                    "review_count": p.review_count,
                }
            )
        return {
            "generated_at": self.generated_at,
            "company": self.company,
            "queries_planned": self.queries_planned,
            "queries_executed": self.queries_executed,
            "unique_branches": self.unique_branches,
            "baseline_unique": self.baseline_unique,
            "new_branches_vs_baseline": self.new_branches_vs_baseline,
            "district_expansions": self.district_expansions,
            "provinces_targeted": len(IRAN_PROVINCES),
            "provinces_with_branches": sum(1 for p in self.provinces if p.branches_discovered > 0),
            "zero_provinces": self.zero_provinces,
            "provinces": provinces,
            "query_outcomes": [asdict(q) for q in self.query_outcomes],
        }


class NationwideDiscoveryEngine:
    """
    Adaptive multi-level Maps discovery.

    Does not collect reviews — only discovers and dedupes branches.
    """

    def __init__(
        self,
        source: Any,
        *,
        company_name: str = "Tipax",
        city_expand_threshold: int = CITY_RESULT_EXPAND_THRESHOLD,
        include_preseed_districts: bool = False,
        max_queries: int | None = None,
        gap_provinces: set[str] | None = None,
    ):
        self.source = source
        self.company_name = company_name
        self.city_expand_threshold = city_expand_threshold
        self.include_preseed_districts = include_preseed_districts
        self.max_queries = max_queries
        self.gap_provinces = gap_provinces or {"Ardabil", "Kermanshah"}

    def plan_queries(self) -> list[DiscoveryQuery]:
        return build_discovery_queries(
            include_districts=self.include_preseed_districts,
            include_gap_probes=True,
            gap_provinces=self.gap_provinces,
        )

    async def run(
        self,
        *,
        baseline_keys: set[str] | None = None,
    ) -> DiscoveryRunResult:
        planned = self.plan_queries()
        queue: list[DiscoveryQuery] = list(planned)
        executed_texts: set[str] = set()
        outcomes: list[QueryOutcome] = []
        merged: list[Branch] = []
        seen: set[str] = set()
        baseline = set(baseline_keys or ())
        district_expansions = 0

        # province_en -> coverage
        coverage: dict[str, ProvinceCoverage] = {
            p["en"]: ProvinceCoverage(province_en=p["en"], province_fa=p["fa"])
            for p in IRAN_PROVINCES
        }
        # Track which unique keys belong to which province (first attribution wins).
        branch_province: dict[str, str] = {}
        branch_reviews: dict[str, int] = {}

        # Ensure source can discover.
        if hasattr(self.source, "_ensure_started"):
            await self.source._ensure_started()

        queries_executed = 0
        while queue:
            if self.max_queries is not None and queries_executed >= self.max_queries:
                log.info("discovery_max_queries_reached max=%s", self.max_queries)
                break

            spec = queue.pop(0)
            text_key = spec.text.casefold().strip()
            if text_key in executed_texts:
                continue
            executed_texts.add(text_key)
            queries_executed += 1

            outcome = QueryOutcome(
                query=spec.text,
                level=spec.level,
                province_en=spec.province_en,
                province_fa=spec.province_fa,
                city_fa=spec.city_fa,
                district_fa=spec.district_fa,
                alias=spec.alias,
            )

            try:
                found = await self._search_once(spec)
            except Exception as exc:  # noqa: BLE001
                outcome.error = str(exc)
                log.warning("discovery_query_failed query=%s error=%s", spec.text, exc)
                outcomes.append(outcome)
                if spec.province_en and spec.province_en in coverage:
                    coverage[spec.province_en].queries_executed += 1
                    coverage[spec.province_en].query_outcomes.append(asdict(outcome))
                continue

            outcome.raw_results = len(found)
            new_here = 0
            dup_here = 0
            for branch in found:
                self._stamp_geo(branch, spec)
                key = branch_identity_key(
                    place_id=branch.place_id,
                    name=branch.name,
                    address=branch.address,
                )
                if key in seen:
                    dup_here += 1
                    continue
                seen.add(key)
                merged.append(branch)
                new_here += 1
                branch_reviews[key] = int(branch.review_count or 0)
                if spec.province_en:
                    branch_province[key] = spec.province_en

            outcome.new_unique = new_here
            outcome.duplicate_hits = dup_here
            outcomes.append(outcome)

            if spec.province_en and spec.province_en in coverage:
                cov = coverage[spec.province_en]
                cov.queries_executed += 1
                cov.raw_result_hits += outcome.raw_results
                cov.duplicate_hits += dup_here
                if spec.city_fa:
                    cov.cities_searched.append(spec.city_fa)
                cov.query_outcomes.append(asdict(outcome))

            # Adaptive district expansion for busy cities.
            if (
                spec.level in {"city", "gap_probe"}
                and spec.city_fa
                and spec.province_en
                and outcome.raw_results >= self.city_expand_threshold
            ):
                cities = PROVINCE_CITIES.get(spec.province_en, [])
                city_meta = next((c for c in cities if c.fa == spec.city_fa), None)
                if city_meta and city_meta.districts:
                    extras = district_expansion_queries(
                        province_fa=spec.province_fa,
                        province_en=spec.province_en,
                        city_fa=spec.city_fa,
                        city_en=spec.city_en or city_meta.en,
                        districts=city_meta.districts,
                    )
                    added = 0
                    for extra in extras:
                        if extra.text.casefold() not in executed_texts:
                            queue.append(extra)
                            added += 1
                    if added:
                        district_expansions += 1
                        log.info(
                            "discovery_district_expand city=%s results=%s added_queries=%s",
                            spec.city_fa,
                            outcome.raw_results,
                            added,
                        )

            log.info(
                "discovery_query_done query=%s level=%s raw=%s new=%s dups=%s total_unique=%s",
                spec.text,
                spec.level,
                outcome.raw_results,
                outcome.new_unique,
                outcome.duplicate_hits,
                len(merged),
            )

        # Finalize province unique counts + review sums from attributed branches.
        for key, province_en in branch_province.items():
            if province_en not in coverage:
                continue
            coverage[province_en].branches_discovered += 1
            coverage[province_en].review_count += branch_reviews.get(key, 0)

        # Also attribute unscoped branches via address/name province needles.
        for branch in merged:
            key = branch_identity_key(
                place_id=branch.place_id,
                name=branch.name,
                address=branch.address,
            )
            if key in branch_province:
                continue
            inferred = self._infer_province(branch)
            if not inferred:
                continue
            branch_province[key] = inferred
            coverage[inferred].branches_discovered += 1
            coverage[inferred].review_count += int(branch.review_count or 0)
            if not branch.province:
                branch.province = next(
                    (p["fa"] for p in IRAN_PROVINCES if p["en"] == inferred), ""
                )

        provinces = [coverage[p["en"]] for p in IRAN_PROVINCES]
        zero = [p.province_en for p in provinces if p.branches_discovered == 0]
        new_vs_baseline = sum(
            1
            for b in merged
            if branch_identity_key(place_id=b.place_id, name=b.name, address=b.address)
            not in baseline
        )

        return DiscoveryRunResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            company=self.company_name,
            queries_planned=len(planned),
            queries_executed=queries_executed,
            unique_branches=len(merged),
            new_branches_vs_baseline=new_vs_baseline,
            baseline_unique=len(baseline),
            district_expansions=district_expansions,
            provinces=provinces,
            zero_provinces=zero,
            query_outcomes=outcomes,
            branches=merged,
        )

    async def _search_once(self, spec: DiscoveryQuery) -> list[Branch]:
        """Run one Maps search via the production source collector."""
        collector = getattr(self.source, "_collector", None)
        if collector is None:
            # Fallback: single-query discover on a temporary query list.
            self.source._search_queries = [spec.text]
            return await self.source.discover_branches(self.company_name)

        await collector.search(spec.text)
        return await collector.collect_branches(company_name=self.company_name)

    @staticmethod
    def _stamp_geo(branch: Branch, spec: DiscoveryQuery) -> None:
        if spec.city_fa and not branch.city:
            branch.city = spec.city_fa
        if spec.province_fa and not branch.province:
            branch.province = spec.province_fa
        meta = dict(branch.metadata or {})
        meta["discovery_query"] = spec.text
        meta["discovery_level"] = spec.level
        if spec.district_fa:
            meta["discovery_district"] = spec.district_fa
        branch.metadata = meta

    @staticmethod
    def _infer_province(branch: Branch) -> str | None:
        blob = f"{branch.address} {branch.name} {branch.city} {branch.province}"
        for province in IRAN_PROVINCES:
            if province["fa"] in blob or province["en"].casefold() in blob.casefold():
                return province["en"]
        for province_en, cities in PROVINCE_CITIES.items():
            for city in cities:
                if city.fa and city.fa in blob:
                    return province_en
                if city.en and city.en.casefold() in blob.casefold():
                    return province_en
        return None


def write_discovery_reports(
    result: DiscoveryRunResult,
    *,
    out_dir: Path,
    zero_investigation: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Write coverage JSON/MD and optional zero-province investigation."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report = result.to_report_dict()
    if zero_investigation is not None:
        report["zero_province_investigation"] = zero_investigation

    json_path = out_dir / "discovery_coverage_report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Tipax Nationwide Discovery Coverage Report",
        "",
        f"Generated: `{result.generated_at}`",
        "",
        "## Summary",
        "",
        f"- Queries planned: **{result.queries_planned}**",
        f"- Queries executed: **{result.queries_executed}**",
        f"- Unique branches discovered: **{result.unique_branches}**",
        f"- Baseline unique (pre-run): **{result.baseline_unique}**",
        f"- New vs baseline: **{result.new_branches_vs_baseline}**",
        f"- District expansions triggered: **{result.district_expansions}**",
        f"- Provinces with branches: **{sum(1 for p in result.provinces if p.branches_discovered > 0)}/31**",
        f"- Zero-branch provinces: **{', '.join(result.zero_provinces) or 'none'}**",
        "",
        "## Per-province coverage",
        "",
        "| Province | Cities searched | Queries | Branches | Dup rate | Review count |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p in result.provinces:
        cities = len(set(p.cities_searched))
        md_lines.append(
            f"| {p.province_en} | {cities} | {p.queries_executed} | "
            f"{p.branches_discovered} | {p.duplicate_rate:.1%} | {p.review_count} |"
        )

    md_path = out_dir / "discovery_coverage_report.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    paths = {"json": json_path, "md": md_path}
    if zero_investigation is not None:
        zi_path = out_dir / "zero_province_investigation.md"
        zi_path.write_text(
            _format_zero_investigation_md(zero_investigation),
            encoding="utf-8",
        )
        paths["zero_md"] = zi_path
        zi_json = out_dir / "zero_province_investigation.json"
        zi_json.write_text(
            json.dumps(zero_investigation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths["zero_json"] = zi_json
    return paths


def _format_zero_investigation_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Zero-Province Discovery Investigation",
        "",
        f"Generated: `{payload.get('generated_at', '')}`",
        "",
        payload.get("summary", ""),
        "",
    ]
    for prov in payload.get("provinces", []):
        lines.extend(
            [
                f"## {prov.get('province_en')} ({prov.get('province_fa')})",
                "",
                f"- Queries executed: {prov.get('queries_executed')}",
                f"- Cities searched: {', '.join(prov.get('cities_searched') or []) or 'none'}",
                f"- Raw result hits: {prov.get('raw_result_hits')}",
                f"- Unique branches attributed: {prov.get('branches_discovered')}",
                f"- Likely cause: {prov.get('likely_cause')}",
                "",
                "Notes:",
                "",
            ]
        )
        for note in prov.get("notes") or []:
            lines.append(f"- {note}")
        lines.append("")
        if prov.get("sample_queries"):
            lines.append("Sample queries:")
            lines.append("")
            for q in prov["sample_queries"][:15]:
                lines.append(
                    f"- `{q.get('query')}` → raw={q.get('raw_results')} "
                    f"new={q.get('new_unique')} err={q.get('error') or '-'}"
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def build_zero_province_investigation(result: DiscoveryRunResult) -> dict[str, Any]:
    """Explain provinces that still have zero attributed branches after expansion."""
    provinces_out = []
    for p in result.provinces:
        if p.branches_discovered > 0:
            continue
        sample = [o for o in result.query_outcomes if o.province_en == p.province_en]
        raw_total = sum(o.raw_results for o in sample)
        errors = [o for o in sample if o.error]
        non_empty = [o for o in sample if o.raw_results > 0]

        if not sample:
            cause = "No queries were executed for this province (plan/budget truncation)."
        elif errors and not non_empty:
            cause = "All province queries failed (Maps/network/consent errors)."
        elif raw_total == 0:
            cause = (
                "Maps returned no Tipax-like place cards for province/city/alias variants. "
                "Listings may be absent, misnamed, or suppressed in limited view."
            )
        elif non_empty and all(o.new_unique == 0 for o in non_empty):
            cause = (
                "Results appeared but were all duplicates of branches already attributed "
                "to other provinces/queries (geo attribution / naming mismatch)."
            )
        else:
            cause = "Unknown — inspect query outcomes."

        notes = [
            f"Executed {len(sample)} targeted queries including gap aliases "
            f"(تیپاکس / Tipax / نمایندگی / اکسس پوینت / Tipax branch / Tipax service point).",
            "City-level and English province probes were included for gap provinces.",
            "Review extraction was not run; this investigation is discovery-only.",
        ]
        if p.province_en in {"Ardabil", "Kermanshah"}:
            notes.append(
                "Phase 9 audit previously flagged this province with zero branches "
                "under province-only Tipax searches."
            )
        if raw_total == 0:
            notes.append(
                "Possible real-world gap: agencies may be listed under different brand "
                "strings, partner names, or without public Google Maps pages."
            )

        provinces_out.append(
            {
                "province_en": p.province_en,
                "province_fa": p.province_fa,
                "queries_executed": p.queries_executed,
                "cities_searched": sorted(set(p.cities_searched)),
                "raw_result_hits": p.raw_result_hits,
                "branches_discovered": p.branches_discovered,
                "likely_cause": cause,
                "notes": notes,
                "sample_queries": [asdict(o) for o in sample[:20]],
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": (
            f"{len(provinces_out)} province(s) still have zero attributed Tipax branches "
            "after multi-level discovery (province/city/district/alias expansion)."
            if provinces_out
            else "All 31 provinces have at least one attributed branch."
        ),
        "provinces": provinces_out,
    }
