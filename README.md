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
# Production: restore the canonical frozen file matching freeze sha256, then:
#   data/prediction_foundation/datasets/observations.jsonl.gz
# Startup fails clearly if that file is missing (no fixture fallback).
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs: http://127.0.0.1:8000/docs

**Fixture mode** (tests / local smoke only — never production):

```bash
PREDICTION_DATASET_PATH=tests/fixtures/prediction_api/observations_fixture.jsonl.gz \
PREDICTION_VERIFY_FREEZE=false \
uvicorn src.api.main:app --port 8000
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + dataset version |
| GET | `/races` | List freeze-backed races (metadata) |
| GET | `/races/{race_id}` | Race + horses from freeze observations |
| GET | `/races/{race_id}/prediction?baseline=A` | Baseline ranking (`A`/`B`/`C`/`D`) |
| GET | `/horses/search?name=` | Search horses by display name |
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

## Five-Parreh (Phase 1)

Cartesian-product ticket builder for **exactly five consecutive races**.
Domain: `src/five_parreh/`. Docs: [`docs/five_parreh.md`](docs/five_parreh.md).

This phase does **not** rank, score, or assign probabilities to combinations.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/five-parreh/combinations` | Build combinations + cost from selections |

```bash
curl -s http://127.0.0.1:8000/five-parreh/combinations \
  -H 'Content-Type: application/json' \
  -d '{"races":[
    {"race_id":"R1","horses":["A","B","C"]},
    {"race_id":"R2","horses":["D","E","F"]},
    {"race_id":"R3","horses":["G","H","I"]},
    {"race_id":"R4","horses":["J","K","L"]},
    {"race_id":"R5","horses":["M","N","O"]}
  ],"price_per_combination":10000}'
```

## Telegram Bot (thin UI client)

Architecture: **Telegram UI → HTTP API → formatters → Telegram**.  
The bot contains **no** scoring, `rank_race`, ML, pedigree, or Five-Parreh Cartesian-product logic.

### Setup

```bash
pip install -r requirements.txt
# Copy .env.example → .env and set TELEGRAM_BOT_TOKEN (never commit the real token)
```

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather (required) |
| `API_BASE_URL` | Prediction API base (default `http://localhost:8000`) |
| `REQUEST_TIMEOUT_SECONDS` | HTTP timeout (default 10) |
| `TELEGRAM_DEFAULT_PRICE_PER_COMBINATION` | Display/cost default for پنج‌پره (default 10000) |

### Run (API and bot are independent)

```bash
# Terminal 1 — API (fixture mode for local/dev without production freeze file)
PREDICTION_DATASET_PATH=tests/fixtures/prediction_api/observations_fixture.jsonl.gz \
PREDICTION_VERIFY_FREEZE=false \
uvicorn src.api.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — Telegram bot
export TELEGRAM_BOT_TOKEN=...   # from BotFather
export API_BASE_URL=http://127.0.0.1:8000
python -m src.telegram_bot.bot
```

### Commands

| Command | Action |
|---------|--------|
| `/start` | Welcome + inline menu |
| `/help` | Short Persian help |
| `/races` | Lists races via `GET /races` |
| `/predict [id]` | Calls `GET /races/{id}/prediction` — shows **Score**, never invents probability |
| `/horse` | Ask for **horse name** → `GET /horses/search` → user picks a name button → bot calls `GET /horses/{id}` internally |
| `/fiveparreh` | Future Five-Parreh **events** only → predict each designated race → combinations |

### Five-Parreh bot flow (future events)

1. List **declared future** Five-Parreh events (`FIVE_PARREH_EVENTS_PATH` JSON) — never inferred from freeze `race_id`s  
2. User selects one event (exactly 5 designated races, all still in the future)  
3. For each race: show prediction ranks → multi-select horses  
4. Confirm count/cost → `POST /five-parreh/combinations`  

See [`docs/five_parreh_events.md`](docs/five_parreh_events.md).

### Production dataset blocker

Canonical `data/prediction_foundation/datasets/observations.jsonl.gz` is still missing.
Production API startup fails until it is restored. The bot must not bypass this; use fixture API mode only for development/tests.

### Bot tests

```bash
python -m pytest -q tests/test_telegram_bot.py
```

Mocks HTTP — no real Telegram token or production dataset required.
