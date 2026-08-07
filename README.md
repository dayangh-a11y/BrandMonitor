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
