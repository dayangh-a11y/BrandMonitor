# Phase 8 — Telegram Output Design

- Bot UI: **not built**
- Telegram = presentation layer only
- All numbers come from Prediction Engine / API JSON

## Commands → Engine

- `/race` → `GET /race/{race_id} + /ranking`
- `/next` → `upcoming race discovery (future) → /race/{id}/ranking`
- `/horse` → `GET /horse/{horse_id}/analysis`
- `/form` → `GET /horse/{horse_id}/form`
- `/pedigree` → `GET /horse/{horse_id}/pedigree`
- `/compare` → `multi horse_id analysis merge (engine-side)`
- `/predict` → `alias of /race ranking — scores not probabilities`

## Example card

```
🏇 گنبدکاووس
گروه 4 | 1500 متر

🥇 گل مارال
Score: 24.4444
Confidence: VERY_LOW
Data quality: LOW

🥈 انفجار ایگدری
Score: 15.2778

🥉 دازجهان ب
Score: 14.4444

⚠️ هشدار:
- horse_id=3257 has no prior starts before 1995-04-14 (very low evidence)
- horse_id=3370 has no prior starts before 1995-04-14 (very low evidence)
- horse_id=9243 has no prior starts before 1995-04-14 (very low evidence)
- horse_id=3369 has no prior starts before 1995-04-14 (very low evidence)
- horse_id=9414 has no prior starts before 1995-04-14 (very low evidence)

جزئیات اختیاری: [فرم اخیر] [شجره] [میادین] [مسافت] [تحلیل کامل]
(methodology=pe-v1.0.0:baseline_A_historical_v1; score≠probability)
```
