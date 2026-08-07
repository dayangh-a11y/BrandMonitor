# Race video extraction — investigation

## Question

Why did historical collection store **0** race videos?

## Method

Fetched five race pages with Playwright and inspected:

1. Visible HTML around the video UI
2. Embedded Next.js RSC JSON (`_weekInfo.races[].media`)
3. Network-style URL presence (no separate video API required for listed clips)

### Sample URLs

| # | URL | Era |
|---|-----|-----|
| 1 | `/racecards/clpniklfc1y5mwrdovypaxdou?round=1` | 2006 (old) |
| 2 | `/racecards/clpniklyr1ym0wrdo42hiw7k5?round=5` | older |
| 3 | `/racecards/clpniqv2y2gcowrdocteaara4?round=6` | mid |
| 4 | `/racecards/cmb2i62bv00gtmp01nycmmqrf?round=4` | 1404 / recent |
| 5 | `/racecards/cms261wbt00ollt01w4jifkjx?round=6` | 2026-08-01 (newest) |

Artifacts: `output/video_debug/race_*.html`, `race_*_object.json`.

## Findings

### Where video data lives

**In the HTML page response**, inside the RSC payload:

`_weekInfo.races[n].media[]`

Not loaded by a separate video API for these listings. The empty modal shell is present in HTML:

```html
<div class="modal" id="myModalClip" ... aria-label="نمایش ویدیو">
  <div id="video-body" class="modal-body"></div>
</div>
```

The modal body is filled client-side when the user opens “نمایش ویدیو”, but **the URLs themselves are already in the page JSON**.

### Two media shapes

**A. Historical / older heats (samples 1–3)** — placeholder only, **no URL**:

```json
"media": [{"type": "APARAT"}]
```

Conclusion for many older races: the site marks Aparat as the provider but **does not publish a video URL**. There is nothing extractable.

**B. Newer heats (samples 4–5)** — real URLs in HTML/JSON:

```json
"media": [
  {"url": "photofinish/….jpg", "type": "PHOTO_FINISH", "title": "4"},
  {"url": "https://aparat.com/v/…", "type": "APARAT", "title": "…"},
  {"url": "https://aparat.com/v/…", "type": "YOUTUBE", "title": "…"}
]
```

Relative photofinish paths resolve on CDN: `https://cdn.asbdavani.app/photofinish/…`.

YouTube footer link (`youtube.com/@asbdavani_app`) is site branding, not a race clip.

### Why the warehouse had 0 videos

1. Parser built `Race` **without** copying `media`.
2. Raw `payload_json` was `Race.model_dump()` → no `media` key.
3. Warehouse ETL already looked for `payload_json["media"]` / `["videos"]`, found nothing.

So newer races **did have videos in HTML**, but extraction dropped them. Older races often truly lack URLs.

## Fix (extraction only)

- Parse `races[].media` into `Race.media`
- Normalize relative media URLs via `cdn.asbdavani.app`
- Existing warehouse ETL then persists items that include a `url`

No crawler architecture changes.
