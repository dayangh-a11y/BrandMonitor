"""Unit tests for Telegram bot thin client (mocked HTTP API — no real Telegram)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from src.telegram_bot.api_client import PredictionApiClient
from src.telegram_bot.config import TelegramBotSettings
from src.telegram_bot.errors import (
    ApiUnavailableError,
    DatasetUnavailableError,
    HorseNotFoundError,
    RaceNotFoundError,
)
from src.telegram_bot import formatters as fmt
from src.telegram_bot.state import FiveParrehSession, SessionStore


def test_config_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    s = TelegramBotSettings(telegram_bot_token="", api_base_url="http://localhost:8000")
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        s.require_token()


def test_config_strips_base_url_slash() -> None:
    s = TelegramBotSettings(
        telegram_bot_token="x",
        api_base_url="http://localhost:8000/",
    )
    assert s.api_base_url == "http://localhost:8000"
    assert s.require_token() == "x"


def test_api_client_list_races() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/races"
        return httpx.Response(200, json={"total": 1, "races": [{"race_id": 1, "track": "گنبد"}]})

    client = PredictionApiClient("http://test", timeout_seconds=2)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    data = client.list_races(limit=10)
    assert data["races"][0]["race_id"] == 1
    client.close()


def test_api_client_prediction_and_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/prediction"):
            return httpx.Response(
                200,
                json={
                    "race_id": 10,
                    "prediction": [
                        {"rank": 1, "horse_id": 1, "horse_name": None, "score": 87.4, "probability": None}
                    ],
                },
            )
        if request.url.path.startswith("/horses/"):
            return httpx.Response(404, json={"detail": "missing"})
        if request.url.path == "/races/999":
            return httpx.Response(404, json={"detail": "missing"})
        if request.url.path == "/health":
            return httpx.Response(
                503,
                json={"detail": "PRODUCTION BLOCKER: observations missing"},
            )
        return httpx.Response(500, json={"detail": "boom"})

    client = PredictionApiClient("http://test")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    pred = client.get_race_prediction(10)
    assert pred["prediction"][0]["score"] == 87.4
    assert pred["prediction"][0]["probability"] is None
    with pytest.raises(HorseNotFoundError):
        client.get_horse(1)
    with pytest.raises(RaceNotFoundError):
        client.get_race(999)
    with pytest.raises(DatasetUnavailableError):
        client.get_health()
    client.close()


def test_api_client_five_parreh_post() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/five-parreh/combinations"
        import json

        payload = json.loads(request.content.decode())
        assert len(payload["races"]) == 5
        return httpx.Response(
            200,
            json={
                "total_combinations": 243,
                "price_per_combination": 10000,
                "total_cost": 2430000,
                "selections_per_race": [3, 3, 3, 3, 3],
                "combinations_omitted": False,
                "combinations": [],
            },
        )
    client = PredictionApiClient("http://test")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    races = [{"race_id": f"R{i}", "horses": ["A", "B", "C"]} for i in range(1, 6)]
    out = client.generate_five_parreh(races, price_per_combination=10_000)
    assert out["total_combinations"] == 243
    assert out["total_cost"] == 2_430_000
    client.close()


def test_api_unavailable_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow")

    client = PredictionApiClient("http://test")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    with pytest.raises(ApiUnavailableError):
        client.list_races()
    client.close()


def test_formatters_start_help_score_not_percent() -> None:
    assert "سیستم تحلیل" in fmt.welcome_text()
    assert "/predict" in fmt.help_text()
    text = fmt.format_prediction(
        {
            "race_id": 1,
            "prediction": [
                {"rank": 1, "horse_id": 9, "horse_name": "Horse A", "score": 87.4, "probability": None}
            ],
        }
    )
    assert "امتیاز: 87.4" in text
    assert "Score:" not in text
    assert "87%" not in text
    assert "احتمال برد" not in text.split("ℹ️")[0]  # body must not claim win probability
    assert "ℹ️ امتیاز، احتمال برد نیست." in text


def test_format_prediction_null_score_and_friendly_warnings() -> None:
    text = fmt.format_prediction(
        {
            "race_id": 601,
            "prediction": [
                {"rank": 1, "horse_id": 3317, "horse_name": None, "score": 24.0, "warnings": []},
                {"rank": 2, "horse_id": 3232, "horse_name": None, "score": 20.7, "warnings": []},
                {
                    "rank": 3,
                    "horse_id": 3231,
                    "horse_name": None,
                    "score": None,
                    "warnings": [
                        "low_feature_coverage",
                        "score_unavailable_insufficient_features",
                    ],
                },
            ],
        }
    )
    assert "🏇 پیش‌بینی کورس 601" in text
    assert "🥇 اسب 3317" in text
    assert "امتیاز: 24.0" in text
    assert "🥈 اسب 3232" in text
    assert "امتیاز: 20.7" in text
    assert "🥉 اسب 3231" in text
    assert "امتیاز: —" in text
    assert "⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد." in text
    # Internal codes must not leak to users
    assert "low_feature_coverage" not in text
    assert "score_unavailable_insufficient_features" not in text
    assert "احتمال برد" not in text.replace("ℹ️ امتیاز، احتمال برد نیست.", "")
    assert "ℹ️ امتیاز، احتمال برد نیست." in text
    # Deduplicate same friendly message when both codes present
    assert text.count("⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد.") == 1


def test_friendly_warnings_mapping() -> None:
    msgs = fmt.friendly_warnings(
        ["low_feature_coverage", "score_unavailable_insufficient_features", "unknown_code"]
    )
    assert msgs == ["⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد."]


def test_format_races_empty() -> None:
    assert "در دسترس نیست" in fmt.format_race_list({"races": []})


def test_format_horse_and_fiveparreh() -> None:
    horse = fmt.format_horse(
        {
            "horse_id": 3470,
            "horse_name": None,
            "observation_count": 9,
            "evidence": [{"metric": "career_win_rate", "value": 0.1}],
            "warnings": ["low_feature_coverage"],
        }
    )
    assert "3470" in horse
    assert "low_feature_coverage" not in horse
    assert "⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد." in horse
    assert "ℹ️ امتیاز، احتمال برد نیست." in horse

    confirm = fmt.format_fiveparreh_confirm(
        [3, 3, 2, 2, 3],
        total_combinations=108,
        price_per_combination=10_000,
    )
    assert "108" in confirm
    assert "1,080,000" in confirm

    result = fmt.format_fiveparreh_result(
        {
            "total_combinations": 243,
            "price_per_combination": 10000,
            "total_cost": 2430000,
            "combinations_omitted": True,
        }
    )
    assert "243" in result
    assert "خلاصه" in result


def test_fiveparreh_state_flow_and_validation() -> None:
    store = SessionStore(ttl_seconds=60)
    s = store.get_or_create(42)
    assert s.step == "pick_event"
    s.race_ids = ["1", "2", "3", "4", "5"]
    s.race_index = 0
    s.step = "pick_horses"
    s.toggle_horse("10")
    s.toggle_horse("11")
    s.toggle_horse("10")  # deselect
    assert s.selected_for_current() == ["11"]
    s.horses_by_race = {
        "1": ["a", "b"],
        "2": ["c", "d"],
        "3": ["e", "f"],
        "4": ["g", "h"],
        "5": ["i", "j"],
    }
    assert s.selections_per_race() == [2, 2, 2, 2, 2]
    assert s.total_combinations_estimate() == 32
    payload = s.to_api_payload()
    assert len(payload) == 5
    assert all(len(r["horses"]) >= 1 for r in payload)

    # empty race => no estimate
    s.horses_by_race["3"] = []
    assert s.total_combinations_estimate() is None


def _sample_event_doc(*, future: bool, race_count: int = 5, event_id: str = "fp-future-1") -> dict:
    from datetime import datetime, timedelta, timezone

    base = datetime.now(timezone.utc) + (timedelta(days=3) if future else timedelta(days=-3))
    races = []
    for i in range(race_count):
        races.append(
            {
                "race_id": str(9000 + i),
                "label": f"Race {chr(ord('X') + i)}",
                "scheduled_start": (base + timedelta(minutes=30 * i)).isoformat(),
            }
        )
    return {
        "events": [
            {
                "event_id": event_id,
                "display_date": "جمعه ۳۰ مرداد",
                "track": "مشهد",
                "city": "مشهد",
                "title": "پنج‌پره",
                "races": races,
            }
        ]
    }


def test_future_event_eligibility_and_exactly_five() -> None:
    from src.telegram_bot.five_parreh_events import (
        InMemoryFiveParrehEventSource,
        list_future_events,
        parse_events_document,
    )

    future = parse_events_document(_sample_event_doc(future=True))
    past = parse_events_document(_sample_event_doc(future=False, event_id="fp-past"))
    four = parse_events_document(_sample_event_doc(future=True, race_count=4, event_id="fp-four"))
    source = InMemoryFiveParrehEventSource(future + past + four)
    listed = list_future_events(source)
    assert [e.event_id for e in listed] == ["fp-future-1"]
    assert listed[0].race_ids == ["9000", "9001", "9002", "9003", "9004"]


def test_completed_race_rejects_whole_event() -> None:
    from datetime import datetime, timedelta, timezone

    from src.telegram_bot.five_parreh_events import (
        InMemoryFiveParrehEventSource,
        list_future_events,
        parse_events_document,
        reject_if_any_race_completed,
    )

    now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    doc = {
        "events": [
            {
                "event_id": "fp-mixed",
                "display_date": "x",
                "track": "y",
                "title": "پنج‌پره",
                "races": [
                    {
                        "race_id": "1",
                        "label": "A",
                        "scheduled_start": (now - timedelta(minutes=1)).isoformat(),
                    },
                    {
                        "race_id": "2",
                        "label": "B",
                        "scheduled_start": (now + timedelta(minutes=30)).isoformat(),
                    },
                    {
                        "race_id": "3",
                        "label": "C",
                        "scheduled_start": (now + timedelta(minutes=60)).isoformat(),
                    },
                    {
                        "race_id": "4",
                        "label": "D",
                        "scheduled_start": (now + timedelta(minutes=90)).isoformat(),
                    },
                    {
                        "race_id": "5",
                        "label": "E",
                        "scheduled_start": (now + timedelta(minutes=120)).isoformat(),
                    },
                ],
            }
        ]
    }
    event = parse_events_document(doc)[0]
    assert reject_if_any_race_completed(event, now=now) is True
    assert list_future_events(InMemoryFiveParrehEventSource([event]), now=now) == []


def test_fiveparreh_not_inferred_from_race_id_arithmetic() -> None:
    from src.telegram_bot.five_parreh_events import InMemoryFiveParrehEventSource, list_future_events

    # Empty source: historical freeze race sequences must NOT invent events.
    assert list_future_events(InMemoryFiveParrehEventSource([])) == []


def test_future_meeting_selection_locks_exactly_five_for_api() -> None:
    from src.telegram_bot.five_parreh_events import (
        InMemoryFiveParrehEventSource,
        get_event_by_id,
        parse_events_document,
    )

    source = InMemoryFiveParrehEventSource(parse_events_document(_sample_event_doc(future=True)))
    event = get_event_by_id(source, "fp-future-1")
    assert event is not None
    assert len(event.races) == 5
    session = FiveParrehSession(step="confirm_event", event_id=event.event_id)
    session.race_ids = event.race_ids
    session.horses_by_race = {rid: [f"h{rid}"] for rid in session.race_ids}
    session.step = "confirm"
    payload = session.to_api_payload()
    assert len(payload) == 5
    assert [p["race_id"] for p in payload] == event.race_ids


def test_format_future_fiveparreh_events() -> None:
    from src.telegram_bot.five_parreh_events import parse_events_document

    empty = fmt.format_future_fiveparreh_events([])
    assert "آینده" in empty
    assert "ثبت نشده" in empty
    events = parse_events_document(_sample_event_doc(future=True))
    text = fmt.format_future_fiveparreh_events(events)
    assert "مشهد" in text
    detail = fmt.format_fiveparreh_event_detail(events[0])
    assert "این پنج کورس در پنج‌پره هستند" in detail
    assert "Race X" in detail


def test_user_facing_errors_have_no_paths() -> None:
    msg = str(DatasetUnavailableError().user_message)
    assert "observations.jsonl" not in msg
    assert "/" not in msg or "⚠️" in msg
    assert "Traceback" not in msg


@pytest.mark.asyncio
async def test_handlers_start_help_with_mocks() -> None:
    from src.telegram_bot.handlers import cmd_help, cmd_start

    update = MagicMock()
    update.callback_query = None
    update.effective_chat.id = 1
    update.effective_message.reply_text = MagicMock()
    # reply_text is async in PTB — make it awaitable
    async def _reply_text(*a, **k):
        return None

    update.effective_message.reply_text = _reply_text

    from src.telegram_bot.five_parreh_events import InMemoryFiveParrehEventSource

    context = MagicMock()
    context.application.bot_data = {
        "api_client": MagicMock(),
        "sessions": SessionStore(),
        "settings": TelegramBotSettings(telegram_bot_token="t", api_base_url="http://x"),
        "five_parreh_events": InMemoryFiveParrehEventSource([]),
    }
    await cmd_start(update, context)
    await cmd_help(update, context)


@pytest.mark.asyncio
async def test_handlers_races_predict_horse_mocked() -> None:
    from src.telegram_bot.five_parreh_events import InMemoryFiveParrehEventSource
    from src.telegram_bot.handlers import cmd_horse, cmd_predict, cmd_races

    client = MagicMock()
    client.list_races.return_value = {
        "total": 1,
        "races": [{"race_id": 3393, "track": "گنبد", "race_date": "2026-01-01", "field_size": 8}],
    }
    client.get_race_prediction.return_value = {
        "race_id": 3393,
        "prediction": [{"rank": 1, "horse_id": 1, "horse_name": "A", "score": 12.5, "probability": None}],
    }
    client.get_horse.return_value = {"horse_id": 3470, "observation_count": 2, "evidence": [], "warnings": []}

    async def _reply_text(*a, **k):
        return None

    update = MagicMock()
    update.callback_query = None
    update.effective_chat.id = 7
    update.effective_message.reply_text = _reply_text
    context = MagicMock()
    context.args = []
    context.application.bot_data = {
        "api_client": client,
        "sessions": SessionStore(),
        "settings": TelegramBotSettings(
            telegram_bot_token="t",
            api_base_url="http://x",
            telegram_races_page_size=10,
        ),
        "five_parreh_events": InMemoryFiveParrehEventSource([]),
    }
    await cmd_races(update, context)
    client.list_races.assert_called()

    context.args = ["3393"]
    await cmd_predict(update, context)
    client.get_race_prediction.assert_called()

    context.args = ["3470"]
    await cmd_horse(update, context)
    client.get_horse.assert_called_with("3470")
