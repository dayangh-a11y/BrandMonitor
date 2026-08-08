# Track Configuration (Finishing Straight)

**`straight_length_m`** is the length of the **home straight** from the final turn to the finish line.

It is **not**:

- race distance (`wh_races.distance`)
- total circuit / track perimeter length

## Reference table

`ref_track_configurations`

| Column | Meaning |
|--------|---------|
| `track_id` | Stable racecourse code (e.g. `gonbad-kavous`) |
| `track_name` | Venue name (e.g. ثامن مشهد) |
| `city` | City / WH track label |
| `straight_length_m` | Home straight meters |
| `source` | Provenance (`visual_track_diagram`) |
| `source_url` | Optional URL |
| `source_confidence` | 0–1 confidence |

Seed / display:

```bash
python scripts/seed_track_configurations.py
```

## Categories

| Category | Range |
|----------|-------|
| Short | < 200 m |
| Medium | 200–275 m |
| Long | ≥ 276 m |

## Feature Set

When a race confidently matches a `track_id`, attach:

- `straight_length_m`
- `straight_length_category`

If the city/venue is ambiguous → **do not apply** (no guessing).

## Track Context (Performance Score)

Minimum context variables:

Race Distance · Straight Length · Track/City · Breed · Horse Age · Weight · Starting Gate · Finish Position · Finish Time · Number of Runners

## Comparison rules

- Do not compare horses across different straight categories unless Track Configuration is in the model.
- Separate Track Bias (straight / track traits) from horse ability.
- Multi-track careers: analyze each start with that track’s straight length.
- Raw race results stay append-only; never overwrite history.
- New conflicting meter values → report conflict; keep prior until confirmed.

## API

```python
from src.racecourses import (
    resolve_track_configuration,
    straight_length_features,
    build_track_context,
    propose_straight_length_update,
)
```
