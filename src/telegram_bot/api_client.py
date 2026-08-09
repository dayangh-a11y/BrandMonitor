"""HTTP client for Prediction / Five-Parreh API. No business logic duplication."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from src.telegram_bot.errors import (
    ApiUnavailableError,
    DatasetUnavailableError,
    HorseNotFoundError,
    RaceNotFoundError,
    TelegramBotError,
    ValidationUserError,
)


class PredictionApiClient:
    """Thin HTTP wrapper. All bot→API traffic goes through this class."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PredictionApiClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not path.startswith("/"):
            raise ValidationUserError("⚠️ مسیر درخواست نامعتبر است.")
        # Prevent open redirects / host injection — always relative to base_url.
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException:
            logger.warning("API timeout method={} path={}", method, path)
            raise ApiUnavailableError() from None
        except httpx.HTTPError as exc:
            logger.warning("API connection error method={} path={} err={}", method, path, type(exc).__name__)
            raise ApiUnavailableError() from None

        if response.status_code == 404:
            if path.startswith("/horses/"):
                raise HorseNotFoundError()
            raise RaceNotFoundError()
        if response.status_code == 503:
            detail = ""
            try:
                detail = str(response.json().get("detail") or "")
            except Exception:  # noqa: BLE001
                detail = response.text[:200]
            if "PRODUCTION BLOCKER" in detail or "observations" in detail.lower():
                raise DatasetUnavailableError()
            raise ApiUnavailableError()
        if response.status_code == 422:
            raise ValidationUserError("⚠️ ورودی نامعتبر است. لطفاً دوباره بررسی کنید.")
        if response.status_code >= 500:
            logger.error("API server error status={} path={}", response.status_code, path)
            raise ApiUnavailableError()
        if response.status_code >= 400:
            logger.warning("API client error status={} path={}", response.status_code, path)
            raise TelegramBotError("⚠️ درخواست قابل پردازش نیست.")

        try:
            return response.json()
        except Exception:  # noqa: BLE001
            logger.error("API returned non-JSON path={}", path)
            raise ApiUnavailableError() from None

    def get_health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_races(self, *, limit: int = 30, offset: int = 0) -> dict[str, Any]:
        return self._request("GET", "/races", params={"limit": limit, "offset": offset})

    def get_race(self, race_id: int | str) -> dict[str, Any]:
        rid = _safe_id(race_id, "race")
        return self._request("GET", f"/races/{rid}")

    def get_race_prediction(self, race_id: int | str, *, baseline: str = "A") -> dict[str, Any]:
        rid = _safe_id(race_id, "race")
        baseline = (baseline or "A").upper()
        if baseline not in {"A", "B", "C", "D"}:
            raise ValidationUserError("⚠️ پایهٔ پیش‌بینی نامعتبر است.")
        return self._request(
            "GET",
            f"/races/{rid}/prediction",
            params={"baseline": baseline},
        )

    def get_horse(self, horse_id: int | str) -> dict[str, Any]:
        hid = _safe_id(horse_id, "horse")
        return self._request("GET", f"/horses/{hid}")

    def generate_five_parreh(
        self,
        races: list[dict[str, Any]],
        *,
        price_per_combination: int | float | None = None,
        include_combinations: bool = True,
        max_combinations_in_response: int = 50,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "races": races,
            "include_combinations": include_combinations,
            "max_combinations_in_response": max_combinations_in_response,
        }
        if price_per_combination is not None:
            body["price_per_combination"] = price_per_combination
        return self._request("POST", "/five-parreh/combinations", json=body)


def _safe_id(value: int | str, kind: str) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationUserError(
            "⚠️ شناسهٔ مسابقه نامعتبر است." if kind == "race" else "⚠️ شناسهٔ اسب نامعتبر است."
        ) from None
    if n < 0:
        raise ValidationUserError(
            "⚠️ شناسهٔ مسابقه نامعتبر است." if kind == "race" else "⚠️ شناسهٔ اسب نامعتبر است."
        )
    return n
