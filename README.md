# Horse Racing Data Collector

سیستم جمع‌آوری داده مسابقات اسب‌دوانی — **فقط Collector** (بدون ML، پیش‌بینی یا تحلیل آماری).

## تکنولوژی

- Python 3.12
- Playwright
- BeautifulSoup
- PostgreSQL + SQLAlchemy
- Pydantic
- Loguru
- Typer CLI

## معماری

کد اپلیکیشن فقط به اینترفیس `DataSource` وابسته است:

- `collect_race()`
- `collect_horse()`
- `collect_horse_history()`
- `collect_race_list()`

پیاده‌سازی فعلی: `asbdavani` (سایت asbdavani.app). منابع دیگر بعداً قابل اضافه‌اند.

## نصب

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

## استفاده

```bash
python main.py collect --url "https://asbdavani.app/racecards/<WEEK_ID>?round=1"
```

خروجی در پوشه `output/`:

- `Race.json` — اطلاعات مسابقه + تمام اسب‌ها
- `HorseHistory.json` — تاریخچه مسابقات هر اسب (در صورت وجود لینک پروفایل)

گزینه‌ها:

```bash
python main.py collect --url "RACE_URL" --output output/run1 --skip-history
python main.py datasources
```

## ساختار

```
src/
  datasources/     # DataSource interface + registry
  asbdavani/       # پیاده‌سازی asbdavani.app
  browser/         # Playwright client
  models/          # Pydantic models
  database/        # Data Warehouse (raw_* + feat_*)
  pipelines/       # Feature pipelines (Raw → Features)
  collectors/      # orchestration
  parsers/         # HTML / RSC helpers
  utils/           # settings, logging, retry, json
docs/
  data_warehouse.md
tests/
main.py
```

## کراولر انبوه (Sprint 3)

دامنه پیش‌فرض فقط سه میدان: **گنبدکاووس، آق قلا، بندرترکمن**  
(`CRAWL_ALLOWED_RACECOURSES` — بدون کراول سراسری).

```bash
python main.py crawler discover
python main.py crawler run --workers 4
python main.py crawler dashboard
python main.py crawler daily-report
```

جزئیات: [`docs/crawler.md`](docs/crawler.md)

## Prediction HTTP API (freeze-backed)

Read-only HTTP layer over the **existing** prediction-foundation baselines.
Uses `baseline_eval.rank_race` unchanged. **Score is not probability** — responses always set `"probability": null`.

Dataset freeze: **`pf-v1.0.0-20260808`**. ML gate: **`DO_NOT_TRAIN_YET`**.

### Start

```bash
pip install -r requirements.txt
# Production: restore observations.jsonl.gz matching freeze sha256, then:
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs: http://127.0.0.1:8000/docs

Local smoke without the full freeze file (fixture only):

```bash
PREDICTION_DATASET_PATH=tests/fixtures/prediction_api/observations_fixture.jsonl.gz \
PREDICTION_VERIFY_FREEZE=false \
uvicorn src.api.main:app --port 8000
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + dataset version |
| GET | `/races/{race_id}` | Race + horses from freeze observations |
| GET | `/races/{race_id}/prediction?baseline=A` | Baseline ranking (`A`/`B`/`C`/`D`) |
| GET | `/horses/{horse_id}` | Freeze-backed horse analysis |

### Example

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/races/636/prediction | jq '.prediction[0]'
```

Example prediction item:

```json
{
  "rank": 1,
  "horse_id": 3446,
  "horse_name": null,
  "score": 62.1,
  "probability": null,
  "evidence": [{"metric": "career_avg_finish", "value": 4.2}],
  "warnings": []
}
```

`horse_name` is null when the freeze observations omit display names (ids only).

### Score vs probability

- **score**: baseline ranking strength from existing scorers A–D  
- **probability**: always `null` in this API — baselines do not emit calibrated probabilities; do not treat score as a percent chance to win

See also: `docs/PREDICTION_API_BLOCKER.md` (historical blockers) and `docs/baseline_evaluation.md`.
