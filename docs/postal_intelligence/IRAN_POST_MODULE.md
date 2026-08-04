# Iran Post Dedicated Module

Iran Post (`post`) is treated as the **national postal operator**, not a regular private carrier.

## What it maintains

| Domain | Source |
|--------|--------|
| Official services | `config/iran_post/official_profile.yaml` |
| Official pricing | curated public / merchant gateway (no invented tariffs) |
| Official delivery estimates | curated public product windows |
| Branch directory | Maps-observed warehouse branches + official claimed scale |
| Service coverage | official provinces/cities/branches + observed cities |
| Weight & size limits | curated public |
| Insurance rules | curated public |
| Tracking | public surfaces only (`tracking.post.ir`) |
| Working hours | curated public |
| Google Maps reviews | warehouse `pi_reviews` for Post offices only |

## Comparison modes

### 1. National Ranking

Compares all selected companies with **all available data**.

Always displays:

- `coverage_percentage`
- `number_of_branches`
- `number_of_reviews`
- `confidence_score`

Emits **unequal geographic coverage warnings** when province-coverage gaps exceed the configured threshold (default 25 pp), and always reminds that Iran Post is not a peer private network.

### 2. Fair Comparison Mode

Compares **only cities where every selected company has observed branches**.

- If the intersection is empty → refuses a peer ranking (`eligible=false`) rather than inventing overlap.
- Fair mode for Post uses **Maps-observed** post-office cities, not the official ~9000-branch claim.

## Policy

> Never compare companies with unequal geographic coverage without warning the user.

`treat_as_regular_carrier: false` in the official profile.

## CLI

```bash
PYTHONPATH=. python3 scripts/build_iran_post_module.py
```

Writes JSON under `docs/postal_intelligence/iran_post/`.

## API

Requires `X-API-Token`.

| Method | Path |
|--------|------|
| GET | `/postal/iran-post/catalog` |
| GET | `/postal/iran-post/profile` |
| GET | `/postal/iran-post/snapshot` |
| GET | `/postal/iran-post/maps-reviews` |
| GET | `/postal/iran-post/branches` |
| GET | `/postal/iran-post/compare/national` |
| GET | `/postal/iran-post/compare/fair?slugs=post&slugs=tipax&slugs=chapar` |
| POST | `/postal/iran-post/compare` `{ "mode": "national"|"fair", "slugs": [...] }` |

## Code layout

- `config/iran_post/official_profile.yaml` — curated national-operator profile
- `postal/iran_post/profile.py` — profile loader
- `postal/iran_post/geo.py` — city/province normalization + coverage %
- `postal/iran_post/maps_reviews.py` — warehouse Maps reviews for Post offices
- `postal/iran_post/compare.py` — National Ranking + Fair Comparison
- `postal/iran_post/provider.py` — `IranPostModule` facade
- `api/iran_post_routes.py` — HTTP surface

Live pricing quotes remain in `postal/pricing/adapters/iran_post.py` (credential-gated merchant API) and are separate from this intelligence module.

## Maps-observed footprint (latest expand)

After province/city sweeps with aliases (`اداره پست`, `شرکت ملی پست`, …):

| Metric | Before | After |
|--------|-------:|------:|
| Observed post offices | ~32 | **~260** |
| Maps reviews (warehouse) | ~242 | **~800+** |
| Provinces touched | ~4 | **~23–30** |

Source DB: `data/coverage_expand/post_coverage.db` → rebuild via `scripts/build_postal_intelligence.py`.
Still far below the official ~9000-branch claim — Fair Comparison remains required for peer routes.

