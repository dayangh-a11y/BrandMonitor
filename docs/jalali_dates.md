# Jalali dates (Iranian horse racing)

## Policy

- **Default calendar for users:** Jalali (Shamsi).
- **Database storage / SQL filters:** Gregorian (`date` / ISO).
- **Timezone:** `Asia/Tehran`.
- Bare years such as `1403` are Jalali calendar years.
- Do not mix calendars in user-facing text unless both are shown.

## Code

Use `src/utils/jalali.py`:

| Need | Helper |
|------|--------|
| User Jalali day → DB | `to_gregorian("1403/05/16")` / `parse_user_date` |
| Jalali year → DB range | `query_jalali_year(1403)` |
| DB date → user | `format_jalali(race_date)` |
| Show both calendars | `format_both(race_date)` |
| Range filter | `query_date_range(start, end)` |

```python
from src.utils.jalali import format_jalali, query_jalali_year, to_gregorian

start, end = query_jalali_year(1403)  # Gregorian bounds for SQL
g = to_gregorian("1403/05/16")
print(format_jalali(g))  # 1403/05/16
```
