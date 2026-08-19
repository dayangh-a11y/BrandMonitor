# Data Warehouse Design

قبل از جمع‌آوری انبوه، داده‌ها در دو لایه جدا نگه داشته می‌شوند.

## اصل جداسازی

| لایه | پیشوند جداول | محتوا | نحوه پر شدن |
|------|--------------|--------|-------------|
| **Raw** | `raw_*` | حقایق جمع‌آوری‌شده از منبع | Collector / ingest |
| **Features** | `feat_*` | متریک‌های مشتق‌شده | فقط Feature Pipeline |

- هیچ Featureای داخل جداول Raw ذخیره نمی‌شود.
- همه Featureها از Raw قابل محاسبه مجدد و به‌روزرسانی‌اند.
- Collector با `--persist` فقط Raw را می‌نویسد؛ Features دست‌نخورده می‌مانند تا `features build` اجرا شود.

```
Datasource → Collector → JSON files
                      ↘ raw_*  ──(pipelines)──▶ feat_*
```

## Raw tables

- `raw_ingest_runs` — لاگ هر اجرای جمع‌آوری
- `raw_horses` — بعد اسب (شناسه منبع، نام، جنسیت، تاریخ تولد، پدر/مادر، URL)
- `raw_races` — مشخصات مسابقه + `payload_json` کامل
- `raw_race_entries` — ردیف اسب در کارت/نتیجه (وزن، چابک، مربی، رتبه منبع، مقام، زمان، فاصله، ضریب…)
- `raw_horse_starts` — تاریخچه استارت‌های پروفایل اسب

**نکته:** فیلدهایی مثل `source_rating`، `finish_position`، `time_raw` حقایق منبع‌اند، نه Feature مهندسی‌شده.  
سن محاسبه‌شده توسط Collector فقط داخل `payload_json` نگه داشته می‌شود و ستون Raw جدا ندارد.

## Features tables

- `feat_pipeline_runs` — حسابرسی اجرای Pipeline
- `feat_horse_career` — starts / wins / places / win_rate / avg_finish / …
- `feat_horse_form` — فرم پنج استارت اخیر
- `feat_horse_distance` — عملکرد بر اساس مسافت
- `feat_jockey_stats` / `feat_trainer_stats` — آمار افراد

هر ردیف Feature به `pipeline_run_id` و `computed_at` وصل است.

## Feature Pipelines

اینترفیس: `src/pipelines/base.py` → `FeaturePipeline.compute(session, pipeline_run_id)`

ثبت‌شده‌ها:

- `horse_career`
- `horse_form`
- `horse_distance`
- `jockey_stats`
- `trainer_stats`

Pipelineها فقط از Raw می‌خوانند و فقط در `feat_*` می‌نویسند (معمولاً delete + rebuild برای idempotency).

## CLI

```bash
# ایجاد جداول warehouse
python main.py init-db

# جمع‌آوری + ذخیره Raw
python main.py collect --url "RACE_URL" --persist

# لیست / ساخت Features
python main.py features list
python main.py features build
python main.py features build --pipeline horse_career
```

## قوانین توسعه

1. ستون جدید منبع → جدول `raw_*` (یا `payload_json`).
2. متریک مشتق / تجمیعی → جدول `feat_*` + Pipeline جدید یا به‌روز.
3. هرگز Feature را در ingest مسیر Collector ننویسید.
4. Pipeline باید قابل اجرای مجدد باشد بدون وابستگی به وضعیت قبلی Features.
