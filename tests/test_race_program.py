"""Unit tests for future race-program eligibility and grouping."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.race_program.eligibility import is_eligible_for_prediction, is_within_upcoming_window
from src.race_program.models import ProgramRace
from src.race_program.service import RaceProgramService

FIXTURE = Path("tests/fixtures/race_program/program_fixture.json")
NOW = datetime(2030, 8, 20, 12, 0, tzinfo=timezone.utc)


def test_future_race_eligible_past_and_running_rejected() -> None:
    future = NOW + timedelta(hours=2)
    past = NOW - timedelta(hours=2)
    running = NOW - timedelta(seconds=1)  # already started ⇒ ineligible
    assert is_eligible_for_prediction(future, now=NOW) is True
    assert is_eligible_for_prediction(past, now=NOW) is False
    assert is_eligible_for_prediction(running, now=NOW) is False
    assert is_eligible_for_prediction(None, now=NOW) is False


def test_missing_scheduled_time_not_safely_future() -> None:
    race = ProgramRace(
        race_id="x",
        race_number=1,
        label="کورس ۱",
        scheduled_start=None,
        status="unknown_time",
    )
    assert race.is_eligible(now=NOW) is False
    svc = RaceProgramService.from_document(
        {
            "meetings": [
                {
                    "meeting_id": "m1",
                    "display_date": "x",
                    "track": "مشهد",
                    "races": [
                        {"race_id": "1", "race_number": 1, "label": "کورس ۱"},
                    ],
                }
            ]
        }
    )
    assert svc.list_upcoming_meetings(now=NOW, days=7) == []
    detail = svc.meeting_detail("m1", now=NOW, prediction_only=False)
    assert detail is not None
    assert detail["races"][0]["status"] == "unknown_time"
    assert detail["races"][0]["eligible_for_prediction"] is False


def test_upcoming_grouped_by_meeting_excludes_history() -> None:
    svc = RaceProgramService.from_document(
        __import__("json").loads(FIXTURE.read_text(encoding="utf-8"))
    )
    meetings = svc.list_upcoming_meetings(now=NOW, days=7)
    assert len(meetings) == 1
    assert meetings[0]["meeting_id"] == "msh-future"
    assert meetings[0]["location"] == "مشهد"
    assert meetings[0]["display_date"] == "جمعه ۳۰ مرداد ۱۴۰۵"
    race_ids = [r["race_id"] for r in meetings[0]["races"]]
    # Past + unknown-time races must not appear; far meeting outside 7 days excluded.
    assert "9003" not in race_ids
    assert "9004" not in race_ids
    assert "9100" not in race_ids
    assert race_ids == ["3393", "3394", "3395", "9001", "9002"]
    assert all(r["eligible_for_prediction"] for r in meetings[0]["races"])


def test_upcoming_window_excludes_beyond_days() -> None:
    start = NOW + timedelta(days=10)
    assert is_within_upcoming_window(start, now=NOW, days=7) is False
    assert is_within_upcoming_window(NOW + timedelta(days=1), now=NOW, days=7) is True


def test_no_upcoming_message() -> None:
    svc = RaceProgramService(meetings=[], events=[])
    payload = svc.upcoming_payload(now=NOW, days=7)
    assert payload["count"] == 0
    assert payload["message"] == "در ۷ روز آینده مسابقه‌ای برای پیش‌بینی ثبت نشده است."


def test_five_parreh_uses_same_program_source() -> None:
    svc = RaceProgramService.from_document(
        __import__("json").loads(FIXTURE.read_text(encoding="utf-8"))
    )
    events = svc.list_future_five_parreh_events(now=NOW)
    assert len(events) == 1
    assert events[0]["event_id"] == "fp-msh-future"
    assert [r["race_id"] for r in events[0]["races"]] == [
        "3393",
        "3394",
        "3395",
        "9001",
        "9002",
    ]
    # Same meeting appears in /predict upcoming.
    meetings = svc.list_upcoming_meetings(now=NOW, days=7)
    assert meetings[0]["meeting_id"] == events[0]["meeting_id"]


def test_currently_running_race_rejected_in_meeting_detail() -> None:
    svc = RaceProgramService.from_document(
        {
            "meetings": [
                {
                    "meeting_id": "live",
                    "display_date": "امروز",
                    "track": "تهران",
                    "races": [
                        {
                            "race_id": "1",
                            "race_number": 1,
                            "label": "کورس ۱",
                            "scheduled_start": (NOW - timedelta(minutes=5)).isoformat(),
                        },
                        {
                            "race_id": "2",
                            "race_number": 2,
                            "label": "کورس ۲",
                            "scheduled_start": (NOW + timedelta(hours=1)).isoformat(),
                        },
                    ],
                }
            ]
        }
    )
    detail = svc.meeting_detail("live", now=NOW, prediction_only=True)
    assert detail is not None
    assert [r["race_id"] for r in detail["races"]] == ["2"]


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(Path("tests/fixtures/prediction_api/observations_fixture.jsonl.gz").resolve()))
    monkeypatch.setenv("PREDICTION_VERIFY_FREEZE", "false")
    monkeypatch.setenv("HORSE_NAME_INDEX_PATH", str(Path("tests/fixtures/prediction_api/horse_names.json").resolve()))
    monkeypatch.setenv("RACE_PROGRAM_PATH", str(FIXTURE.resolve()))
    monkeypatch.setattr("src.race_program.service.utc_now", lambda: NOW)
    monkeypatch.setattr("src.race_program.eligibility.utc_now", lambda: NOW)

    from src.api import deps
    from src.api.main import app
    from src.api.race_program_routes import clear_race_program_cache

    deps.clear_engine_cache()
    clear_race_program_cache()
    with TestClient(app) as c:
        yield c
    clear_race_program_cache()
    deps.clear_engine_cache()


def test_api_upcoming_and_five_parreh_endpoints(api_client: TestClient) -> None:
    up = api_client.get("/race-program/upcoming", params={"days": 7})
    assert up.status_code == 200
    body = up.json()
    assert body["count"] == 1
    assert body["meetings"][0]["track"] == "مشهد"
    assert "3393" in [r["race_id"] for r in body["meetings"][0]["races"]]
    # Historical freeze dump must not be the source — only program meetings.
    assert all(m["meeting_id"] != "freeze" for m in body["meetings"])

    detail = api_client.get("/race-program/meetings/msh-future")
    assert detail.status_code == 200
    assert detail.json()["race_count"] == 5

    fp = api_client.get("/race-program/five-parreh")
    assert fp.status_code == 200
    assert fp.json()["count"] == 1
    assert fp.json()["events"][0]["event_id"] == "fp-msh-future"

    one = api_client.get("/race-program/five-parreh/fp-msh-future")
    assert one.status_code == 200
    assert len(one.json()["races"]) == 5


def test_api_empty_program_persian_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text('{"meetings":[],"five_parreh_events":[]}', encoding="utf-8")
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(Path("tests/fixtures/prediction_api/observations_fixture.jsonl.gz").resolve()))
    monkeypatch.setenv("PREDICTION_VERIFY_FREEZE", "false")
    monkeypatch.setenv("RACE_PROGRAM_PATH", str(empty.resolve()))
    monkeypatch.setattr("src.race_program.service.utc_now", lambda: NOW)

    from src.api import deps
    from src.api.main import app
    from src.api.race_program_routes import clear_race_program_cache

    deps.clear_engine_cache()
    clear_race_program_cache()
    with TestClient(app) as client:
        r = client.get("/race-program/upcoming")
        assert r.status_code == 200
        assert r.json()["message"] == "در ۷ روز آینده مسابقه‌ای برای پیش‌بینی ثبت نشده است."
    clear_race_program_cache()
    deps.clear_engine_cache()
