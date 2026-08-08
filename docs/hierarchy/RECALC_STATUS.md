# Hierarchy recalculation status

| Item | Status |
| --- | --- |
| Conceptual model locked | Yes — see `DATA_MODEL.md` |
| Deterministic ID rules | Yes — no guessed UUIDs |
| Rebuild script | `scripts/rebuild_race_hierarchy.py` |
| Unit tests | `tests/test_race_hierarchy.py` (Heat ≠ Race Day) |
| Prior Race=Heat reports | **INVALID** — see `INVALIDATED_REPORTS.md` |
| Coverage announced | **No** |
| Enrichment run | **No** |
| Completeness % announced | **No** |

## Production warehouse

Expected path: `/workspace/output/historical/horse_racing.db`

On this agent VM the file is **absent** (it lives on the horse-racing collector agent disk).  
`rebuild_race_hierarchy.py` exits with `database_not_found` until that SQLite file is mounted or copied here.

## Field inventory (live schema)

See `DATA_MODEL.md` §1–3 for how each of Race Week / Race Day / Heat / Result / Horse
is derived from existing columns without inventing IDs.
