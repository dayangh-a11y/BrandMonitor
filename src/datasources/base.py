"""DataSource interface — all site-specific collectors implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import HorseHistory, HorseProfile, Race, RaceListItem


class DataSource(ABC):
    """
    Abstract contract for race-data providers.

    Application code must depend only on this interface, never on a concrete
    website implementation.
    """

    name: str

    @abstractmethod
    def collect_race(self, url: str) -> Race:
        """Collect a single race (card + runners / results) from a race URL."""

    @abstractmethod
    def collect_horse(self, url: str) -> HorseProfile:
        """Collect horse profile metadata from a horse profile URL."""

    @abstractmethod
    def collect_horse_history(self, url: str) -> HorseHistory:
        """Collect full race history for a horse from its profile URL."""

    @abstractmethod
    def collect_race_list(self, url: str | None = None) -> list[RaceListItem]:
        """Collect available race listing entries from an index / calendar URL."""

    def close(self) -> None:
        """Release any held resources (browser, sessions). Optional."""
