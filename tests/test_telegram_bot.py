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
    assert "Score: 87.4" in text
    assert "%" not in text.split("Score:")[1][:10]
    assert "87%" not in text


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
    assert "احتمال برد تولید نمی‌کند" in horse

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
    assert s.step == "pick_race"
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
    context.application.bot_data = {
        "api_client": MagicMock(),
        "sessions": SessionStore(),
        "settings": TelegramBotSettings(telegram_bot_token="t", api_base_url="http://x"),
    }
    await cmd_start(update, context)
    await cmd_help(update, context)


@pytest.mark.asyncio
async def test_handlers_races_predict_horse_mocked() -> None:
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
    }
    await cmd_races(update, context)
    client.list_races.assert_called()

    context.args = ["3393"]
    await cmd_predict(update, context)
    client.get_race_prediction.assert_called()

    context.args = ["3470"]
    await cmd_horse(update, context)
    client.get_horse.assert_called_with("3470")
