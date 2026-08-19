"""asbdavani.app DataSource implementation."""

from __future__ import annotations

from loguru import logger

from src.asbdavani.constants import BASE_URL, RACECARDS_PATH, absolute_url
from src.asbdavani.parsers.horse import parse_horse_history_html, parse_horse_profile_html
from src.asbdavani.parsers.race import parse_race_html, parse_race_list_html
from src.browser import BrowserClient
from src.datasources.base import DataSource
from src.models import HorseHistory, HorseProfile, Race, RaceListItem
from src.utils.settings import Settings, get_settings


class AsbdavaniDataSource(DataSource):
    """Collect race / horse data from asbdavani.app via Playwright + parsers."""

    name = "asbdavani"

    def __init__(
        self,
        browser: BrowserClient | None = None,
        settings: Settings | None = None,
        *,
        owns_browser: bool | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if browser is None:
            self.browser = BrowserClient(self.settings)
            self._owns_browser = True
        else:
            self.browser = browser
            self._owns_browser = False if owns_browser is None else owns_browser

    def _html(self, url: str) -> str:
        return self.browser.fetch_html(url)

    def collect_race(self, url: str) -> Race:
        logger.info("[{}] collect_race {}", self.name, url)
        html = self._html(url)
        race = parse_race_html(html, url)
        logger.info(
            "[{}] race={!r} horses={}",
            self.name,
            race.race,
            len(race.horses),
        )
        return race

    def collect_horse(self, url: str) -> HorseProfile:
        logger.info("[{}] collect_horse {}", self.name, url)
        html = self._html(url)
        return parse_horse_profile_html(html, url)

    def collect_horse_history(self, url: str) -> HorseHistory:
        logger.info("[{}] collect_horse_history {}", self.name, url)
        html = self._html(url)
        history = parse_horse_history_html(html, url)
        logger.info(
            "[{}] horse={!r} history_rows={}",
            self.name,
            history.horse.name,
            len(history.history),
        )
        return history

    def collect_race_list(self, url: str | None = None) -> list[RaceListItem]:
        target = url or absolute_url(RACECARDS_PATH)
        logger.info("[{}] collect_race_list {}", self.name, target)
        html = self._html(target)
        raw_items = parse_race_list_html(html, BASE_URL)
        return [
            RaceListItem(
                title=item.get("title") or None,
                url=item["url"],
                sourceId=item.get("sourceId") or None,
            )
            for item in raw_items
        ]

    def close(self) -> None:
        if self._owns_browser:
            self.browser.close()


def register() -> None:
    from src.datasources.registry import register_datasource

    register_datasource("asbdavani", AsbdavaniDataSource)
