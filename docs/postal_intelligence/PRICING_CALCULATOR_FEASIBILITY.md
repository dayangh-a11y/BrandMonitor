# Official Shipping Price & Delivery-Time Calculators — Feasibility Report

**Product:** BrandMonitor Postal Intelligence  
**Scope:** Tipax, Chapar, Mahex, AloPeyk, Pishro, Iran Post  
**Date:** 2026-08-03  
**Status:** Investigation only — **no calculator integration implemented**  
**Constraint honored:** No CAPTCHA/auth bypass, no credential stuffing, no scraping of protected panels. Findings come from public HTML/JS, official docs, and benign public-endpoint observation.

---

## Executive summary

| Company | Public website calculator | Mechanism | Official partner API for quotes | BrandMonitor integration feasibility |
|---------|---------------------------|-----------|----------------------------------|--------------------------------------|
| **Tipax** | Yes (`/transit-cost-calculator`, `/transit-time-calculator`) | ASP.NET WebForms **server postback** (+ WCF helper for cities) | **Yes — eTipax OM API** (`/api/OM/v3/Pricing`) with account token | **High** via official API after commercial onboarding |
| **Chapar** | Yes (`/shipping-cost`, `/shipping-time`) | Next.js UI → **public CDN/API endpoints** | Partner shipment APIs exist (third-party clients); website quote endpoints appear publicly callable | **Medium–High** for time; **Medium** for price (undocumented website API; prefer contract) |
| **Mahex** | Yes (`/rate`) | Next.js UI → **server API** `website/api/web/v1/rate-calculation` | Business panel/webservice marketed; public developer docs not found | **Medium** — website API works as XHR target; needs ToS/partner confirmation + resilience |
| **AloPeyk** | App/web booking (site SSL issues in probe env) | N/A for static tariff | **Yes — documented** `POST /api/v2/orders/price/calc` (Bearer) | **High** via official API key |
| **Pishro** | No (site: “down for maintenance”) | None observed | None found | **None** until site/API returns |
| **Iran Post** | Public site often unreachable from probe env; tariffs published as **PDF rate books**; e-commerce merchants use **ecommerce.post.ir** / gateway APIs | SOAP/REST **merchant** services + static tariff tables | **Yes for contracted shops**; not a free anonymous public calculator API | **Medium** via merchant contract **or** curated PDF tariff snapshots |

**Recommendation:** Build a reusable **Pricing Provider** interface now, but implement only **officially contracted** adapters first (Tipax eTipax, AloPeyk, Iran Post e-commerce). Treat Chapar/Mahex website XHR surfaces as *observation candidates* until written permission / partner docs exist. Do **not** automate Tipax ASP.NET ViewState postbacks.

---

## Method

1. Loaded official company seeds from `config/official_companies.yaml`.
2. Fetched public marketing/calculator pages and Next.js / ASP.NET assets.
3. Static-analyzed public JS bundles for request URLs, parameters, and auth hooks.
4. Cross-checked official documentation (Tipax Academy / eTipax, AloPeyk docs).
5. Made only **non-abusive** probes (e.g. empty/dummy quote calls) to learn error/auth shape — never solved CAPTCHAs or used stolen tokens.
6. Separated **website calculator mechanism** from **official partner API**.

Artifacts from probing (local, not committed): `/tmp/calc_probe/*.json`.

---

## 1. Tipax (تیپاکس)

### 1.1 Website calculators

| Item | Detail |
|------|--------|
| Cost UI | https://tipaxco.com/transit-cost-calculator |
| Time UI | https://tipaxco.com/transit-time-calculator |
| Legacy `/price` | Redirects to **mobile login** (`default.aspx?tabid=518&ReturnPath=%2fprice`) — not a public anonymous tariff page |
| Stack | DNN / ASP.NET WebForms + Telerik controls |
| Mechanism | **Server-side endpoint (HTML postback)**. Calculation is **not** pure client-side JS. Submit uses `__VIEWSTATE`, `__VIEWSTATEGENERATOR`, `__RequestVerificationToken`, and control names under `Estimate*` |

**Observed cost form parameters (control names):**

| Parameter (UI) | Control / field |
|----------------|-----------------|
| Origin city | `_rcbStart` (+ ClientState) |
| Destination city | `_rcbEnd` |
| Service / type | `_rblType` (values observed: `1`, `4`, `2`) |
| Weight | `_txtWeight` |
| Declared value | `_txtPrice` |
| Packaging flag | `_rblPacking` |
| Packing type | `_rcbPackingType` |
| Dimensions | `_txtLenght`, `_txtWidth`, `_txtHeight` |
| Payment type | `_rcbPaymentType` |

**Time calculator:** origin/destination combos + map helper; references WCF:

`POST/GET` family under  
`https://tipaxco.com/desktopmodules/Tipax/service/TipaxService.svc/...`  
(e.g. `GetCityByProvince` returns **405** on bare GET — method-constrained SOAP/WCF service).

**Auth / controls:** Anti-forgery token + ViewState required for postback. Homepage estimate widget shows **CAPTCHA** signals. No anonymous stable JSON pricing API on the marketing site.

**Response format (website):** HTML fragment / full page after postback (not a documented JSON schema).

**Feasibility of scraping website calculator:** **Low / discouraged** — brittle ViewState, possible CAPTCHA, ToS risk, high maintenance.

### 1.2 Official partner API (recommended)

Documented by Tipax Academy / eTipax:

| Item | Detail |
|------|--------|
| Product | **ای‌تیپاکس (eTipax)** order-management API |
| Docs | https://academy.tipax.ir/education/api-ای‌تیپاکس/ and parameter guide |
| Test host (docs) | `https://omtestapi.tipax.ir` |
| Auth | Account login → **token** + **RefreshToken** (`/api/OM/v3/Account/token`, `/api/OM/v3/Account/RefreshToken`) — **credentials required** |
| Pricing | `POST /api/OM/v3/Pricing` |
| Min pricing | `POST /api/OM/v3/Pricing/Min` (origin/destination cities only) |
| With address book | `/api/OM/v3/Pricing/WithAddressId` |

**Required pricing parameters (from official parameter guide):**

- `origin.cityId`, `destination.cityId`
- `weight`, `packageValue`
- `length`, `width`, `height`
- `packingId`, `packageContentId`, `packType`
- `paymentType`, `pickupType`, `distributionType`
- `Serviced` (service codes: same-day ground, +1 day, +2 day, intercity express, international, intra-city express, …)
- optional: `discountCode`, `customerId`, `isUnusual`, COD-related fields

**Response:** JSON quote objects (amount breakdown via OM API — exact schema in Tipax partner docs after account access). Probe of `/Pricing` without auth returned **405** (method/auth gated), confirming it is not an open anonymous API.

**Delivery time:** Website time calculator is separate; OM order APIs expose service SLAs via `Serviced` rather than a standalone public ETA endpoint. Prefer contracted OM docs for ETA fields.

| Dimension | Rating |
|-----------|--------|
| Technical feasibility | **High** (official REST) |
| Maintenance complexity | **Medium** (token refresh, city IDs, service code catalog drift) |
| Legal / support posture | **Best path** — designed for integration |

---

## 2. Chapar (چاپار)

### 2.1 Website calculators

| Item | Detail |
|------|--------|
| Cost UI | https://www.chaparnet.com/shipping-cost |
| Time UI | https://www.chaparnet.com/shipping-time (also linked as `/time-estimate`) |
| Stack | Next.js App Router |
| Mechanism | **Client JS → server-side HTTP APIs** (not offline JS math) |

#### Price quote (observed in public bundle)

| Item | Detail |
|------|--------|
| Endpoint | `POST https://cdn.chaparnet.com/api/page/calculate-shipping-costs/request` |
| Request format | `multipart/form-data` **or** `application/x-www-form-urlencoded` (both accepted in probe) |
| Fields | `Origin`, `Destination`, `Weight`, `Value`, `Method`, `SenderCode`, `ReceiverCode`, `Cod` |
| Defaults in UI JS | `SenderCode=1000`, `ReceiverCode=1000`, `Cod=0` |
| Auth | HTTP client configured with optional `localStorage.token`; **dummy quote calls succeeded without a token** (business validation errors only) |
| Response (shape) | JSON: `{ success, message, data: { result, message, objects: { order: { price: { fld_Total_Cost, zone, … }, method_name, currency } } } }` |
| Probe result | With synthetic city ids `1/2`: `result=false`, message *«امکان جمع آوری از شهر مبدا وجود ندارد»* — endpoint live, validation enforced |

#### Delivery time (observed)

| Item | Detail |
|------|--------|
| Endpoint | `POST https://cdn.chaparnet.com/api/time-estimate` |
| Request | JSON `{"origin": <number>, "destination": <number>}` |
| Auth | None observed |
| Response example | `{"success":true,"data":{"result":true,"objects":[{"origin":1,"destination":2,"hour":48,"method":1},{"origin":1,"destination":2,"hour":24,"method":6}]}}` |

#### City list

| Item | Detail |
|------|--------|
| Endpoint (from JS) | `GET https://apigmlch.ir/v1/get_city` |
| Probe note | Hostname **did not resolve** from this research environment (DNS `-2`). Treat as **JS-observed**, verify from an Iran-routed network before depending on it. |

| Dimension | Rating |
|-----------|--------|
| Technical feasibility | **Medium–High** (simple HTTP) |
| Maintenance complexity | **Medium–High** — website API is **undocumented**; paths/fields can change with Next deploys; city-id scheme must be frozen |
| Official stance | Prefer **written Chapar partner API** for production. Website XHR is fine for demos only with rate limits + monitoring. |

---

## 3. Mahex (ماهکس)

### 3.1 Website calculator

| Item | Detail |
|------|--------|
| UI | https://mahex.com/rate (also embedded from home tabs) |
| Stack | Next.js |
| Mechanism | **Server-side API** called from browser |

**Endpoint (from public JS):**

```http
GET https://mahex.com/website/api/web/v1/rate-calculation
  ?shipperCityCode={code}
  &consigneeCityCode={code}
  &totalGrossWeight={kg}
  &totalDeclaredValue={amount}
  &totalLength={cm}
  &totalWidth={cm}
  &totalHeight={cm}
```

**Required UI parameters:**

- `shipperCityCode`, `consigneeCityCode` (Mahex city codes, e.g. `IR-…` labels in bundle)
- `totalWeight` (max **45 kg** validated in UI)
- `totalDeclaredValue`
- `totalLength`, `totalWidth`, `totalHeight`

**Response (from JS handling):** JSON including `totalAmount` (UI floors to integer display).

**Auth / controls:**

- Base API prefix `https://mahex.com/website/api/`
- Public bundle embeds a **reCAPTCHA site key** (`6LfaM0sr…`) for site workflows; rate-calculation probe with dummy codes returned HTTP **500** `UnknownException` JSON (not an explicit 401). Do **not** assume unauthenticated production use is permitted.
- Weight/size validation is client-enforced and likely rechecked server-side.

**Official developer portal:** Not found as a public OpenAPI site. Marketing copy references business panel / webservice after commercial signup.

| Dimension | Rating |
|-----------|--------|
| Technical feasibility | **Medium** |
| Maintenance complexity | **Medium–High** (undocumented query API, city code catalog, possible bot controls) |
| Recommended path | Partner agreement → stable API credentials; until then keep **curated price_index** only |

---

## 4. AloPeyk (الوپیک)

### 4.1 Website vs API

| Item | Detail |
|------|--------|
| Marketing site | `https://alopeyk.com` — TLS verification failed in this environment (certificate chain). Not used as primary evidence. |
| Official docs | https://docs.alopeyk.com/ |
| Mechanism | **Public documented REST API** (partner token). Pricing is **server-side**. |

### 4.2 Official price calculation

| Item | Detail |
|------|--------|
| Endpoint | `POST https://api.alopeyk.com/api/v2/orders/price/calc` (sandbox: `sandbox-api.alopeyk.com`) |
| Auth | **`Authorization: Bearer {token}`** + `X-Requested-With: XMLHttpRequest` |
| Request JSON | `transport_type`, `addresses[]` with `{type: origin\|destination, lat, lng}`, optional `has_return`, `cashed`, `optimize` |
| Response | Includes `price`, `distance`, `duration`, `price_with_return`, per-leg fields (see official PHP SDK samples; amounts in Toman in examples) |
| Batch | `POST /api/v2/orders/batch-price` (up to 15) |

**Delivery time:** Returned as `duration` (seconds) alongside price — not a separate postal SLA table. AloPeyk is **on-demand urban** logistics; compare carefully against intercity postal carriers in BrandMonitor scoring.

**Alonomic / parcel products:** Community MCP schemas mention `POST /business-service/api/v1/parcels/calc` for parcel dimensions/worth — confirm against current AloPeyk business docs before relying on it (not verified live in this probe).

| Dimension | Rating |
|-----------|--------|
| Technical feasibility | **High** |
| Maintenance complexity | **Low–Medium** (stable versioned API, token rotation) |
| Notes | Best-in-class official docs among supported set |

---

## 5. Pishro (پیشرو)

| Item | Detail |
|------|--------|
| Website | https://pishro.net → body: `down for maintenance` (~20 bytes) |
| Calculator | **None available** |
| API | **None found** |
| Feasibility | **Blocked** until official surface returns |

Keep curated `official_pricing.price_index` with **low confidence** and `calculator_status: unavailable`.

---

## 6. Iran Post (شرکت ملی پست)

### 6.1 Public website / calculator

| Item | Detail |
|------|--------|
| `post.ir` / `www.post.ir` / `tracking.post.ir` | **Connection reset** from this research environment |
| Static tariffs | Official **rate books (نرخنامه)** published as PDF (e.g. 1405 tariff tables circulating via Post-affiliated channels). These are **table lookups**, not interactive calculators. |
| Mechanism options | (a) **Curated tariff tables** from official PDFs; (b) **Merchant e-commerce API** after shop contract |

### 6.2 Merchant / gateway APIs (officially intended for shops)

Iran Post e-commerce (`ecommerce.post.ir`) and certified gateways expose price checks for contracted `shop_id`s. Community/official-adjacent examples (Yii2 Post Ecommerce, Tapin gateway docs) show shapes like:

**Example gateway price check (Tapin public doc — intermediary, not Post core):**

```http
POST https://public.api.tapin.ir/api/v1/post-office/check-price/
Content-Type: application/json
```

```json
{
  "price": "5000",
  "weight": "10000",
  "order_type": "0",
  "pay_type": "1",
  "from_province": "1",
  "from_city": "1",
  "to_province": "1",
  "to_city": "1"
}
```

Response fields include `send_price`, `tax`, `total`.

**Auth:** Shop credentials / OAuth client for Post e-commerce REST; SOAP variants exist in older stacks. **Not anonymous.**

| Dimension | Rating |
|-----------|--------|
| Technical feasibility | **Medium** (after contract) **or Low** (PDF-only) |
| Maintenance complexity | **High** for PDF tables (annual tariff changes); **Medium** for merchant API |
| BrandMonitor note | For intelligence scoring, PDF-derived indices may be enough; live quotes need a merchant account |

---

## Cross-cutting findings

1. **Almost no carrier publishes a fixed HTML price table** suitable for static harvest — matches `DATA_COVERAGE_REPORT.md` (“calculator_only”).
2. **Two integration classes:**
   - **Class A — Official partner APIs** (Tipax eTipax, AloPeyk, Iran Post merchant): clear auth, support path.
   - **Class B — Website XHR** (Chapar CDN API, Mahex `rate-calculation`): technically observable, legally/operationally weaker.
3. **Client-side-only pricing math** was **not** found for any supported carrier; all live quotes are server-evaluated.
4. **Delivery time** is inconsistently exposed: Chapar has a clean ETA API; Tipax has a WebForms ETA UI; AloPeyk returns duration with price; others are SLA constants in our curated YAML today.
5. **Do not bypass** Tipax CAPTCHA/ViewState, Mahex bot protections, or Post merchant auth.

---

## Proposed BrandMonitor interface (design only — not implemented)

If / when Class A credentials exist, introduce a reusable provider layer:

```text
postal/
  pricing/
    __init__.py
    types.py          # QuoteRequest, QuoteOffer, DeliveryEstimate, ProviderError
    base.py           # PricingProvider protocol
    registry.py       # load adapters by company slug
    adapters/
      tipax_etipax.py
      alopeyk_v2.py
      chapar_cdn.py      # optional, feature-flagged, undocumented
      mahex_website.py   # optional, feature-flagged
      iran_post_merchant.py
      curated_index.py   # fallback: official_companies.yaml price_index
```

### Interface sketch

```python
from typing import Protocol, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class Money:
    amount: int          # integer minor units (Rial) to avoid float drift
    currency: str = "IRR"

@dataclass(frozen=True)
class GeoPoint:
    lat: float | None = None
    lng: float | None = None
    city_code: str | None = None   # provider-native
    city_name: str | None = None
    province_code: str | None = None

@dataclass(frozen=True)
class ParcelSpec:
    weight_grams: int
    length_mm: int | None = None
    width_mm: int | None = None
    height_mm: int | None = None
    declared_value: Money | None = None
    pack_type: str | None = None   # normalized enum mapped per provider

@dataclass(frozen=True)
class QuoteRequest:
    origin: GeoPoint
    destination: GeoPoint
    parcel: ParcelSpec
    service_hint: str | None = None  # express / economy / on_demand / …
    options: dict | None = None      # COD, return, pickup type, …

@dataclass(frozen=True)
class QuoteOffer:
    provider: str
    company_slug: str
    total: Money
    breakdown: dict[str, Money]      # transport, fuel, vat, insurance, …
    service_code: str | None
    service_name: str | None
    eta_hours_min: float | None
    eta_hours_max: float | None
    raw_refs: dict                   # provider ids only; no secrets
    retrieved_at: datetime
    confidence: float                # 0–1 evidence grade for this quote
    source_kind: str                 # official_api | website_api | curated_table | unavailable

@dataclass(frozen=True)
class ProviderCapabilities:
    supports_live_price: bool
    supports_live_eta: bool
    requires_auth: bool
    official_docs_url: str | None
    maintenance_class: str           # low | medium | high

class PricingProvider(Protocol):
    slug: str

    def capabilities(self) -> ProviderCapabilities: ...

    def quote(self, request: QuoteRequest) -> Sequence[QuoteOffer]:
        """Return zero or more offers. Never invent prices.
        If unauthorized or unsupported, raise ProviderError or return
        a single offer with source_kind='unavailable' and confidence=0.
        """
        ...

    def estimate_delivery(self, request: QuoteRequest) -> Sequence[QuoteOffer]:
        """ETA-focused; may reuse quote() when ETA is bundled."""
        ...
```

### Adapter policy

| Adapter | Enable when | Notes |
|---------|-------------|-------|
| `tipax_etipax` | OM token in secrets | Prefer `/Pricing` + `/Pricing/Min` |
| `alopeyk_v2` | API Bearer token | Map lat/lng; mark service as on-demand |
| `iran_post_merchant` | Shop OAuth / SOAP creds | Or `curated_index` from نرخنامه PDF |
| `chapar_cdn` | Explicit allow-flag + legal OK | Monitor schema; cache city table |
| `mahex_website` | Explicit allow-flag + legal OK | Expect outages/bot walls |
| `curated_index` | Always | Current YAML `price_index` / typical days — **default** |

### Persistence (future)

Store quote samples in Postal Intelligence DB, e.g. `pi_price_quotes`, with:

- request hash, company_slug, total, currency, eta, `source_kind`, `retrieved_at`, raw JSON (redacted)
- never store API secrets in quote rows

Use aggregates to refresh `official_pricing` confidence — **without** silently changing `postal_score_v1` weights until a scored migration is approved.

---

## Maintenance complexity matrix

| Provider surface | Breakage risk | Auth ops | Catalog ops | Suggested SLA for BrandMonitor jobs |
|------------------|---------------|----------|-------------|-------------------------------------|
| Tipax eTipax OM | Medium | Token refresh | City IDs, Serviced codes | Daily benchmark matrix |
| Tipax WebForms | **Very high** | CAPTCHA/ViewState | Control IDs | **Do not automate** |
| Chapar CDN APIs | High (undocumented) | Optional token | Numeric city ids | Hourly canary + fallback |
| Mahex website API | High | Possible bot score | `IR-*` city codes | Canary + curated fallback |
| AloPeyk v2 | Low–Medium | API key | Transport types | On-demand samples in major cities |
| Iran Post merchant | Medium | Shop credentials | City/province ids | Daily |
| Iran Post PDF | Low technical / High editorial | None | Annual tariff edits | Per fiscal-year update |
| Pishro | N/A | N/A | N/A | Wait |

---

## Security & compliance notes

- Do **not** ship scrapers that solve Tipax CAPTCHAs or forge DNN ViewState.
- Do **not** embed third-party API keys from WooCommerce plugins found online.
- Prefer written contracts + Tipax Academy / AloPeyk / Post e-commerce onboarding.
- Rate-limit any website-API adapters; identify BrandMonitor with a clear User-Agent and honor `robots`/ToS.
- Quotes are **commercial facts at retrieval time**; always stamp `retrieved_at` and source.

---

## Suggested next steps (implementation later)

1. **Product/legal:** Obtain Tipax eTipax test account + AloPeyk sandbox token; open Chapar/Mahex partner inquiries for documented quote APIs.
2. **Engineering:** Land `postal/pricing/` interface + `curated_index` adapter only (no live HTTP) behind a feature flag.
3. **Data:** Design `pi_price_quotes` schema and a benchmark route matrix (Tehran↔Isfahan/Mashhad/Tabriz, 1 kg / 5 kg).
4. **Scoring:** Keep using curated `price_index` until live quote coverage is statistically stable; then propose a scored-dimension update in a separate RFC.
5. **Pishro / Post site:** Re-probe when network reachability improves; add adapters only after official surfaces are confirmed.

---

## Appendix A — Quick reference URLs

| Company | Calculator / docs |
|---------|-------------------|
| Tipax cost | https://tipaxco.com/transit-cost-calculator |
| Tipax time | https://tipaxco.com/transit-time-calculator |
| Tipax eTipax | https://tipaxco.com/etipax |
| Tipax API academy | https://academy.tipax.ir/education/etipax-api-parameters/ |
| Chapar cost | https://www.chaparnet.com/shipping-cost |
| Chapar time | https://www.chaparnet.com/shipping-time |
| Mahex rate | https://mahex.com/rate |
| AloPeyk docs | https://docs.alopeyk.com/ |
| Pishro | https://pishro.net/ (maintenance) |
| Iran Post | https://post.ir/ (unreachable in probe); merchant: https://ecommerce.post.ir/ |

## Appendix B — Mechanism taxonomy used in this report

- **Public API:** Documented, versioned, intended for integrators (may still need keys).
- **Server-side endpoint:** Browser/app calls a backend that computes the price (documented or not).
- **Client-side JavaScript:** Price fully computed in-browser from embedded tables/formulas (not observed here).
- **Other:** PDF tariff books, human sales quotes, login-gated portals, maintenance pages.
