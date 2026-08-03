# Phase 10 — Nationwide Discovery Engine

## Goal

Maximize **unique Tipax branch discovery** across Iran. Review extraction is intentionally unchanged and not run in this phase.

## Strategy

Multi-level Google Maps search instead of province-only queries:

1. **Nationwide aliases** — `تیپاکس`, `Tipax`, `نمایندگی تیپاکس`, `اکسس پوینت تیپاکس`, `Tipax branch`, `Tipax service point`
2. **Province** — core aliases × 31 provinces (full alias set for gap provinces)
3. **City** — every major city under each province
4. **Adaptive districts** — when a city returns ≥ 8 cards, expand with district-name phrase variants
5. **Gap probes** — Ardabil / Kermanshah get English + alternate FA phrases

## Entrypoint

```bash
FAST_DISCOVER=true python scripts/discover_tipax_nationwide.py \
  --db data/tipax_iran.db \
  --report-dir /opt/cursor/artifacts/phase10_discovery
```

Plan-only (no browser):

```bash
python scripts/discover_tipax_nationwide.py --plan-only
```

## Outputs

- `docs/phase10_discovery/discovery_coverage_report.md` — per-province cities/queries/branches/dup rate/review_count
- `docs/phase10_discovery/zero_province_investigation.md` — why zero-branch provinces remain empty
- JSON mirrors under `/opt/cursor/artifacts/phase10_discovery/`

## Notes

- Uses existing `FAST_DISCOVER` card parse; does **not** modify review extraction.
- `CrawlConfig.discovery_only` skips the review loop if used via `ProductionCrawler`.
- New branches are upserted into `data/tipax_iran.db` without collecting reviews.
