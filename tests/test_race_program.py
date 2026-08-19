"""Unit tests for future race-program eligibility and grouping."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.race_program.eligibility import is_eligible_for_prediction, is_within_upcoming_window
from src.race_program.models import ProgramRace
from src.race_program.service import RaceProgramService
from tests.fixtures.race_program.build import (
    FP_EVENT_ID,
    FP_RACE_IDS,
    PRIMARY_MEETING_ID,
    build_program_document,
    write_program_fixture,
)

FIXTURE = Path("tests/fixtures/race_program/program_fixture.json")
OBS = Path("tests/fixtures/prediction_api/observations_fixture.jsonl.gz")
HORSE_NAMES = Path("tests/fixtures/prediction_api/horse_names.json")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


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
    svc = RaceProgramService.from_document(build_program_document(now=NOW))
    meetings = svc.list_upcoming_meetings(now=NOW, days=7)
    assert len(meetings) == 1
    assert meetings[0]["meeting_id"] == PRIMARY_MEETING_ID
    assert meetings[0]["location"] == "مشهد"
    race_ids = [r["race_id"] for r in meetings[0]["races"]]
    # Past + unknown-time races must not appear; far meeting outside 7 days excluded.
    assert "9003" not in race_ids
    assert "9004" not in race_ids
    assert "9100" not in race_ids
    assert race_ids == list(FP_RACE_IDS)
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
    svc = RaceProgramService.from_document(build_program_document(now=NOW))
    events = svc.list_future_five_parreh_events(now=NOW)
    assert len(events) == 1
    assert events[0]["event_id"] == FP_EVENT_ID
    assert [r["race_id"] for r in events[0]["races"]] == list(FP_RACE_IDS)
    assert len(events[0]["races"]) == 5
    # Same meeting appears in /predict upcoming.
    meetings = svc.list_upcoming_meetings(now=NOW, days=7)
    assert meetings[0]["meeting_id"] == events[0]["meeting_id"]


def test_five_parreh_excludes_completed_and_is_explicit() -> None:
    doc = build_program_document(now=NOW)
    # Completed / unknown races exist on the meeting but must not be in the FP event.
    meeting_races = {r["race_id"] for r in doc["meetings"][0]["races"]}
    assert "9003" in meeting_races
    assert "9004" in meeting_races
    fp_ids = doc["five_parreh_events"][0]["race_ids"]
    assert fp_ids == list(FP_RACE_IDS)
    assert "9003" not in fp_ids
    assert "9004" not in fp_ids

    svc = RaceProgramService.from_document(doc)
    events = svc.list_future_five_parreh_events(now=NOW)
    assert len(events) == 1
    assert [r["race_id"] for r in events[0]["races"]] == list(FP_RACE_IDS)
    assert all(r["scheduled_start"] is not None for r in events[0]["races"])


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
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    fixture_path = write_program_fixture(tmp_path / "program_fixture.json", now=NOW)
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(OBS.resolve()))
    monkeypatch.setenv("PREDICTION_VERIFY_FREEZE", "false")
    monkeypatch.setenv("HORSE_NAME_INDEX_PATH", str(HORSE_NAMES.resolve()))
    monkeypatch.setenv("RACE_PROGRAM_PATH", str(fixture_path.resolve()))
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
    assert body["count"] >= 1
    assert body["meetings"]
    assert body["meetings"][0]["track"] == "مشهد"
    meeting_race_ids = [r["race_id"] for r in body["meetings"][0]["races"]]
    assert meeting_race_ids == list(FP_RACE_IDS)
    # Historical freeze dump must not be the source — only program meetings.
    assert all(m["meeting_id"] != "freeze" for m in body["meetings"])

    detail = api_client.get(f"/race-program/meetings/{PRIMARY_MEETING_ID}")
    assert detail.status_code == 200
    assert detail.json()["race_count"] == 5
    # Meeting detail exposes races for UI selection — no manual race_id typing required.
    assert all(r.get("label") and r.get("race_number") for r in detail.json()["races"])

    fp = api_client.get("/race-program/five-parreh")
    assert fp.status_code == 200
    assert fp.json()["count"] == 1
    assert fp.json()["events"][0]["event_id"] == FP_EVENT_ID

    one = api_client.get(f"/race-program/five-parreh/{FP_EVENT_ID}")
    assert one.status_code == 200
    races = one.json()["races"]
    assert len(races) == 5
    assert [r["race_id"] for r in races] == list(FP_RACE_IDS)


def test_api_future_race_prediction_and_compare_without_manual_race_id(
    api_client: TestClient,
) -> None:
    """Predict / horse-vs-horse via program meeting → race_number, not typed race_id."""
    up = api_client.get("/race-program/upcoming", params={"days": 7})
    assert up.status_code == 200
    meeting = up.json()["meetings"][0]
    race = meeting["races"][0]
    assert race["label"] == "کورس ۱"
    assert race["race_number"] == 1
    race_id = race["race_id"]

    pred = api_client.get(f"/races/{race_id}/prediction")
    assert pred.status_code == 200
    field = pred.json()["prediction"]
    assert len(field) >= 2
    assert all(item.get("horse_name") for item in field[:2])

    horse_a = field[0]["horse_id"]
    horse_b = field[1]["horse_id"]
    assert horse_a != horse_b
    cmp = api_client.get(
        f"/races/{race_id}/compare",
        params={"horse_a": horse_a, "horse_b": horse_b},
    )
    assert cmp.status_code == 200
    body = cmp.json()
    assert body["horse_a"]["horse_id"] == horse_a
    assert body["horse_b"]["horse_id"] == horse_b
    assert body.get("selected") in {"horse_a", "horse_b", None} or body.get("selected_horse")


def test_api_all_five_parreh_races_resolve_predictions(api_client: TestClient) -> None:
    one = api_client.get(f"/race-program/five-parreh/{FP_EVENT_ID}")
    assert one.status_code == 200
    races = one.json()["races"]
    assert len(races) == 5
    for race in races:
        r = api_client.get(f"/races/{race['race_id']}/prediction")
        assert r.status_code == 200, race["race_id"]
        assert len(r.json()["prediction"]) >= 1


def test_api_empty_program_persian_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text('{"meetings":[],"five_parreh_events":[]}', encoding="utf-8")
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(OBS.resolve()))
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


def test_committed_fixture_file_is_coherent_with_builder() -> None:
    """Committed JSON keeps the same designated FP race ids as the builder."""
    assert FIXTURE.exists()
    raw = __import__("json").loads(FIXTURE.read_text(encoding="utf-8"))
    assert raw["five_parreh_events"][0]["race_ids"] == list(FP_RACE_IDS)
    meeting = next(m for m in raw["meetings"] if m["meeting_id"] == PRIMARY_MEETING_ID)
    scheduled = [r for r in meeting["races"] if r.get("status") == "scheduled" and r.get("scheduled_start")]
    # Primary scheduled races are exactly the designated FP set (plus may include far? no).
    primary_ids = [r["race_id"] for r in scheduled if r["race_id"] in FP_RACE_IDS]
    assert primary_ids == list(FP_RACE_IDS)
