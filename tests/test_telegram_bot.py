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
        },
        meta={
            "race_number": 3,
            "display_date": "جمعه ۳۰ مرداد ۱۴۰۵",
            "track": "مشهد",
        },
    )
    assert "🏇 پیش‌بینی کورس 3" in text
    assert "📅 جمعه ۳۰ مرداد ۱۴۰۵" in text
    assert "📍 مشهد" in text
    assert "601" not in text  # race_id must stay internal in Telegram UX
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


def test_format_upcoming_empty_and_meetings() -> None:
    empty = fmt.format_upcoming_meetings(
        {"meetings": [], "message": "در ۷ روز آینده مسابقه‌ای برای پیش‌بینی ثبت نشده است."}
    )
    assert "۷ روز آینده" in empty
    text = fmt.format_upcoming_meetings(
        {
            "meetings": [
                {
                    "meeting_id": "msh-future",
                    "display_date": "جمعه ۳۰ مرداد ۱۴۰۵",
                    "track": "مشهد",
                    "location": "مشهد",
                }
            ]
        }
    )
    assert "مسابقات آینده" in text
    assert "مشهد" in text
    assert "msh-future" not in text
    races = fmt.format_meeting_races(
        {
            "display_date": "جمعه ۳۰ مرداد ۱۴۰۵",
            "location": "مشهد",
            "races": [
                {"race_id": "3393", "race_number": 1, "label": "کورس ۱"},
                {"race_id": "3394", "race_number": 2, "label": "کورس ۲"},
            ],
        }
    )
    assert "مسابقات مشهد" in text or "مسابقات مشهد" in races
    assert "کورس ۱" in races
    assert "3393" not in races


def test_format_horse_and_fiveparreh() -> None:
    horse = fmt.format_horse(
        {
            "horse_id": 3470,
            "horse_name": "انفجار ایگدری",
            "observation_count": 9,
            "evidence": [{"metric": "career_win_rate", "value": 0.1}],
            "warnings": ["low_feature_coverage"],
        }
    )
    assert "انفجار ایگدری" in horse
    assert "شناسه" not in horse
    assert "3470" not in horse  # horse_id must stay internal in Telegram UX
    assert "low_feature_coverage" not in horse
    assert "⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد." in horse
    assert "ℹ️ امتیاز، احتمال برد نیست." in horse

    search = fmt.format_horse_search_results(
        {
            "horses": [
                {"horse_id": 3239, "horse_name": "شیرین صحرا", "breed": "Thoroughbred"},
            ]
        }
    )
    assert "نتایج جستجوی اسب" in search
    assert "شیرین صحرا" in search
    assert "3239" not in search
    assert "اسبی با این نام پیدا نشد" in fmt.format_horse_search_results({"horses": []})

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
    assert "9000" not in detail  # race_id must stay internal


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

    context = MagicMock()
    from src.telegram_bot.state import HorseLookupStore

    context.application.bot_data = {
        "api_client": MagicMock(),
        "sessions": SessionStore(),
        "settings": TelegramBotSettings(telegram_bot_token="t", api_base_url="http://x"),
        "horse_lookup": HorseLookupStore(),
    }
    await cmd_start(update, context)
    await cmd_help(update, context)


@pytest.mark.asyncio
async def test_handlers_predict_meeting_flow_and_horse() -> None:
    from src.telegram_bot.handlers import cmd_horse, cmd_predict, on_callback
    from src.telegram_bot.keyboards import meeting_races_keyboard, upcoming_meetings_keyboard
    from src.telegram_bot.state import HorseLookupStore

    client = MagicMock()
    client.list_upcoming_meetings.return_value = {
        "days": 7,
        "count": 1,
        "meetings": [
            {
                "meeting_id": "msh-future",
                "display_date": "جمعه ۳۰ مرداد ۱۴۰۵",
                "track": "مشهد",
                "location": "مشهد",
                "races": [
                    {
                        "race_id": "3393",
                        "race_number": 1,
                        "label": "کورس ۱",
                        "eligible_for_prediction": True,
                    }
                ],
            }
        ],
        "message": None,
    }
    client.get_upcoming_meeting.return_value = {
        "meeting_id": "msh-future",
        "display_date": "جمعه ۳۰ مرداد ۱۴۰۵",
        "track": "مشهد",
        "location": "مشهد",
        "races": [
            {
                "race_id": "3393",
                "race_number": 3,
                "label": "کورس ۳",
                "eligible_for_prediction": True,
            }
        ],
    }
    client.get_race_prediction.return_value = {
        "race_id": 3393,
        "prediction": [{"rank": 1, "horse_id": 1, "horse_name": "A", "score": 12.5, "probability": None}],
    }
    client.search_horses.return_value = {
        "query": "دنزی بوی",
        "count": 1,
        "horses": [{"horse_id": 3239, "horse_name": "شیرین صحرا", "breed": "Thoroughbred"}],
    }
    client.get_horse.return_value = {
        "horse_id": 3239,
        "horse_name": "شیرین صحرا",
        "observation_count": 2,
        "evidence": [],
        "warnings": [],
    }

    replies: list[str] = []

    async def _reply_text(text, **k):
        replies.append(text)
        return None

    update = MagicMock()
    update.callback_query = None
    update.effective_chat.id = 7
    update.effective_user.id = 7
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
        "horse_lookup": HorseLookupStore(),
        "predict_meta": {},
    }

    await cmd_predict(update, context)
    client.list_upcoming_meetings.assert_called_with(days=7)
    client.list_races.assert_not_called()
    assert any("مسابقات آینده" in r for r in replies)
    assert all("3393" not in r for r in replies)
    kb = upcoming_meetings_keyboard(client.list_upcoming_meetings.return_value["meetings"])
    labels = [b.text for row in kb.inline_keyboard for b in row if b.callback_data.startswith("mtg:")]
    assert labels == ["مشهد — جمعه ۳۰ مرداد ۱۴۰۵"]

    update.callback_query = MagicMock()
    update.callback_query.data = "mtg:msh-future"
    update.callback_query.message = MagicMock()

    async def _answer(*a, **k):
        return None

    async def _reply_cb(text, **k):
        replies.append(text)
        return None

    update.callback_query.answer = _answer
    update.callback_query.message.reply_text = _reply_cb
    await on_callback(update, context)
    client.get_upcoming_meeting.assert_called_with("msh-future")
    assert any("مسابقات مشهد" in r for r in replies)
    race_kb = meeting_races_keyboard(client.get_upcoming_meeting.return_value)
    race_labels = [b.text for row in race_kb.inline_keyboard for b in row if b.callback_data.startswith("prd:")]
    assert race_labels == ["کورس ۳"]
    assert all("3393" not in t for t in race_labels)

    update.callback_query.data = "prd:3393"
    await on_callback(update, context)
    client.get_race_prediction.assert_called_with("3393")
    assert any("پیش‌بینی کورس 3" in r for r in replies)
    assert all("3393" not in r for r in replies if "پیش‌بینی" in r)

    context.args = ["دنزی", "بوی"]
    await cmd_horse(update, context)
    client.search_horses.assert_called()
    client.get_horse.assert_not_called()

    update.callback_query.data = "horse_sel:3239"
    await on_callback(update, context)
    client.get_horse.assert_called_with("3239")


@pytest.mark.asyncio
async def test_predict_and_fiveparreh_use_same_api_race_program_source() -> None:
    from src.telegram_bot.handlers import cmd_fiveparreh, cmd_predict
    from src.telegram_bot.state import HorseLookupStore

    client = MagicMock()
    client.list_upcoming_meetings.return_value = {
        "days": 7,
        "count": 0,
        "meetings": [],
        "message": "در ۷ روز آینده مسابقه‌ای برای پیش‌بینی ثبت نشده است.",
    }
    client.list_five_parreh_events.return_value = {
        "count": 0,
        "events": [],
        "message": "در حال حاضر رویداد پنج‌پرهٔ آینده‌ای ثبت نشده است.",
    }

    async def _reply_text(text, **k):
        return None

    update = MagicMock()
    update.callback_query = None
    update.effective_chat.id = 3
    update.effective_user.id = 3
    update.effective_message.reply_text = _reply_text
    context = MagicMock()
    context.args = []
    context.application.bot_data = {
        "api_client": client,
        "sessions": SessionStore(),
        "settings": TelegramBotSettings(telegram_bot_token="t", api_base_url="http://x"),
        "horse_lookup": HorseLookupStore(),
    }
    await cmd_predict(update, context)
    await cmd_fiveparreh(update, context)
    client.list_upcoming_meetings.assert_called_once()
    client.list_five_parreh_events.assert_called_once()
    # Must not fall back to historical freeze race list or local file source.
    client.list_races.assert_not_called()


def test_api_client_search_horses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/horses/search"
        assert request.url.params["name"] == "دنزی بوی"
        return httpx.Response(
            200,
            json={
                "query": request.url.params["name"],
                "count": 1,
                "horses": [{"horse_id": 3239, "horse_name": "شیرین صحرا", "breed": "Thoroughbred"}],
            },
        )

    client = PredictionApiClient("http://test")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    out = client.search_horses("دنزی بوی")
    assert out["horses"][0]["horse_name"] == "شیرین صحرا"
    client.close()


@pytest.mark.asyncio
async def test_horse_flow_text_prompt_then_select() -> None:
    from src.telegram_bot.handlers import cmd_horse, on_callback, on_text_message
    from src.telegram_bot.keyboards import horse_search_keyboard
    from src.telegram_bot.state import HorseLookupStore

    client = MagicMock()
    client.search_horses.return_value = {
        "query": "صحرا",
        "count": 2,
        "horses": [
            {"horse_id": 3239, "horse_name": "شیرین صحرا", "breed": "Thoroughbred"},
            {"horse_id": 9999, "horse_name": "صحرا نورد", "breed": "Thoroughbred"},
        ],
    }
    client.get_horse.return_value = {
        "horse_id": 3239,
        "horse_name": "شیرین صحرا",
        "observation_count": 1,
        "evidence": [],
        "warnings": [],
    }

    replies: list[str] = []

    async def _reply_text(text, **k):
        replies.append(text)
        return None

    update = MagicMock()
    update.callback_query = None
    update.effective_chat.id = 11
    update.effective_user.id = 11
    update.effective_message.reply_text = _reply_text
    update.effective_message.text = None
    context = MagicMock()
    context.args = []
    lookup = HorseLookupStore()
    context.application.bot_data = {
        "api_client": client,
        "sessions": SessionStore(),
        "settings": TelegramBotSettings(telegram_bot_token="t", api_base_url="http://x"),
        "horse_lookup": lookup,
    }

    await cmd_horse(update, context)
    assert lookup.is_waiting(11)
    assert any("نام اسب" in r for r in replies)
    client.search_horses.assert_not_called()

    update.effective_message.text = "صحرا"
    await on_text_message(update, context)
    assert not lookup.is_waiting(11)
    client.search_horses.assert_called_with("صحرا", limit=15)
    assert any("نتایج جستجوی اسب" in r for r in replies)
    assert all("3239" not in r and "9999" not in r for r in replies)

    kb = horse_search_keyboard(client.search_horses.return_value["horses"])
    labels = [btn.text for row in kb.inline_keyboard for btn in row if btn.callback_data.startswith("horse_sel:")]
    assert labels == ["شیرین صحرا", "صحرا نورد"]
    assert all("3239" not in t and "9999" not in t for t in labels)

    update.callback_query = MagicMock()
    update.callback_query.data = "horse_sel:3239"
    update.callback_query.message = MagicMock()

    async def _answer(*a, **k):
        return None

    async def _reply_cb(text, **k):
        replies.append(text)
        return None

    update.callback_query.answer = _answer
    update.callback_query.message.reply_text = _reply_cb
    await on_callback(update, context)
    client.get_horse.assert_called_with("3239")
    assert any("تحلیل شیرین صحرا" in r for r in replies)
    assert all("3239" not in r for r in replies if "تحلیل" in r)


def test_horse_directory_search_units() -> None:
    from src.prediction_engine.horse_directory import HorseNameDirectory, HorseNameRecord

    d = HorseNameDirectory(
        [
            HorseNameRecord(3239, "شیرین صحرا", breed="Thoroughbred", aliases=("دنزی بوی", "Danzig Boy")),
            HorseNameRecord(3450, "گل مارال", breed="Thoroughbred"),
            HorseNameRecord(3470, "انفجار ایگدری"),
        ]
    )
    exact = d.search("انفجار ایگدری")
    assert exact and exact[0].horse_id == 3470
    partial = d.search("مارال")
    assert any(r.horse_id == 3450 for r in partial)
    multi = d.search("صحرا")
    assert multi
    assert d.search("ناموجود") == []
