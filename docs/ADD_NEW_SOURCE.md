# How to add a new data source (< 10 minutes)

BrandMonitor multi-source ingest is provider-based. **Do not scrape fragile HTML** unless you have a compliant, stable extractor or official API.

## Steps

1. **Create a provider module** under `collectors/providers/` (or a thin wrapper in `collectors/<source>.py`):

```python
# collectors/providers/example_portal.py
from collectors.providers.import_adapter import ManualImportProvider

class ExamplePortalProvider(ManualImportProvider):
    def __init__(self, **kwargs):
        super().__init__(
            "example_portal",
            "Example Portal",
            dataset_dir=kwargs.get("dataset_dir") or "data/imports/example_portal",
            mode=kwargs.get("mode") or "manual_import",
        )
```

2. **Register it** in `collectors/providers/__init__.py`:

```python
from collectors.providers.example_portal import ExamplePortalProvider
_FACTORY["example_portal"] = ExamplePortalProvider
PROVIDER_CATALOG.append(
    ProviderInfo("example_portal", "Example Portal", "manual_import", True, "CSV/JSON import")
)
```

3. **Drop sample/production files** into `data/imports/example_portal/*.csv` using the unified columns:

`brand,branch,province,city,latitude,longitude,rating,review,review_date,reviewer,reply,reply_date,photos_count,url`

4. **Run the pipeline**:

```bash
python3 scripts/run_multisource_pipeline.py \
  --sources google_maps neshan balad cafebazaar myket example_portal
```

5. **Optional live crawl**: only if the source fits `BranchReviewSource` (discover/collect/close). Wire it in `collectors/sources/registry.py` **without changing** Scoring/AI/API contracts.

## Provider modes

| Mode | When to use |
|------|-------------|
| `manual_import` | No official API yet — CSV/JSON datasets |
| `official_api` | Vendor API + credentials available |
| `compliant_extractor` | Approved non-fragile extractor |
| `live_maps` | Existing Google Maps Playwright path |

Swap modes later by changing the provider constructor — **callers stay the same**.

## Planned sources (stubs in catalog)

Google Play, Apple App Store, Instagram, X, Reddit, LinkedIn, official websites, news, complaint portals.
