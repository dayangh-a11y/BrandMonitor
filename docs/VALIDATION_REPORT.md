# Production Validation Report

Generated: `2026-08-07T06:49:18.497749+00:00`

Validation crawl of the first **100** race pages from asbdavani.app (target 100).

## Totals

| Entity | Count |
|--------|------:|
| Races | 100 |
| Horses | 564 |
| Jockeys | 59 |
| Trainers | 202 |
| Owners | 596 |
| Raw race rows | 100 |
| Raw horse rows | 1022 |

## Crawl performance

| Metric | Value |
|--------|------:|
| Success | 100 |
| Failed (broken pages) | 0 |
| Skipped unchanged | 0 |
| Success rate | 100.0% |
| Average processing time | 3.23s |
| Total elapsed | 323.54s |

## Missing fields

Total missing-value issues: **0**

- None

## Duplicate entities

Candidate duplicate matches: **5**

- `trainer` score=0.9333333333333333 `عبدالحکیم مهرانی` ≈ `عبدالحی مهرانی` (fuzzy)
- `owner` score=0.9375 `عبدالجلیل مهرانی` ≈ `عبدالخلیل مهرانی` (fuzzy)
- `owner` score=0.9333333333333333 `عیدمحمدوآشوربای ایگدری` ≈ `عیدمحمدوعاشوربای ایگدری` (fuzzy)
- `owner` score=0.9629629629629629 `نور گلدی پرویز` ≈ `نورگلدی پرویز` (fuzzy)
- `horse` score=1.0 `clpnidjqr06aawrdobnvt1iie` ≈ `clpniepzs0d54wrdo50y730l2` (name_collision)

## Parsing failures

Parser error rows: **0**

- None

## Broken pages

Failed race jobs: **0**

- None

## Quality summary

```
=== Data Quality Report ===
Number of races:      100
Number of horses:     564
Number of jockeys:    59
Number of trainers:   202
Number of owners:     596
Duplicate count:      5
Missing value count:  0
Parser errors:        0
Broken URLs:          0
Invalid dates:        0
Invalid ratings:      0
Invalid times:        0
Processing speed:     0.0376s (57083.62 rows/s)
```

## Sample race

```json
{
  "id": 1,
  "name": "از 0 تا 60",
  "date": "2006-06-01",
  "track": "گنبدکاووس",
  "distance": 1000,
  "race_number": 1,
  "source_url": "https://asbdavani.app/racecards/clpniklfc1y5mwrdovypaxdou?round=1"
}
```

## Sample horse

```json
{
  "id": 1,
  "name": "چلیپا",
  "sex": "ماده",
  "birthdate": null,
  "profile_url": "https://asbdavani.app/performance/horses/clpnieq9q0ddlwrdogcq95287",
  "source_horse_id": "clpnieq9q0ddlwrdogcq95287"
}
```

## Sample result (from sample race)

```json
{
  "finish_position": 7,
  "weight": 50.0,
  "time_raw": "1:05.690"
}
```
