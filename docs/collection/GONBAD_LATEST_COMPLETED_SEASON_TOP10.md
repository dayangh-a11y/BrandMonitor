# Gonbad Kavous — Top Horses, Latest Completed Season (DB only)

**Database:** `output/historical/horse_racing.db`

## Season definition (derived from DB)

There is **no `season` column** in the warehouse. Seasons are inferred from `wh_races.race_date`:

1. Collect distinct Gonbad (`racecourse_code = 'gonbad-kavous'`) race dates.
2. Split into clusters where the gap exceeds `median(gaps)/2` = **94 days** (median gap = 189).
3. A cluster is **completed** if a later cluster exists. The latest completed cluster is used.

| Field | Value |
|-------|-------|
| Season date range | **2026-02-14 → 2026-02-14** |
| Race days in DB for this season | 2026-02-14 |
| Heats | 8 |
| Later cluster (proves completion) | 2026-08-01 → 2026-08-01 |

> **Coverage caveat:** this historical extract only stores a sparse sample of Gonbad race days (often one meeting per season half). Metrics below reflect **only rows present in the DB**, not the full live season.

## Missing / unavailable fields

| Requested field | Status |
|-----------------|--------|
| Season label (بهار/پاییز + year) | **Missing** — not stored; inferred from date gaps |
| Latest IOR | **Missing** — `wh_race_results.odds` is NULL for all rows in this season |
| Latest Rating | **Available** as `source_rating` (entrance rating); shown as Latest Rating |
| Prize money | **Available** via `wh_races.prize_json` mapped by `finish_position` |
| Average speed/time | **Partially available** — from `time_raw` + `distance` when time is present |

## Turkmen (`surface` = ترکمن)

| Rank | Horse | Starts | Wins | 2nd | 3rd | Win% | Place% | Prize | Avg Finish | Avg Speed (m/s) | Avg Time (s) | Latest Rating | Latest IOR |
|-----:|-------|-------:|-----:|----:|----:|-----:|-------:|------:|-----------:|----------------:|-------------:|--------------:|-----------:|
| 1 | یاد آی تکه | 1 | 1 | 0 | 0 | 100.0 | 100.0 | 294,000,000 | 1.0 | 13.973 | 157.446 | 83.0 | N/A |
| 2 | کارتال ترکان | 1 | 0 | 1 | 0 | 0.0 | 100.0 | 130,000,000 | 2.0 | 13.969 | 157.493 | 85.0 | N/A |
| 3 | کبوتر کاریز | 1 | 0 | 0 | 1 | 0.0 | 100.0 | 68,000,000 | 3.0 | 13.941 | 157.812 | 78.0 | N/A |
| 4 | هیجا وحدانی | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 40,000,000 | 4.0 | 13.91 | 158.158 | 69.0 | N/A |
| 5 | آرکا یالی رخشان | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 20,000,000 | 5.0 | 13.852 | 158.823 | 80.0 | N/A |
| 6 | هاندان سلطان | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 15,000,000 | 6.0 | 13.746 | 160.043 | 74.0 | N/A |
| 7 | عقاب صحرای قیداری | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 0 | 7.0 | 13.631 | 161.394 | 72.0 | N/A |
| 8 | تاخته رستم خانی | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 0 | 8.0 | 13.622 | 161.502 | 84.0 | N/A |
| 9 | آرتام رحیمی | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 0 | 9.0 | 13.512 | 162.823 | 72.0 | N/A |
| 10 | تاپار پرویز رخشان | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 0 | 10.0 | 13.504 | 162.915 | 65.0 | N/A |

**Why #1 یاد آی تکه:** ranked first by the required priority — **1 win(s)**, win% **100.0**, prize **294,000,000**, avg finish **1.0**. Next horse کارتال ترکان has wins=0, win%=0.0, prize=130,000,000, avg_finish=2.0.

## Do-Khoon (Crossbred) (`surface` = دوخون)

| Rank | Horse | Starts | Wins | 2nd | 3rd | Win% | Place% | Prize | Avg Finish | Avg Speed (m/s) | Avg Time (s) | Latest Rating | Latest IOR |
|-----:|-------|-------:|-----:|----:|----:|-----:|-------:|------:|-----------:|----------------:|-------------:|--------------:|-----------:|
| 1 | لیدی سانگ | 1 | 1 | 0 | 0 | 100.0 | 100.0 | 366,000,000 | 1.0 | 15.264 | 144.129 | 87.0 | N/A |
| 2 | سیتی گزل | 1 | 1 | 0 | 0 | 100.0 | 100.0 | 211,000,000 | 1.0 | 16.829 | 59.42 | 65.0 | N/A |
| 3 | اکوادور | 1 | 1 | 0 | 0 | 100.0 | 100.0 | 211,000,000 | 1.0 | 15.896 | 62.907 | 0.0 | N/A |
| 4 | اکس کالیبور | 1 | 1 | 0 | 0 | 100.0 | 100.0 | 211,000,000 | 1.0 | 16.09 | 62.149 | 0.0 | N/A |
| 5 | واشینگتن | 1 | 1 | 0 | 0 | 100.0 | 100.0 | 171,000,000 | 1.0 | 15.079 | 145.901 | 60.0 | N/A |
| 6 | دات کام | 1 | 1 | 0 | 0 | 100.0 | 100.0 | 137,000,000 | 1.0 | 14.921 | 147.444 | 40.0 | N/A |
| 7 | تیمسار | 1 | 0 | 1 | 0 | 0.0 | 100.0 | 162,000,000 | 2.0 | 15.188 | 144.852 | 88.0 | N/A |
| 8 | آلپین گلد | 1 | 0 | 1 | 0 | 0.0 | 100.0 | 94,000,000 | 2.0 | 16.444 | 60.812 | 60.0 | N/A |
| 9 | زرین تاج | 1 | 0 | 1 | 0 | 0.0 | 100.0 | 94,000,000 | 2.0 | 15.86 | 63.052 | 0.0 | N/A |
| 10 | هولیا | 1 | 0 | 1 | 0 | 0.0 | 100.0 | 94,000,000 | 2.0 | 15.941 | 62.73 | 0.0 | N/A |

**Why #1 لیدی سانگ:** ranked first by the required priority — **1 win(s)**, win% **100.0**, prize **366,000,000**, avg finish **1.0**. Next horse سیتی گزل has wins=1, win%=100.0, prize=211,000,000, avg_finish=1.0.

## Thoroughbred (`surface` = تروبرد)

| Rank | Horse | Starts | Wins | 2nd | 3rd | Win% | Place% | Prize | Avg Finish | Avg Speed (m/s) | Avg Time (s) | Latest Rating | Latest IOR |
|-----:|-------|-------:|-----:|----:|----:|-----:|-------:|------:|-----------:|----------------:|-------------:|--------------:|-----------:|
| 1 | سامال | 1 | 1 | 0 | 0 | 100.0 | 100.0 | 211,000,000 | 1.0 | 15.667 | 102.124 | 53.0 | N/A |
| 2 | آنیکا | 1 | 0 | 1 | 0 | 0.0 | 100.0 | 94,000,000 | 2.0 | 15.63 | 102.366 | 50.0 | N/A |
| 3 | هج لا | 1 | 0 | 0 | 1 | 0.0 | 100.0 | 49,000,000 | 3.0 | 15.591 | 102.625 | 48.0 | N/A |
| 4 | ریمیک وان | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 29,000,000 | 4.0 | 15.447 | 103.578 | 43.0 | N/A |
| 5 | ریو مونیکا | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 15,000,000 | 5.0 | 15.43 | 103.693 | 44.0 | N/A |
| 6 | فوکوس سرا | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 11,000,000 | 6.0 | 15.36 | 104.17 | 58.0 | N/A |
| 7 | آی نور مرجانی | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 0 | 7.0 | 15.095 | 105.992 | 36.0 | N/A |
| 8 | بومباستیک | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 0 | 8.0 | 15.042 | 106.37 | 38.0 | N/A |
| 9 | گراویتون | 1 | 0 | 0 | 0 | 0.0 | 0.0 | 0 | 9.0 | 15.031 | 106.444 | 37.0 | N/A |

**Why #1 سامال:** ranked first by the required priority — **1 win(s)**, win% **100.0**, prize **211,000,000**, avg finish **1.0**. Next horse آنیکا has wins=0, win%=0.0, prize=94,000,000, avg_finish=2.0.

## Specials (all breeds, same season window)

| Category | Result |
|----------|--------|
| Best trainer | **جمال آموت** — 2 wins / 3 starts (66.7%), prize 577,000,000 |
| Best jockey | **محمد صفا آموت** — 2 wins / 6 starts (33.3%), prize 592,000,000 |
| Best owner | **دایان و دیلای آق** — 1 wins / 1 starts (100.0%), prize 366,000,000 |
| Highest win rate horse | **یاد آی تکه** (ترکمن) — 1/1 = 100.0% |
| Highest earnings horse | **لیدی سانگ** (دوخون) — 366,000,000 (1 wins / 1 starts) |
| Most starts horse | **یاد آی تکه** (ترکمن) — 1 starts (1 wins) |

Trainer/jockey/owner ranking priority (DB-derived, parallel to horses): wins → win% → prize.

**Tie note:** with only one meeting in this season window, many horses are 1-start / 1-win (100% win rate) and “most starts” is tied at 1. Win-rate and most-starts specials break ties by wins then starts (then name order is not applied—first max wins). Earnings special is unique here (لیدی سانگ).

## SQL used

### Distinct Gonbad dates (season clustering input)
```sql
SELECT DISTINCT race_date AS d
FROM wh_races
WHERE racecourse_code = 'gonbad-kavous'
  AND race_date IS NOT NULL
ORDER BY race_date;
```

### Season heats
```sql
SELECT id, name, race_date, surface, distance, prize_json, source_url, race_number
FROM wh_races
WHERE racecourse_code = 'gonbad-kavous'
  AND race_date >= ?
  AND race_date <= ?
ORDER BY race_date, race_number;
-- params: season_start, season_end = latest completed cluster bounds
-- bound values used: '2026-02-14' , '2026-02-14'
```

### Results join for metrics
```sql
SELECT
  r.id AS race_id,
  r.race_date,
  r.name AS race_name,
  r.surface,
  r.distance,
  r.prize_json,
  rr.finish_position,
  rr.time_raw,
  rr.source_rating,
  rr.odds,
  rr.number,
  h.id AS horse_pk,
  h.name AS horse_name,
  h.source_horse_id,
  h.profile_url,
  j.name AS jockey_name,
  t.name AS trainer_name,
  o.name AS owner_name
FROM wh_race_results rr
JOIN wh_races r ON r.id = rr.race_id
LEFT JOIN wh_horses h ON h.id = rr.horse_id
LEFT JOIN wh_jockeys j ON j.id = rr.jockey_id
LEFT JOIN wh_trainers t ON t.id = rr.trainer_id
LEFT JOIN wh_owners o ON o.id = rr.owner_id
WHERE r.racecourse_code = 'gonbad-kavous'
  AND r.race_date >= ?
  AND r.race_date <= ?
ORDER BY r.race_date, r.race_number, rr.finish_position;
-- params: '2026-02-14' , '2026-02-14'
```

### Ranking rule (applied in Python after SQL fetch)
```text
ORDER BY wins DESC, (wins*1.0/starts) DESC, total_prize DESC, avg(finish_position) ASC
Prize per start = prize_json.prizes[rank==finish_position].prize
Avg speed (m/s) = distance_m / time_seconds(time_raw) when both present
Starts exclude finish_position IS NULL OR finish_position <= 0
```
