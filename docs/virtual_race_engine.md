# Virtual Race Engine

Score **hypothetical** races without a database `race_id`.

No `wh_races` row is required. A temporary field is built from the card,
then pre-race / market scoring is reused.

## Input

| Field | Notes |
|-------|--------|
| Horse list | `horse_id`, permanent id, or identity signals (name/sire/dam/age/sex/owner/trainer) |
| Distance | metres |
| Class | race class label |
| Track / track_condition | going / surface |
| Weather | dict (temp, humidity, rain, wind, …) |
| Racecourse | code or Persian name |
| Weights / draw / jockeys / trainers | per runner overlays |
| Date | used for rest-day calculation |

## Output

- Win probability · Top3 probability · Pairwise probabilities
- Race report (strength, pace, shape, recommendations)
- Value horse · Dark horse · Risk · Confidence

**Does not save unless `persist=True` / `--persist`.**

## CLI

```bash
python main.py virtual run -f scenario.json
python main.py virtual run -f scenario.json --persist --key gonbad-demo
python main.py virtual run -f scenario.json --json
```

### Example `scenario.json`

```json
{
  "distance": 1000,
  "class": "کلاس6(60-46)",
  "racecourse": "گنبدکاووس",
  "date": "2026-08-07",
  "track_condition": "dry",
  "weather": {"air_temperature_c": 34, "humidity_pct": 28, "rainfall_mm": 0},
  "race_name": "Virtual Class 6",
  "horses": [
    {
      "horse_id": 4150,
      "weight": 59,
      "draw": 1,
      "jockey": "بهمن اونق",
      "trainer": "بهمن اونق",
      "rating": 60,
      "odds": 3.2
    },
    {
      "name": "بادپا",
      "sex": "نر",
      "age": 3,
      "weight": 58,
      "draw": 2,
      "jockey": "احسان جرجانی",
      "trainer": "احسان جرجانی",
      "rating": 58
    }
  ]
}
```

## API

```python
from src.virtual_race import build_virtual_race_report, scenario_from_dict

payload = build_virtual_race_report(session, scenario_from_dict(data), persist=False)
# payload["horses"][*].winning_probability / top3_probability
# payload["pairwise"], payload["reports"], payload["risk"], payload["confidence"]
```

## Package

`src/virtual_race/` — `scenario`, `field`, `engine`, `report`, `models` (`anl_virtual_race_reports`)
