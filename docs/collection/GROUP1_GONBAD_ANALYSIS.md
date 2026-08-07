# Analytical Report: Latest Group 1 Thoroughbred at Gonbad Kavous

**Selection rule (database only):**  
`racecourse_code = gonbad-kavous` AND `surface = تروبرد` AND race name matching pure **گروه 1** (not `گروه 1 و 2`).  

**Selected race:** warehouse `wh_races.id = 562` — the latest such heat by `race_date`.

Source: collected historical DB (`output/historical/horse_racing.db`).  
No external lookup. Gaps below are gaps in the stored source extract.

---

## 1. Race information

| Field | Value | Evidence |
|--------|--------|----------|
| Race ID | 562 | `wh_races.id` |
| Name | گروه 1 | `wh_races.name` |
| Date | **1997-12-05** | `wh_races.race_date` |
| Track | گنبدکاووس | `wh_races.track` / `racecourse_code=gonbad-kavous` |
| Distance | **1800** m | `wh_races.distance` |
| Surface | **تروبرد** (Thoroughbred) | `wh_races.surface` |
| Weather | **Not available** | `wh_races.weather` is NULL; raw payload `weather` is null |
| Race number (heat) | 6 | `wh_races.race_number` |
| Runners (card) | **12** | 12 `wh_race_results` / raw horses |
| Prize total | 525,000 | `prize_json.total` |
| Source URL | https://asbdavani.app/racecards/clpnipd2p2e50wrdoegb9alm8?round=6 | `source_url` |
| Video | None stored | no `wh_race_videos`; historical media placeholder without URL |

---

## 2. Final results

**Important data limitation:** In this heat the source only records finishing positions **1, 2, 3**. Other runners have `finish_position = 0` or `NULL` (no official order beyond the frame in the extract). Final times and margins are **null / 0.0** for all runners. Card ratings are **0.0** for every horse. Jockey names are **null** for every runner.

| Order | Cloth | Horse | Time | Margin | Rating | Weight | Notes |
|------:|------:|-------|------|-------:|-------:|-------:|-------|
| 1st | 12 | صبرا | n/a | n/a (0.0) | 0.0 | 56.0 | Winner |
| 2nd | 8 | بگونیا | n/a | n/a (0.0) | 0.0 | 50.5 | |
| 3rd | 11 | جهان نما | n/a | n/a (0.0) | 0.0 | 50.5 | |
| Unplaced / incomplete in source | 1 | چلنجر | n/a | 0.0 | 0.0 | 51.5 | `finish_position=0` |
| | 3 | سعادت | n/a | 0.0 | 0.0 | 52.0 | `finish_position=0` |
| | 4 | بهرام صداقت(شمن) | n/a | 0.0 | 0.0 | 50.0 | `finish_position=0` |
| | 5 | کبری | n/a | 0.0 | 0.0 | 58.0 | `finish_position=0` |
| | 6 | دنیا گزل | n/a | 0.0 | 0.0 | 50.0 | `finish_position=0` |
| | 7 | اولکام گنبد | n/a | 0.0 | 0.0 | 51.0 | `finish_position=0` |
| | 9 | سرمست | n/a | 0.0 | 0.0 | 51.0 | `finish_position=0` |
| | 10 | جهان استار | n/a | 0.0 | 0.0 | 51.5 | `finish_position=0` |
| | 2 | وات سکرت | n/a | 0.0 | 0.0 | 56.0 | `finish_position=NULL` (no result in extract) |

---

## 3. Winner analysis — صبرا

| Field | Value | Evidence |
|--------|--------|----------|
| Horse | صبرا | result + `wh_horses` |
| Horse ID | 3276 / `clpnigews0o7hwrdow1m6ihmu` | warehouse / source |
| Profile URL | https://asbdavani.app/performance/horses/clpnigews0o7hwrdow1m6ihmu | |
| Sex | نر | race-card payload / `wh_horses.sex` |
| Age | **3** (on this card) | raw race horse `age` field (birthdate not stored) |
| Birthdate | Not in DB | `wh_horses.birthdate` NULL |
| Trainer | ارازقلی ایری | `wh_trainers` via result |
| Jockey | **Not in DB** | null on raw entry and warehouse |
| Owner | حالت قلی قره سارلی | `wh_owners` via result |
| Carried weight | 56.0 | `wh_race_results.weight` |

---

## 4. Previous performance (winner) — DB only

Starts for صبرا in the collected DB with `race_date < 1997-12-05` (Golestan triad archive only; not a full national career):

| Date | Race | Track | Dist | Finish | Time |
|------|------|-------|-----:|-------:|------|
| 1997-05-09 | از 42 تا 56 امتیاز | گنبدکاووس | 1700 | 2 | n/a |
| 1996-12-06 | از 32 تا 52 امتیاز | گنبدکاووس | 1650 | 3 | n/a |
| 1996-05-24 | گروه 3 | بندرترکمن | 1500 | 3 | n/a |
| 1996-04-26 | گروه 3 | گنبدکاووس | 1600 | **1** | **1:46.400** |
| 1995-10-13 | گروه شروع تشویقی | بندرترکمن | 1000 | **1** | n/a |

**Last 10 races in DB:** only **5** prior starts exist.

| Metric | Value | Definition used |
|--------|------:|-----------------|
| Starts in DB before this race | 5 | |
| Wins | 2 | finish_position = 1 |
| Places (1–3) | 5 | finish_position ∈ {1,2,3} |
| Win percentage | **40%** | 2/5 |
| Place percentage | **100%** | 5/5 |
| Finishing trend (newest → oldest) | 2, 3, 3, 1, 1 | |
| Rating trend | All stored ratings **0.0** | no usable rating series |

---

## 5. Competition analysis

### Ratings
Every runner’s `source_rating` in this race is **0.0**.

| Requested metric | Result from DB |
|------------------|----------------|
| Average rating of the field | **0.0** (12/12 rated 0) |
| Strongest rival (by rating) | **Cannot be determined** — no rating differentiation |
| Weakest rival (by rating) | **Cannot be determined** — no rating differentiation |
| Field strength score (rating-based) | **Not computable** — all ratings zero |

### Form-based field picture (evidence substitute)
Using only prior DB finishes with `finish_position > 0` before 1997-12-05:

| Runner | Prior valid finishes | Win% | Place% | Avg finish (≤5) |
|--------|---------------------:|-----:|-------:|----------------:|
| وات سکرت | 1 | 100 | 100 | 1.0 |
| **صبرا** | 5 | **40** | **100** | **2.0** |
| جهان استار | 1 | 0 | 100 | 2.0 |
| کبری | 1 | 0 | 100 | 3.0 |
| بهرام صداقت(شمن) | 6 | 0 | 66.7 | 2.8 |
| دنیا گزل | 5 | 0 | 60 | 4.6 |
| سرمست | 2 | 0 | 50 | 3.5 |
| سعادت | 3 | 0 | 33.3 | 5.7 |
| چلنجر | 1 | 0 | 0 | 5.0 |
| بگونیا | 1 | 0 | 0 | 5.0 |
| اولکام گنبد | 4 | 0 | 0 | 7.0 |
| جهان نما | 0 | — | — | — |

**Transparent field-strength proxy (not a trained model):**  
mean prior place% among runners with ≥1 valid prior finish = **55.5%** (11 horses).  
Interpretation: the field mixes a few strong form horses with several weak/unknown form lines; rating-based strength is unavailable.

**Strongest rival by prior form evidence:** وات سکرت (1/1 win at Gonbad 1700 on 1997-05-09) — but this horse has `finish_position=NULL` in the Group 1 extract (no recorded result).  
**Among horses that finished 2nd/3rd:** بگونیا (prior: one 5th) and جهان نما (no prior finishes in DB).

---

## 6. Why the winner was successful (evidence only)

From historical rows only:

1. **Consistent placing:** صبرا’s five prior DB starts were all top-3 (place rate 100%).
2. **Proven winning ability:** two prior wins, including a **گروه 3** win at Gonبد (1996-04-26, 1600m, time 1:46.400).
3. **Recent form:** last start before this Group 1 was 2nd at Gonbad over 1700m (1997-05-09).
4. **Distance context:** prior wins/places at 1000–1700m; this race is 1800m — same track (Gonbad) as several strong priors.
5. **What we cannot claim:** jockey performance, sectional times, margins, weather, or rating edge — those fields are missing or zero in the extract.

---

## 7. Pre-race top-three contender?

**Question:** If this race had not yet been run, would the database have identified صبرا as one of the top three contenders?

**Answer: Yes — under a form ranking that uses only pre-race DB history.**

**Method (explicit, not a black-box model):**  
Rank runners with ≥1 valid prior finish by:

1. higher prior place%  
2. then higher prior win%  
3. then lower average finish (last ≤5)

**Pre-race top 3 by that ranking:**

| Rank | Horse | Place% | Win% | Avg finish | Actual result in this race |
|-----:|-------|-------:|-----:|-----------:|----------------------------|
| 1 | وات سکرت | 100 | 100 | 1.0 | No result recorded (`NULL`) |
| 2 | **صبرا** | **100** | **40** | **2.0** | **Won** |
| 3 | جهان استار | 100 | 0 | 2.0 | `finish_position=0` (incomplete) |

So **صبرا is #2 on pre-race form evidence** and is inside the top three.

**Caveats (must state):**
- Card ratings cannot identify contenders here (all 0).
- Ranking uses only Golestan races present in this DB, not a full career file.
- وات سکرت ranks above صبرا on the same rules but has only **one** prior start.
- No odds or model probabilities exist in the platform.

---

## Selection note

Later Gonbad Thoroughbred heats exist (through 2026), but their names are handicaps, maidens, “کلاس…”, or **G2** (e.g. `مایل بهاره (G2)`).  
The latest **pure `گروه 1` + تروبرد + گنبدکاووس** row in the collected DB is **1997-12-05** (id 562).
