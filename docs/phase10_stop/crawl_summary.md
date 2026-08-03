# Tipax Nationwide Discovery — Graceful Stop Report

Generated: `2026-08-03T10:44:40.800117+00:00`

## Stop status

**Graceful live stop could not be completed from this agent.**

The Phase 10 discovery process (`pid 39142`, `scripts/discover_tipax_nationwide.py`) was last observed on cloud agent `bc-019fc20e-15fc-71af-b04a-0697ab52a9ca`, not on this VM. That engine only persists branches after `engine.run()` finishes and has no stop-file/SIGINT flush path. Per instructions, crawler logic was not modified.

| Action | Result |
|---|---|
| Flush pending writes to DB | **Not possible remotely** — last poll still showed DB `369` while in-memory unique was `829` |
| Save crawl state | **Done** → `crawl_state.json`, `resume_checkpoint.json` |
| Generate final progress reports | **Done** (this file + metrics/CSVs) |
| Resume checkpoint | **Done** (partial completed-query set recovered from transcript) |

## Summary metrics

| Metric | Value |
|---|---:|
| Total queries executed | **461** |
| Unique branches discovered (in-memory, last poll) | **829** |
| Unique branches persisted in DB | **369** |
| New vs baseline (in-memory estimate) | **460** |
| Total reviews collected (this discovery run) | **0** (discovery-only) |
| Total reviews in DB (prior crawls) | **1804** |
| Duplicate rate (recovered sample) | **45.5%** (498/1095 on 85 recovered lines) |
| Failed queries | **0** |
| Skipped queries (estimate) | **~184** (duplicate district re-queue; not logged exactly) |
| District expansions | **16** |
| Average processing speed | **1.61 queries/min** |
| Elapsed time | **4:46:07.560000** (process etime max `04:26:46`) |
| Last log timestamp | `2026-08-03 09:54:24,015` |

## Branches by province (persisted DB)

Source: Phase 9 `province_summary.csv` (DB unchanged during Phase 10 discovery).

| Province | FA | Branches | Status |
|---|---|---:|---|
| Tehran | تهران | 50 | ok |
| Alborz | البرز | 8 | ok |
| Isfahan | اصفهان | 50 | ok |
| Fars | فارس | 32 | ok |
| Razavi Khorasan | خراسان رضوی | 17 | ok |
| East Azerbaijan | آذربایجان شرقی | 13 | ok |
| West Azerbaijan | آذربایجان غربی | 12 | ok |
| Ardabil | اردبیل | 0 | no_branches |
| Yazd | یزد | 10 | ok |
| Kerman | کرمان | 7 | ok |
| Kermanshah | کرمانشاه | 0 | no_branches |
| Hamadan | همدان | 3 | ok |
| Qazvin | قزوین | 1 | unusually_low |
| Qom | قم | 2 | unusually_low |
| Markazi | مرکزی | 2 | unusually_low |
| Lorestan | لرستان | 7 | ok |
| Khuzestan | خوزستان | 25 | ok |
| Bushehr | بوشهر | 2 | unusually_low |
| Hormozgan | هرمزگان | 16 | ok |
| Sistan and Baluchestan | سیستان و بلوچستان | 10 | ok |
| Kurdistan | کردستان | 6 | ok |
| Ilam | ایلام | 1 | unusually_low |
| Kohgiluyeh and Boyer-Ahmad | کهگیلویه و بویراحمد | 1 | unusually_low |
| Chaharmahal and Bakhtiari | چهارمحال و بختیاری | 5 | ok |
| Gilan | گیلان | 26 | ok |
| Mazandaran | مازندران | 21 | ok |
| Golestan | گلستان | 1 | unusually_low |
| Semnan | سمنان | 1 | unusually_low |
| Zanjan | زنجان | 1 | unusually_low |
| North Khorasan | خراسان شمالی | 3 | ok |
| South Khorasan | خراسان جنوبی | 2 | unusually_low |

## Top 50 branches by review count (persisted DB)

Discovery-only run did not collect reviews; table reflects prior crawl enrichment.

| Rank | Name | Province | Collected | Claimed |
|---:|---|---|---:|---:|
| 1 | TIHUB | Tehran | 10 | 39 |
| 2 | Tipax | North Khorasan | 10 | 30 |
| 3 | تیپاکس شعبه 4 | Bandar Abbas | 10 | 10 |
| 4 | تیپاکس شعبه کشاورز | Isfahan | 10 | 14 |
| 5 | سالن سورتینگ تیپاکس ( تی هاب ) | Isfahan | 10 | 40 |
| 6 | تیپاکس شعبه ملاصدرا | Fars | 10 | 15 |
| 7 | تیپاکس قم|شعبه مرکزی | Qom | 10 | 60 |
| 8 | نمایندگی تیپاکس رهنان | Isfahan | 10 | 16 |
| 9 | تیپاکس شعبه آرژانتین | Tehran | 10 | 22 |
| 10 | تیپاکس نمایندگی فیض اصفهان | Feiz St | 10 | 67 |
| 11 | نمایندگی تیپاکس شیراز شهرک صنعتی | Fars | 10 | 12 |
| 12 | تیپاکس آریا | Isfahan | 10 | 10 |
| 13 | نمایندگی تیپاکس آتشگاه اصفهان | Isfahan | 10 | 35 |
| 14 | نمایندگی تیپاکس نازی آباد | Tehran | 10 | 26 |
| 15 | تیپاکس گلستان | Golestan | 10 | 29 |
| 16 | نمایندگی تیپاکس شیراز پاسارگاد | Fars | 10 | 34 |
| 17 | TIPAX | Isfahan | 10 | 41 |
| 18 | تیپاکس شعبه نورآباد | Fars | 10 | 20 |
| 19 | نمایندگی تیپاکس قرچک | Tehran | 10 | 57 |
| 20 | تیپاکس شعبه ۱ نجف آباد | Riazi St، روبه روی حلال احمر | 10 | 25 |
| 21 | تیپاکس آمل ۱۷شهریور - Tipax Amol Branch | ده متری اول | 10 | 21 |
| 22 | تیپاکس ملک‌شهر | Isfahan | 10 | 18 |
| 23 | نمایندگی تیپاکس کاشان امیرکبیر | Isfahan | 10 | 29 |
| 24 | تیپاکس فاطمی | Tehran | 10 | 43 |
| 25 | تیپاکس عباس آباد | Tehran | 10 | 18 |
| 26 | نمایندگی تیپاکس افسریه | Tehran | 10 | 15 |
| 27 | نمایندگی تیپاکس حکیمیه | Tehran | 10 | 21 |
| 28 | نمایندگی تیپاکس دهکده المپیک | خیابان ۴۵، Iran | 10 | 12 |
| 29 | نمایندگی تیپاکس چهاردانگه | Tehran | 10 | 28 |
| 30 | نمایندگی تیپاکس مشیریه | تهران | 10 | 25 |
| 31 | نمایندگی تیپاکس راه آهن | Tehran | 10 | 11 |
| 32 | نمایندگی تیپاکس واوان تهران | Tehran | 10 | 14 |
| 33 | تیپاکس مهرشهر | Tehran | 10 | 57 |
| 34 | نمایندگی تیپاکس نظرآباد | Alborz | 10 | 20 |
| 35 | تیپاکس کیانمهر | Alborz | 10 | 21 |
| 36 | تیپاکس مهستان | Alborz | 10 | 23 |
| 37 | تیپاکس هشتگرد | Alborz | 10 | 13 |
| 38 | Tayeb -Shams Abadi- Taleghani | Isfahan | 10 | 11 |
| 39 | نمایندگی تیپاکس فلاورجان | اصفهان | 10 | 23 |
| 40 | Tipax Central Office(انبار مرکزی شیراز) | Fars | 10 | 19 |
| 41 | دفتر تیپاکس شعبه نصر | Fars | 10 | 11 |
| 42 | دفتر تیپاکس کازرون | فارس | 10 | 13 |
| 43 | نمایندگی تیپاکس فسا سرو | Fars | 10 | 12 |
| 44 | تیپاکس شعبه جهرم | Fars | 10 | 18 |
| 45 | marvdasht tipax post office | Fars | 10 | 15 |
| 46 | نمایندگی مشهد فجر تیپاکس | Razavi Khorasan | 10 | 13 |
| 47 | Tipax Misaq | Fars | 10 | 22 |
| 48 | Tipax hemmat | Razavi Khorasan | 10 | 31 |
| 49 | تیپاکس شعبه پیروزی رضاشهر | Razavi Khorasan | 10 | 10 |
| 50 | تیپاکس طرقبه و شاندیز | Iran | 10 | 16 |

## Provinces with weak coverage

- **Ardabil** (اردبیل): 0 branches — `no_branches`
- **Kermanshah** (کرمانشاه): 0 branches — `no_branches`
- **Qazvin** (قزوین): 1 branches — `unusually_low`
- **Qom** (قم): 2 branches — `unusually_low`
- **Markazi** (مرکزی): 2 branches — `unusually_low`
- **Bushehr** (بوشهر): 2 branches — `unusually_low`
- **Ilam** (ایلام): 1 branches — `unusually_low`
- **Kohgiluyeh and Boyer-Ahmad** (کهگیلویه و بویراحمد): 1 branches — `unusually_low`
- **Golestan** (گلستان): 1 branches — `unusually_low`
- **Semnan** (سمنان): 1 branches — `unusually_low`
- **Zanjan** (زنجان): 1 branches — `unusually_low`
- **South Khorasan** (خراسان جنوبی): 2 branches — `unusually_low`

## Failed queries

None observed (`discovery_query_failed` / Traceback greps empty across polls).

## Skipped queries

Engine silently skips duplicate query texts (executed_texts). Estimated skipped ≈ 184 from duplicate district re-expansions (184 queries re-added for cities already expanded). Exact skip count was not logged by the discovery process.

## Improvements that would most increase branch discovery next run

1. **Persist incrementally + support graceful stop** — Current engine keeps all uniques in memory and only upserts after full completion. Add periodic persist + SIGINT/stop-file handling so a plateau stop does not lose ~460 discovered branches (without changing Maps crawl parsers).
2. **Dedupe district expansion queue before append** — Alias threshold caused duplicate city re-expansions (e.g. Tehran +80 twice), inflating the queue with texts that are later skipped. Track queued texts, not only executed.
3. **Cap / prioritize district queries** — Late-phase district queries were mostly new=0. Prefer districts in weak provinces and stop expanding a city after N consecutive zero-new queries.
4. **Target zero/weak provinces with alternate brand strings** — Ardabil and Kermanshah stayed at 0 persisted branches. Try partner/agency names, Latin transliterations, nearby city hubs, and place-type filters beyond Tipax aliases.
5. **Resume from checkpointed completed query set** — Write completed query texts + discovered place_ids continuously so the next nationwide run skips finished work and only attacks remaining gaps.
6. **Enrich discovery cards with claimed review_count when available** — FAST_DISCOVER often yields 0 review_count on cards, understating coverage quality. Lightweight enrichment on new place_ids only would improve prioritization without full review scrape.

## Artifacts

- `docs/phase10_stop/crawl_summary.md`
- `docs/phase10_stop/crawl_metrics.json`
- `docs/phase10_stop/province_coverage.csv`
- `docs/phase10_stop/discovery_statistics.csv`
- `docs/phase10_stop/resume_checkpoint.json`
- `docs/phase10_stop/crawl_state.json`

## Operator follow-up on the live discovery agent

If the Phase 10 agent VM is still up, run there (does not change crawler logic):

```bash
# 1) Ask the process to exit only after current query if a wrapper exists; otherwise
#    wait for natural completion OR, as last resort after checkpointing logs:
kill -INT 39142   # prefer INT over KILL; engine may still lose in-memory uniques

# 2) Preserve evidence
cp -a /opt/cursor/artifacts/phase10_discovery /opt/cursor/artifacts/phase10_discovery_stopped_$(date -u +%Y%m%dT%H%M%SZ)
cp -a data/tipax_iran.db data/tipax_iran.stop_backup.db
```

Then merge the full `discovery_run.log` query list into `resume_checkpoint.json`.
