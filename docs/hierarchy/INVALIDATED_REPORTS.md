# INVALID — prior Race = Heat reports

**Status: INVALID as of hierarchy model lock.**

Any prior metric, coverage figure, or collection summary that treated a warehouse
`wh_races` row (Individual Race / Heat) as a **Race Day** or as the sole meaning
of “Race” without the hierarchy

`Race Week → Race Day → Heat → Result → Horse`

must be discarded and recalculated via:

```bash
python scripts/rebuild_race_hierarchy.py
```

Explicitly invalidated (non-exhaustive):

- `docs/collection/FINAL.md` / `docs/collection/final.json`
- `docs/collection/progress_00500.md`
- `docs/VALIDATION_REPORT.md` / `docs/validation_data.json` when “races” means heats only
- Integrity / auditor / coverage artifacts that equated heat counts with race days
- Any completeness or coverage percentage derived under the old definition

No new coverage claims, enrichment, or database-completeness percentages are
published under this hierarchy lock.
