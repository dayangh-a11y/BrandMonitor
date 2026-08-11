# Horse Racing Prediction Lab (Dashboard)

Internal Persian RTL dashboard for testing the existing Prediction API.

## Setup

```bash
cd frontend
cp .env.example .env
npm install
```

For local development set in `.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_BASE_PATH=/
```

## Run

```bash
npm run dev
```

Open http://127.0.0.1:3000 (Vite dev server uses port 3000 to match API CORS defaults).

## Build

```bash
npm run build
```

GitHub Pages build uses `VITE_BASE_PATH=/BrandMonitor/` (see `.github/workflows/deploy-dashboard.yml`).

## Test

```bash
npm test
```

## Architecture

```
WEB DASHBOARD → EXISTING API → EXISTING SERVICES → PREDICTION ENGINE
```

The dashboard only collects input, calls the API, and displays responses. No prediction logic runs in the browser.

## API endpoints used

- `GET /health`
- `GET /race-program/upcoming`
- `GET /race-program/meetings/{meeting_id}`
- `GET /races/{race_id}/prediction`
- `GET /races/{race_id}/compare`
- `GET /race-program/five-parreh`
- `GET /race-program/five-parreh/{event_id}`
- `POST /five-parreh/combinations`
- `GET /horses/search`
- `GET /horses/{horse_id}`
