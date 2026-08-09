# Future race program

Shared source for Telegram **`/predict`** and **`/fiveparreh`**.

## Eligibility

```text
eligible_for_prediction = scheduled_start > current_time
```

- Past and currently running races (start ≤ now) are excluded.
- Missing `scheduled_start` ⇒ `status: unknown_time` — **not** offered for live prediction.
- Default upcoming window: **7 days**.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/race-program/upcoming?days=7` | Upcoming meetings + eligible races |
| GET | `/race-program/meetings/{meeting_id}` | Races for one future meeting |
| GET | `/race-program/five-parreh` | Future Five-Parreh events (same source) |
| GET | `/race-program/five-parreh/{event_id}` | One future event |

Config: `RACE_PROGRAM_PATH` (default `data/race_program/program.json`).

## Does not change

- Scoring / `rank_race` / ML gate / frozen dataset
- Five-Parreh combination engine (`POST /five-parreh/combinations`)
