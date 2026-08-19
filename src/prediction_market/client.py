"""HTTP client for api-mosharekat.asbdavani.app (public endpoints)."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from loguru import logger

DEFAULT_BASE = "https://api-mosharekat.asbdavani.app/api/v1"
DEFAULT_ORIGIN = "https://mosharekat.asbdavani.app"


class MosharekatClient:
    """Thin JSON client with retries. Does not hardcode response field names."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE,
        origin: str = DEFAULT_ORIGIN,
        timeout: float = 30.0,
        max_retries: int = 5,
        sleep_base: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.origin = origin
        self.timeout = timeout
        self.max_retries = max_retries
        self.sleep_base = sleep_base

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        qs = f"?{urlencode(params)}" if params else ""
        if path.startswith("http"):
            url = path + qs
        else:
            url = f"{self.base_url}/{path.lstrip('/')}{qs}"
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                req = Request(
                    url,
                    headers={
                        "User-Agent": "BrandMonitor-PredictionMarket/1.0",
                        "Accept": "application/json",
                        "Origin": self.origin,
                        "Referer": f"{self.origin}/",
                    },
                )
                with urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8")
                return json.loads(body)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                last_err = exc
                wait = self.sleep_base * (2 ** (attempt - 1))
                logger.warning("mosharekat GET {} failed attempt {}: {}", url, attempt, exc)
                time.sleep(wait)
        raise RuntimeError(f"Failed GET {url}: {last_err}")

    def list_race_days(self, *, limit: int = 500) -> list[dict[str, Any]]:
        payload = self.get("/races/days", {"limit": limit})
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict):
            days = data.get("race_days")
            if isinstance(days, list):
                return [d for d in days if isinstance(d, dict)]
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []

    def fetch_racecard(self, day_id: int | str) -> dict[str, Any]:
        return self.get("/races/racecard", {"day_id": day_id})

    def fetch_odds(self, race_id: int | str) -> dict[str, Any]:
        return self.get(f"/pools/race/{race_id}/odds")

    def fetch_survey_statistics(self, race_id: int | str) -> dict[str, Any]:
        return self.get(f"/races/{race_id}/survey-statistics")
