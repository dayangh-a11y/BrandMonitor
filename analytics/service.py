from __future__ import annotations

import time
from typing import Any

from analytics.compute import build_branch_dashboard, build_company_dashboard, compare_entities
from analytics.filters import AnalyticsFilter
from analytics.geo_compute import build_geo_dashboard
from core.logging_setup import get_logger

log = get_logger("api")

DEFAULT_TTL_SECONDS = 300


class AnalyticsService:
    """Reads existing DB data, builds dashboards, serves/refreshes snapshots."""

    def __init__(self, db, *, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.db = db
        self.ttl_seconds = ttl_seconds

    async def company_dashboard(
        self,
        company_id: int,
        filt: AnalyticsFilter | None = None,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        filt = filt or AnalyticsFilter()
        kind = "company_dashboard"
        cache_key = filt.cache_key()
        if not force_refresh:
            cached = await self.db.get_analytics_snapshot(
                "company", company_id, kind, cache_key
            )
            if cached and self._fresh(cached.get("computed_at")):
                payload = cached["payload"]
                payload["cache"] = {"hit": True, "computed_at": cached["computed_at"]}
                return payload

        t0 = time.perf_counter()
        company = await self.db.get_company(company_id)
        if company is None:
            raise KeyError(f"company {company_id}")
        branches = await self.db.list_company_branches(company_id, limit=100000)
        # Enrich with city/province from raw rows
        raw_branches = {int(b["id"]): b for b in await self.db.list_company_branch_rows(company_id)}
        for b in branches:
            raw = raw_branches.get(int(b["id"]), {})
            b["city"] = raw.get("city") or ""
            b["province"] = raw.get("province") or ""
        rows = await self.db.list_company_analytics_rows(company_id)
        score = await self.db.get_company_score(company_id)
        insights = await self.db.get_company_insights(company_id)
        history = await self.db.list_company_score_history(company_id, limit=60)
        payload = build_company_dashboard(
            company=company,
            branches=branches,
            rows=rows,
            score=score,
            insights=insights,
            score_history=history,
            filt=filt,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        payload["performance"] = {
            "build_ms": round(elapsed_ms, 2),
            "source_rows": len(rows),
            "ttl_seconds": self.ttl_seconds,
        }
        await self.db.upsert_analytics_snapshot(
            "company", company_id, kind, cache_key, payload
        )
        payload["cache"] = {"hit": False, "computed_at": payload.get("performance")}
        log.info(
            "analytics_company_built id=%s rows=%s ms=%.1f filter=%s",
            company_id,
            len(rows),
            elapsed_ms,
            cache_key,
        )
        return payload

    async def branch_dashboard(
        self,
        branch_id: int,
        filt: AnalyticsFilter | None = None,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        filt = filt or AnalyticsFilter()
        kind = "branch_dashboard"
        cache_key = filt.cache_key()
        if not force_refresh:
            cached = await self.db.get_analytics_snapshot(
                "branch", branch_id, kind, cache_key
            )
            if cached and self._fresh(cached.get("computed_at")):
                payload = cached["payload"]
                payload["cache"] = {"hit": True, "computed_at": cached["computed_at"]}
                return payload

        t0 = time.perf_counter()
        branch = await self.db.get_branch(branch_id)
        if branch is None:
            raise KeyError(f"branch {branch_id}")
        # city/province may be missing on get_branch projection — reload raw
        raw = await self.db.list_company_branch_rows(int(branch["company_id"]))
        for item in raw:
            if int(item["id"]) == branch_id:
                branch["city"] = item.get("city") or ""
                branch["province"] = item.get("province") or ""
                break
        company = await self.db.get_company(int(branch["company_id"]))
        rows = await self.db.list_branch_analytics_rows(branch_id)
        score = await self.db.get_branch_score(branch_id)
        insights = await self.db.get_branch_insights(branch_id)
        history = await self.db.list_branch_score_history(branch_id, limit=60)
        payload = build_branch_dashboard(
            branch=branch,
            company_name=(company or {}).get("name") or "",
            rows=rows,
            score=score,
            insights=insights,
            score_history=history,
            filt=filt,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        payload["performance"] = {
            "build_ms": round(elapsed_ms, 2),
            "source_rows": len(rows),
            "ttl_seconds": self.ttl_seconds,
        }
        await self.db.upsert_analytics_snapshot(
            "branch", branch_id, kind, cache_key, payload
        )
        payload["cache"] = {"hit": False}
        return payload

    async def compare(
        self,
        *,
        mode: str,
        ids: list[int] | None = None,
        names: list[str] | None = None,
        filt: AnalyticsFilter | None = None,
    ) -> dict[str, Any]:
        filt = filt or AnalyticsFilter()
        mode = mode.lower()
        payloads: list[dict[str, Any]] = []
        label_key = "company_name"

        if mode == "company":
            label_key = "company_name"
            for cid in ids or []:
                payloads.append(await self.company_dashboard(cid, filt))
        elif mode == "branch":
            label_key = "branch_name"
            for bid in ids or []:
                payloads.append(await self.branch_dashboard(bid, filt))
        elif mode in {"province", "city"}:
            # Compare geo slices within a company (first id) or across all companies.
            company_id = (ids or [None])[0]
            if company_id is None:
                companies = await self.db.list_companies(limit=100)
                rows = []
                for c in companies:
                    rows.extend(await self.db.list_company_analytics_rows(int(c["id"])))
                company_name = "All companies"
            else:
                company = await self.db.get_company(int(company_id))
                if company is None:
                    raise KeyError(f"company {company_id}")
                rows = await self.db.list_company_analytics_rows(int(company_id))
                company_name = company["name"]
            targets = names or []
            for name in targets:
                local = AnalyticsFilter(**{**filt.to_dict(), mode: name})
                filtered_rows = [
                    r
                    for r in rows
                    if (r.get(mode) or "").lower() == name.lower()
                ]
                # Build a lightweight geo dashboard from company builder subset
                branches = []
                score = {"score": 0, "components": {}}
                if filtered_rows:
                    ratings = [float(r.get("review_rating") or 0) for r in filtered_rows]
                    from collections import Counter

                    sent = Counter(str(r.get("sentiment") or "Neutral") for r in filtered_rows)
                    pos = sum(sent.get("Positive", 0) for _ in [0])
                    # rough score proxy from CSI
                    from analytics.compute import _csi

                    csi = _csi(sent)
                    payload = {
                        "name": name,
                        "overall_score": csi,
                        "average_rating": round(sum(ratings) / len(ratings), 3) if ratings else 0,
                        "total_reviews": len(filtered_rows),
                        "customer_satisfaction_index": csi,
                        "sentiment_distribution": dict(sent),
                        "complaint_categories": [],
                        "positive_categories": [],
                        "company_name": company_name,
                    }
                    # fill ranked cats
                    from analytics.compute import build_company_dashboard

                    # Use empty branch list; company stub
                    stub = await self.db.get_company(int(company_id)) if company_id else {
                        "id": 0,
                        "name": company_name,
                    }
                    full = build_company_dashboard(
                        company=stub or {"id": 0, "name": company_name},
                        branches=[],
                        rows=filtered_rows,
                        score={"score": csi, "components": {}},
                        insights={"summary": f"{mode.title()} {name}", "pros": [], "cons": []},
                        score_history=[],
                        filt=local,
                    )
                    full["name"] = name
                    payloads.append(full)
            label_key = "name"
        elif mode == "period":
            # names = ["2026-01-01:2026-01-31", "2026-02-01:2026-02-28"]
            company_id = (ids or [None])[0]
            if company_id is None:
                raise ValueError("period compare requires company id")
            for period in names or []:
                if ":" not in period:
                    continue
                start, end = period.split(":", 1)
                local = AnalyticsFilter(**{**filt.to_dict(), "date_from": start, "date_to": end})
                dash = await self.company_dashboard(int(company_id), local)
                dash["name"] = period
                payloads.append(dash)
            label_key = "name"
        else:
            raise ValueError(f"unsupported compare mode: {mode}")

        result = compare_entities(payloads, label_key=label_key)
        result["mode"] = mode
        result["filters"] = filt.to_dict()
        return result

    async def geo_dashboard(
        self,
        company_id: int,
        filt: AnalyticsFilter | None = None,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Phase 11 geographic visualization payload (read-only over existing data)."""
        filt = filt or AnalyticsFilter()
        kind = "geo_dashboard"
        cache_key = filt.cache_key()
        if not force_refresh:
            cached = await self.db.get_analytics_snapshot(
                "company", company_id, kind, cache_key
            )
            if cached and self._fresh(cached.get("computed_at")):
                payload = cached["payload"]
                payload["cache"] = {"hit": True, "computed_at": cached["computed_at"]}
                return payload

        t0 = time.perf_counter()
        company = await self.db.get_company(company_id)
        if company is None:
            raise KeyError(f"company {company_id}")

        branches = await self.db.list_company_branches(company_id, limit=100000)
        raw_branches = {
            int(b["id"]): b for b in await self.db.list_company_branch_rows(company_id)
        }
        for b in branches:
            raw = raw_branches.get(int(b["id"]), {})
            b["city"] = raw.get("city") or b.get("city") or ""
            b["province"] = raw.get("province") or b.get("province") or ""
            b["latitude"] = raw.get("latitude")
            b["longitude"] = raw.get("longitude")
            b["maps_url"] = raw.get("maps_url") or ""
            b["review_count"] = raw.get("review_count") or b.get("review_count") or 0

        rows = await self.db.list_company_analytics_rows(company_id)
        insights_by_branch = await self.db.list_company_branch_insights(company_id)
        payload = build_geo_dashboard(
            company=company,
            branches=branches,
            rows=rows,
            insights_by_branch=insights_by_branch,
            filt=filt,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        payload["performance"] = {
            "build_ms": round(elapsed_ms, 2),
            "source_rows": len(rows),
            "ttl_seconds": self.ttl_seconds,
        }
        await self.db.upsert_analytics_snapshot(
            "company", company_id, kind, cache_key, payload
        )
        payload["cache"] = {"hit": False}
        log.info(
            "analytics_geo_built id=%s pins=%s ms=%.1f",
            company_id,
            len(payload.get("map_pins") or []),
            elapsed_ms,
        )
        return payload

    async def refresh_all(self) -> dict[str, Any]:
        companies = await self.db.list_companies(limit=100000)
        out = {"companies": 0, "branches": 0, "geo": 0}
        filt = AnalyticsFilter()
        for company in companies:
            await self.company_dashboard(int(company["id"]), filt, force_refresh=True)
            await self.geo_dashboard(int(company["id"]), filt, force_refresh=True)
            out["companies"] += 1
            out["geo"] += 1
            for branch in await self.db.list_company_branches(int(company["id"]), limit=100000):
                await self.branch_dashboard(int(branch["id"]), filt, force_refresh=True)
                out["branches"] += 1
        return out

    def _fresh(self, computed_at: str | None) -> bool:
        if not computed_at:
            return False
        try:
            # ISO timestamp
            from datetime import datetime, timezone

            ts = datetime.fromisoformat(computed_at.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
            return age <= self.ttl_seconds
        except Exception:
            return False
