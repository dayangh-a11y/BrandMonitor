"""Build TEST-ONLY race-program documents with freeze-backed race ids.

All scheduled_start values are derived from an explicit ``now`` so the fixture
stays compatible with ``GET /race-program/upcoming?days=7`` without inventing
production schedule data.

Five-Parreh race ids are an explicit designated set — never inferred from
consecutive integers. Every designated race_id must exist in the prediction
observations fixture so ``GET /races/{id}/prediction`` returns 200.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Freeze-backed race ids from tests/fixtures/prediction_api/observations_fixture.jsonl.gz
# Chosen because each has a multi-horse field suitable for prediction / horse-vs-horse.
FP_RACE_IDS: tuple[str, ...] = ("3393", "3391", "3392", "636", "639")
PRIMARY_MEETING_ID = "msh-future"
FP_EVENT_ID = "fp-msh-future"
FIXTURE_PATH = Path(__file__).resolve().parent / "program_fixture.json"


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def build_program_document(now: datetime | None = None) -> dict[str, Any]:
    """Return a coherent TEST race-program payload relative to ``now``."""
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    # All primary meeting races fall inside the default 7-day upcoming window.
    persian_nums = ("۱", "۲", "۳", "۴", "۵")
    base = now_utc + timedelta(hours=26)
    future_races = []
    for index, race_id in enumerate(FP_RACE_IDS):
        future_races.append(
            {
                "race_id": race_id,
                "race_number": index + 1,
                "label": f"کورس {persian_nums[index]}",
                "scheduled_start": _iso(base + timedelta(minutes=30 * index)),
                "status": "scheduled",
            }
        )

    # Explicit negative controls (must never appear as upcoming / FP races).
    future_races.append(
        {
            "race_id": "9003",
            "race_number": 6,
            "label": "کورس ۶",
            "scheduled_start": _iso(now_utc - timedelta(days=400)),
            "status": "completed",
        }
    )
    future_races.append(
        {
            "race_id": "9004",
            "race_number": 7,
            "label": "کورس ۷",
            "status": "unknown_time",
        }
    )

    return {
        "_comment": (
            "TEST FIXTURE ONLY — not a production race card. "
            "Race ids map to freeze observations_fixture races. "
            "Regenerate with: python3 tests/fixtures/race_program/build.py"
        ),
        "meetings": [
            {
                "meeting_id": PRIMARY_MEETING_ID,
                "display_date": "تست — جلسه آینده (fixture)",
                "track": "مشهد",
                "city": "مشهد",
                "races": future_races,
            },
            {
                "meeting_id": "gnb-far",
                "display_date": "تست — خارج از پنجره ۷ روزه",
                "track": "گنبدکاووس",
                "city": "گنبدکاووس",
                "races": [
                    {
                        "race_id": "9100",
                        "race_number": 1,
                        "label": "کورس ۱",
                        "scheduled_start": _iso(now_utc + timedelta(days=40)),
                        "status": "scheduled",
                    }
                ],
            },
        ],
        "five_parreh_events": [
            {
                "event_id": FP_EVENT_ID,
                "meeting_id": PRIMARY_MEETING_ID,
                "display_date": "تست — پنج‌پره آینده (fixture)",
                "track": "مشهد",
                "city": "مشهد",
                "title": "پنج‌پره",
                # Explicit designation — not inferred from consecutive race ids.
                "race_ids": list(FP_RACE_IDS),
            }
        ],
    }


def write_program_fixture(
    path: Path | None = None,
    *,
    now: datetime | None = None,
) -> Path:
    """Materialize ``program_fixture.json`` for live API / E2E use."""
    target = Path(path) if path is not None else FIXTURE_PATH
    payload = build_program_document(now=now)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    path = write_program_fixture()
    print(f"Wrote {path}")
    print(f"Five-Parreh race_ids={list(FP_RACE_IDS)}")


if __name__ == "__main__":
    main()
