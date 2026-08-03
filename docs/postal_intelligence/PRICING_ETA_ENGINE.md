# Pricing & ETA Engine

Unified, carrier-agnostic quoting for BrandMonitor.

## Design rules

- **No hardcoded carriers** in the engine — providers self-register.
- **One new adapter file** = one future carrier (`postal/pricing/adapters/<slug>.py`).
- **Identical output structure** for every provider.
- **Never invent** prices/ETAs — unavailable providers report `available=false` with a clear `message`.

## Canonical I/O

**Input (`QuoteRequest`)**

- Origin / Destination (`city_name`, `city_code`, `lat`/`lng`, …)
- Weight (`weight_kg`)
- Dimensions (`length_cm`, `width_cm`, `height_cm`)
- Package type
- COD (bool)
- Insurance (bool)
- Optional `declared_value`

**Output (`QuoteResult.to_public_dict()`)**

| Field | Meaning |
|-------|---------|
| `company` | Carrier display name |
| `price` | Numeric price or `null` |
| `eta` | Human ETA string or `null` |
| `currency` | e.g. `IRR` / `IRT` or `null` |
| `confidence` | 0–1 evidence grade for this quote |
| `data_source` | Upstream label |
| `last_updated` | ISO timestamp |
| + `available`, `status`, `message` | Explicit availability |

## Built-in adapters

| Slug | Source | Credentials |
|------|--------|-------------|
| `tipax` | eTipax OM `/api/OM/v3/Pricing` | `TIPAX_OM_TOKEN` or username/password |
| `chapar` | CDN quote + time-estimate APIs | none for website surface |
| `mahex` | `website/api/web/v1/rate-calculation` | none for website surface; city codes required |
| `alopeyk` | `/api/v2/orders/price/calc` | `ALOPEYK_API_TOKEN` (+ lat/lng) |
| `post` | Merchant/gateway URL | `IRAN_POST_PRICE_URL` + token/shop id |

## CLI

```bash
PYTHONPATH=. python3 scripts/compare_pricing.py \
  --origin Tehran --destination Isfahan \
  --weight-kg 1 --length-cm 20 --width-cm 15 --height-cm 10 \
  --declared-value 500000 \
  --json-out /tmp/pricing_compare.json
```

## API

Requires `X-API-Token`.

- `GET /postal/pricing/providers`
- `POST /postal/pricing/compare`
- `POST /postal/pricing/quote/{slug}`

Example body:

```json
{
  "origin": {"city_name": "Tehran", "city_code": "1", "lat": 35.7, "lng": 51.4},
  "destination": {"city_name": "Isfahan", "city_code": "2", "lat": 32.6, "lng": 51.6},
  "weight_kg": 1,
  "dimensions": {"length_cm": 20, "width_cm": 15, "height_cm": 10},
  "package_type": "parcel",
  "cod": false,
  "insurance": false,
  "declared_value": 500000
}
```

## Adding a future provider

1. Create `postal/pricing/adapters/my_carrier.py`.
2. Implement `slug`, `company`, `data_source`, `quote(request) -> QuoteResult`.
3. Call `register_provider(MyProvider())` at module bottom.
4. Done — registry auto-discovers the module; engine/API/CLI pick it up with no core edits.
