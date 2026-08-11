# والدین اسب مسابقه باارزش — داشبورد پیش‌بینی

Persian RTL web dashboard for horse-racing prediction analytics.

Architecture:

```
Frontend (static)  →  FastAPI Prediction API  →  existing services / engine
```

The frontend never computes scores, rankings, or Five-Parreh combinations.

## Local development

```bash
cd frontend
cp .env.example .env
# set:
# VITE_API_BASE_URL=http://127.0.0.1:8000
# VITE_BASE_PATH=/
npm install
npm run dev
```

API (fixture mode):

```bash
python3 tests/fixtures/race_program/build.py

PREDICTION_DATASET_PATH=tests/fixtures/prediction_api/observations_fixture.jsonl.gz \
PREDICTION_VERIFY_FREEZE=false \
HORSE_NAME_INDEX_PATH=tests/fixtures/prediction_api/horse_names.json \
RACE_PROGRAM_PATH=tests/fixtures/race_program/program_fixture.json \
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

## Scripts

```bash
npm run dev      # Vite on http://127.0.0.1:3000
npm run build    # production build → dist/
npm run preview  # preview production build
npm test         # Vitest
```

## Production configuration

Required build-time env:

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Absolute API origin, e.g. `https://api.example.com` (no trailing slash) |
| `VITE_BASE_PATH` | Static asset base (`/` for Vercel; `/BrandMonitor/` for GitHub Pages) |

`VITE_API_BASE_URL` must be set for production builds. Localhost is only used as a **dev** fallback.

### Recommended hosting split

- **Frontend:** Vercel (or Netlify / Cloudflare Pages / GitHub Pages)
- **Backend:** Render / Railway / Fly.io (FastAPI + uvicorn)

GitHub Pages hosts the frontend only — not FastAPI.

### CORS

Configure backend `API_CORS_ORIGINS` to include the frontend origin, e.g.:

```env
API_CORS_ORIGINS=https://your-frontend.vercel.app
```

### Render (FastAPI backend — Demo)

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
./scripts/render_start.sh
```

Equivalent:

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
```

Use `.env.demo.example` for DEMO/TEST fixture env vars (not real production race data).
Materialize near-future program times before Demo deploy:

```bash
python3 tests/fixtures/race_program/build.py
```

### Vercel

1. Root directory: `frontend`
2. Build command: `npm run build`
3. Output: `dist`
4. Env: `VITE_API_BASE_URL`, `VITE_BASE_PATH=/`

### GitHub Pages

Workflow: `.github/workflows/deploy-dashboard.yml`

Set `VITE_API_BASE_URL` to the public API URL before relying on Pages for anything beyond static hosting.

## Product navigation

1. داشبورد
2. پیش‌بینی کورس
3. پنج‌پره
4. اسب مقابل اسب
5. تحلیل اسب
6. API / وضعیت سیستم

Raw API payloads are available only under **وضعیت سیستم** (advanced).
