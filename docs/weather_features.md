# Race Weather & Track-Condition Features

ML-ready weather layer for every warehouse race.

## Data flow

```
WhRace (date + racecourse_code)
        ↓ weather backfill (Open-Meteo Archive)
raw_weather_observations   (append-only, versioned)
        ↓ weather attach
wh_race_weather            (structured race-day snapshot + track condition)
        ↓ features build -p race_weather
feat_race_weather          (derived windows / heat index / moisture)
        ↓ features build -p horse_weather
feat_horse_weather
feat_horse_weather_buckets (normalized horse×bucket stats)
```

## CLI

```bash
python main.py init-db
python main.py weather backfill [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--courses gonbad-kavous]
python main.py weather attach
python main.py features build -p race_weather
python main.py features build -p horse_weather
```

## Fields stored per race (`wh_race_weather`)

| Field | Source |
|-------|--------|
| Air temperature, humidity, wind speed/direction, pressure | Open-Meteo hourly @ default race hour |
| Rainfall (hour + day) | Open-Meteo |
| Rain probability | Archive rarely has it → binary proxy from precip when missing |
| Cloud cover, visibility | Open-Meteo (when model provides visibility) |
| Weather condition | WMO weather_code → label |
| Race start time | **Estimated** (`WEATHER_DEFAULT_RACE_HOUR`, default 14:00 local) — asbdavani has no post time |
| Track condition | **Estimated** from rainfall windows (`dry/firm/soft/wet/muddy`) until source publishes going |

## Derived race features (`feat_race_weather`)

- Average temperature previous 3 days
- Rainfall previous 3 and 7 days
- Heat index (°C)
- Weather category (`clear/cloudy/precip/storm/fog/snow/unknown`)
- Surface moisture indicator (0..1)
- Temperature range bucket
- Denormalized snapshot columns for flat ML matrices

## Horse features

`feat_horse_weather`:

- Win rate by weather condition / track condition (JSON maps)
- Average finishing position by temperature range
- Average race time by weather
- Weather sensitivity score (spread of win rates across categories)
- Track-condition preference score + preferred bucket

`feat_horse_weather_buckets`: one row per `(horse_id, dimension, bucket_key)` for target encoding / joins.

## Coordinates

`src/racecourses/registry.py` stores approximate WGS84 lat/lon + `Asia/Tehran` timezone for Golestan tracks.

## Notes / limitations

1. Source site `wh_races.weather` string is usually NULL; this layer does not depend on it.
2. Track condition is a deterministic rainfall heuristic, not an official stewards’ report (`track_condition_source=estimated`).
3. Race start time is estimated; set `WEATHER_DEFAULT_RACE_HOUR` if meetings typically differ.
4. Weather Raw rows follow append-only versioning (`is_current`, `source_hash`).
