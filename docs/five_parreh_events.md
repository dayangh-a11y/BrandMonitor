# Future Five-Parreh events (Telegram product layer)

Five-Parreh is a **future betting/prediction event**, not “any five races in the freeze”.

## Model

```text
Future race meeting
  → Five-Parreh event (exactly 5 designated races, all still in the future)
    → Prediction API per race (existing engine)
    → User horse selections
    → Five-Parreh combination engine (count + cost only)
```

## Event source

Declared events are loaded from JSON (no fabrication from `race_id` arithmetic):

- Example schema: `data/five_parreh/events.example.json`
- Runtime path: `FIVE_PARREH_EVENTS_PATH` (default `data/five_parreh/events.json`)
- Missing file ⇒ **no events** (bot shows an empty/unavailable message)

Each race requires `scheduled_start` (ISO-8601). An event is listed only if:

1. it has **exactly 5** races, and  
2. **every** race `scheduled_start` is strictly after “now”.

Completed / started races are rejected.

## Combination engine

Unchanged: `src/five_parreh` still only does Cartesian product + cost.
