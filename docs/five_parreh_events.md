# Future Five-Parreh events (product layer)

Five-Parreh is a **future betting/prediction event**, not “any five races in the freeze”.

## Model

```text
Future race program (shared)
  → Meeting (date + track/city)
    → Races with scheduled_start
  → Five-Parreh event (exactly 5 designated races, all still in the future)
    → Prediction API per race (existing engine)
    → User horse selections
    → Five-Parreh combination engine (count + cost only)
```

## Shared source with `/predict`

Discovery uses the **same** race-program file/API:

- Runtime path: `RACE_PROGRAM_PATH` (default `data/race_program/program.json`)
- Example: `data/race_program/program.example.json`
- HTTP: `GET /race-program/upcoming`, `GET /race-program/five-parreh`
- Legacy `{ "events": [...] }` documents are still accepted by the loader

Each race requires `scheduled_start` (ISO-8601). Eligible only when:

```text
scheduled_start > current_time
```

Completed / started races and races with missing schedule are rejected for live prediction.

## Combination engine

Unchanged: `src/five_parreh` still only does Cartesian product + cost.
