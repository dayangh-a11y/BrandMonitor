# Tipax Data Quality Report (Phase 9)

Generated: `2026-08-03T04:54:11.992886+00:00`  
Database: `data/tipax_iran.db`  

## 1. Executive summary

- Unique Tipax branches in DB: **369**
- Reviews stored: **1804**
- Data Quality Score: **85.7/100**
- Crawler completion (Maps task queue): **100.0%** (discovered tasks finished)
- Estimated network coverage vs official Tipax footprint: **27.6%** (369 / 1336)

### Crawler Completion vs Network Coverage

| Concept | Meaning | Value |
|---------|---------|------:|
| **Crawler Completion** | Google Maps crawl tasks succeeded / discovered | 100.0% |
| **Network Coverage** | Unique Maps branches / official Tipax agencies estimate | 27.6% |

Official estimate source: Tipax annual report 1403 / public claims: ~1,300+ agencies; DMBoard summary cites 1,336 contact points (up from 1,132 in 1402).

## 2. Data quality score

| Dimension | Score |
|-----------|------:|
| Completeness | 91.0 |
| Consistency | 93.6 |
| Uniqueness | 92.9 |
| Accuracy | 62.6 |
| Freshness | 100.0 |
| **Overall** | **85.7** |

Weights: completeness 25%, consistency 20%, uniqueness 20%, accuracy 25%, freshness 10%.

## 3. Branch audit

- Total unique branches: **369**
- Duplicate extra rows (same place_id/name+address): **0**
- Same-name different place_id groups: **2**
- Missing coordinates: **0**
- Missing phone: **82**
- Missing Google Maps URL: **0**
- Zero collected reviews: **67**
- Suspicious review counts: **47**

## 4. Review quality

- Total reviews: **1804**
- Duplicate extras (content): **425**
- Empty reviews: **477**
- Malformed reviews: **472**
- Language detection errors: **0**
- Impossible ratings: **0**
- Missing dates: **0**
- Owner responses present: **0**

## 5. Geographic coverage

- Known provinces hit: **29 / 31**
- Provinces with no branches: **Ardabil, Kermanshah**
- Unusually low provinces (≤ 2 branches): Qazvin (1), Qom (2), Markazi (2), Bushehr (2), Ilam (1), Kohgiluyeh and Boyer-Ahmad (1), Golestan (1), Semnan (1), Zanjan (1), South Khorasan (2)

## 6. Known issues

- Network coverage is low vs official Tipax footprint: 369 Maps places vs ~1336 agencies (27.6%).
- 47 branches show suspicious claimed review_count patterns (often 320 or large claimed vs few collected).
- 82 branches missing phone; 0 missing coordinates.
- 67 branches have zero collected reviews (Maps review pane often blocked / limited).
- Owner responses present: 0 (extraction effectively empty in this dataset).
- Provinces with no matched branches: Ardabil, Kermanshah.
- 2 same-name groups with different place_id values — may include true multi-location brands or weak identity keys.

## 7. Recommended fixes

- Treat Crawler Completion and Network Coverage as separate KPIs in all future reports.
- Improve Maps review scrolling / residential sessions to raise reviews per branch and owner replies.
- Fix review_count parsing that collapses to the 320 artifact; prefer place-pane counts only.
- Normalize province/city labels (FA/EN) into a controlled taxonomy after crawl (no schema change required for reporting).
- Add a post-crawl dedupe report for same-name multi place_id clusters before analytics.
- Build an official Tipax branch list scraper/compare job (read-only) to measure true network coverage.
- Prioritize manual verification queue for missing phone/coords and zero-review high-claim branches.

## 8. Readiness for next courier company

Readiness for the next courier company: **CONDITIONAL GO**. Pipeline/ops completion is strong (crawler completion 100.0% on Tipax Maps tasks; DQ overall 85.7/100), but Google Maps discovery currently captures only a minority of Tipax's official network (~27.6%). Safe to run the same collector for the next courier **for Maps-visible locations**, while tracking Network Coverage separately and not equating it to Crawler Completion. Block treating analytics as full-network truth until coverage improves or an official directory compare exists.

## 9. Top 50 branches by collected reviews

| Rank | Branch | City | Province | Collected | Claimed | Rating |
|-----:|--------|------|----------|----------:|--------:|-------:|
| 1 | TIHUB | Tehran | Tehran | 10 | 39 | 2.5 |
| 2 | Tipax |  | North Khorasan | 10 | 30 | 3.4 |
| 3 | تیپاکس شعبه 4 | 58J3+Q8R نصر 1 | Bandar Abbas | 10 | 10 | 1.4 |
| 4 | تیپاکس شعبه کشاورز | Isfahan | Isfahan | 10 | 14 | 1.3 |
| 5 | سالن سورتینگ تیپاکس ( تی هاب ) | Isfahan | Isfahan | 10 | 40 | 1.7 |
| 6 | تیپاکس شعبه ملاصدرا |  | Fars | 10 | 15 | 3.0 |
| 7 | تیپاکس قم|شعبه مرکزی |  | Qom | 10 | 60 | 2.1 |
| 8 | نمایندگی تیپاکس رهنان | Isfahan | Isfahan | 10 | 16 | 2.3 |
| 9 | تیپاکس شعبه آرژانتین | Tehran | Tehran | 10 | 22 | 2.3 |
| 10 | تیپاکس نمایندگی فیض اصفهان | روبروی مسجد رکن الملک، | Feiz St | 10 | 67 | 2.8 |
| 11 | نمایندگی تیپاکس شیراز شهرک صنعتی |  | Fars | 10 | 12 | 2.2 |
| 12 | تیپاکس آریا | Isfahan | Isfahan | 10 | 10 | 4.1 |
| 13 | نمایندگی تیپاکس آتشگاه اصفهان | Isfahan | Isfahan | 10 | 35 | 2.6 |
| 14 | نمایندگی تیپاکس نازی آباد | Tehran | Tehran | 10 | 26 | 3.8 |
| 15 | تیپاکس گلستان |  | Golestan | 10 | 29 | 2.9 |
| 16 | نمایندگی تیپاکس شیراز پاسارگاد |  | Fars | 10 | 34 | 2.8 |
| 17 | TIPAX | Isfahan | Isfahan | 10 | 41 | 2.2 |
| 18 | تیپاکس شعبه نورآباد |  | Fars | 10 | 20 | 4.6 |
| 19 | نمایندگی تیپاکس قرچک | Tehran | Tehran | 10 | 57 | 2.5 |
| 20 | تیپاکس شعبه ۱ نجف آباد | Najafabad | Riazi St، روبه روی حلال احمر | 10 | 25 | 2.6 |
| 21 | تیپاکس آمل ۱۷شهریور - Tipax Amol Branch | Amol | ده متری اول | 10 | 21 | 3.5 |
| 22 | تیپاکس ملک‌شهر | Isfahan | Isfahan | 10 | 18 | 3.4 |
| 23 | نمایندگی تیپاکس کاشان امیرکبیر | Isfahan | Isfahan | 10 | 29 | 2.3 |
| 24 | تیپاکس فاطمی | Tehran | Tehran | 10 | 43 | 4.1 |
| 25 | تیپاکس عباس آباد | Tehran | Tehran | 10 | 18 | 3.1 |
| 26 | نمایندگی تیپاکس افسریه | Tehran | Tehran | 10 | 15 | 3.1 |
| 27 | نمایندگی تیپاکس حکیمیه | Tehran | Tehran | 10 | 21 | 3.7 |
| 28 | نمایندگی تیپاکس دهکده المپیک | دهکده المپیک خیابان ساحل | خیابان ۴۵، Iran | 10 | 12 | 3.0 |
| 29 | نمایندگی تیپاکس چهاردانگه | Tehran | Tehran | 10 | 28 | 3.8 |
| 30 | نمایندگی تیپاکس مشیریه | تهران | تهران | 10 | 25 | 2.0 |
| 31 | نمایندگی تیپاکس راه آهن | Tehran | Tehran | 10 | 11 | 2.5 |
| 32 | نمایندگی تیپاکس واوان تهران | Tehran | Tehran | 10 | 14 | 2.2 |
| 33 | تیپاکس مهرشهر | Tehran | Tehran | 10 | 57 | 3.2 |
| 34 | نمایندگی تیپاکس نظرآباد |  | Alborz | 10 | 20 | 2.4 |
| 35 | تیپاکس کیانمهر | Karaj | Alborz | 10 | 21 | 3.8 |
| 36 | تیپاکس مهستان |  | Alborz | 10 | 23 | 2.7 |
| 37 | تیپاکس هشتگرد |  | Alborz | 10 | 13 | 2.5 |
| 38 | Tayeb -Shams Abadi- Taleghani | Isfahan | Isfahan | 10 | 11 | 2.6 |
| 39 | نمایندگی تیپاکس فلاورجان | اصفهان | اصفهان | 10 | 23 | 3.3 |
| 40 | Tipax Central Office(انبار مرکزی شیراز) |  | Fars | 10 | 19 | 1.7 |
| 41 | دفتر تیپاکس شعبه نصر |  | Fars | 10 | 11 | 1.7 |
| 42 | دفتر تیپاکس کازرون |  | فارس | 10 | 13 | 2.4 |
| 43 | نمایندگی تیپاکس فسا سرو |  | Fars | 10 | 12 | 5.0 |
| 44 | تیپاکس شعبه جهرم |  | Fars | 10 | 18 | 4.1 |
| 45 | marvdasht tipax post office |  | Fars | 10 | 15 | 2.8 |
| 46 | نمایندگی مشهد فجر تیپاکس |  | Razavi Khorasan | 10 | 13 | 3.3 |
| 47 | Tipax Misaq |  | Fars | 10 | 22 | 2.4 |
| 48 | Tipax hemmat |  | Razavi Khorasan | 10 | 31 | 2.5 |
| 49 | تیپاکس شعبه پیروزی رضاشهر | Mashhad | Razavi Khorasan | 10 | 10 | 1.0 |
| 50 | تیپاکس طرقبه و شاندیز | طرقبه، طرقبه بعد از پمپ بنزین، امام خمینی ۵، قطعه سوم، | Iran | 10 | 16 | 3.4 |

## 10. Artifacts

- `docs/data_quality_report.md` (this file)
- `docs/branch_validation.csv`
- `docs/province_summary.csv`
- `docs/duplicate_report.csv`
- `docs/top50_branches_by_reviews.csv`
- `docs/manual_verification_queue.csv`

