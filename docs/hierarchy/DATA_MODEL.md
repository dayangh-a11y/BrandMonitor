# مدل مفهومی رسمی مسابقات

**وضعیت:** تثبیت‌شده — هر Heat هرگز Race Day نیست.

گزارش‌ها و Coverageهایی که قبلاً `wh_races` / «Race» را برابر Heat گرفته و آن را Race Day یا روز مسابقه شمرده‌اند **نامعتبر (INVALID)** هستند و باید از نو با این مدل محاسبه شوند.

تا پایان این اصلاح: هیچ Coverage جدیدی اعلام نمی‌شود، Enrichment انجام نمی‌شود، و درصد کامل بودن دیتابیس گزارش نمی‌شود.

---

## سلسله‌مراتب

```text
Race Week
  → Race Day
    → Heat  (Individual Race)
      → Result  (Horse Performance)
        → Horse
```

---

## ۱) فیلدهای واقعی دیتابیس (قبل از Rebuild)

| سطح | جدول | فیلدهای موجود برای تشخیص | شناسه پایدار؟ |
| --- | --- | --- | --- |
| Race Week | *(جدول نداشت)* | از `wh_races.source_url` → `/racecards/{weekId}` | بله — `weekId` منبع |
| Race Day | *(جدول نداشت)* | `wh_races.race_date` + `racecourse_code` / `track` + week از URL | خیر — باید بازسازی شود |
| Heat | `wh_races` | `id`, `source`+`source_race_id`, `race_number`, `source_url` | بله — ترجیحاً `source_race_id` حرارت |
| Result | `wh_race_results` | `id`, FK `race_id` → Heat، `horse_id`, `number`, finish/time/… | بله — PK / (race, horse, number) |
| Horse | `wh_horses` | `id`, `source`+`source_horse_id`, `name` | بله |

نکات مهم استخراج فعلی:

- `race_date` از `week.date` در payload منبع می‌آید (سطح هفته)، نه تاریخ جداگانهٔ هر Heat.
- `source_race_id` ترجیحاً `race_raw.id` است؛ fallback قدیمی به `week_id` خام **اشتباه** بود و Heatها را یکی می‌کرد — اصلاح شد به `{week_id}|round={N}`.

---

## ۲) شناسه‌های قطعی پس از Rebuild (بدون حدس)

| سطح | شناسه | فرمول | اگر ناقص باشد |
| --- | --- | --- | --- |
| Race Week | `race_week_id` | همان `weekId` از URL | لینک هفته = NULL (ساخته نمی‌شود) |
| Race Day | `race_day_id` | `{YYYY-MM-DD}\|{racecourse_code}\|{week_id}` | بدون تاریخ یا مکان → NULL؛ بدون week → `{date}\|{code}` |
| Heat | `heat_key` | `source_race_id` اگر ≠ week_id؛ وگرنه `{week_id}\|round={N}` | NULL — UUID جعلی ساخته نمی‌شود |
| Result | `wh_race_results.id` | PK موجود | — |
| Horse | `wh_horses.id` | PK / source horse id | — |

جداول مادّی‌شده:

- `wh_race_weeks`
- `wh_race_days`
- `wh_heat_hierarchy`
- ستون‌های کمکی روی `wh_races`: `week_id`, `race_day_id`, `heat_key`

---

## ۳) اتصال هر رکورد به سطح بالاتر

### Heat → Race Day

```text
wh_races.race_day_id
  = derive(race_date, racecourse_code, week_id_from(source_url))
```

Heat با `race_day_id` به دقیقاً یک Race Day وصل می‌شود. شمارش Race Day = `COUNT(DISTINCT race_day_id)` نه `COUNT(wh_races)`.

### Race Day → Race Week

```text
wh_race_days.race_week_id = week_id استخراج‌شده از source_url حرارت‌های آن روز
```

یک Race Week می‌تواند چند Race Day داشته باشد (چند تاریخ تقویمی زیر یک هفته رسمی).

### Result → Heat

```text
wh_race_results.race_id → wh_races.id  (= Heat)
```

### Result → Horse

```text
wh_race_results.horse_id → wh_horses.id
```

---

## ۴) بازمحاسبه آمار

```bash
export DATABASE_URL=sqlite:////workspace/output/historical/horse_racing.db
python scripts/rebuild_race_hierarchy.py
```

خروجی‌ها:

- `docs/hierarchy/hierarchy_stats.json`
- `docs/hierarchy/hierarchy_stats.md`
- `docs/hierarchy/race_days.csv` — برای هر Race Day: تاریخ شمسی، میلادی، شهر، Race Week، تعداد Heat / Result / Horse یکتا

آمار حداقل:

- کل DB: Race Weeks / Race Days / Heats / Horses / Results
- به ازای هر سال شمسی: همان پنج متریک
- به ازای هر Race Day: جزئیات بالا

---

## ۵) INVALID — گزارش‌های قبلی

موارد زیر تا بازمحاسبه با این مدل **نامعتبر** اعلام می‌شوند:

- هر شمارش «Race» که برابر `COUNT(wh_races)` بوده و به‌عنوان روز/هفته تفسیر شده
- `docs/collection/FINAL.md` / `final.json` (789 races به‌معنای Heat)
- `docs/VALIDATION_REPORT.md` و validation ۱۰۰تایی وقتی «race» = Heat بدون تفکیک Day
- خلاصه‌های Coverage مبتنی بر تعریف Race=Heat
- هر artifact قبلی با برچسب Race Day = تعداد Heat

پس از اجرای موفق `rebuild_race_hierarchy.py` روی warehouse زنده، فقط خروجی‌های `docs/hierarchy/*` مرجع آمار سلسله‌مراتبی هستند.
