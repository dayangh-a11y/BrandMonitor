"""Race-program models. ``race_id`` / ``meeting_id`` are internal identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.race_program.eligibility import is_eligible_for_prediction


STATUS_SCHEDULED = "scheduled"
STATUS_UNKNOWN_TIME = "unknown_time"
STATUS_STARTED = "started"
STATUS_COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ProgramRace:
    race_id: str
    race_number: int
    label: str
    scheduled_start: datetime | None
    status: str = STATUS_SCHEDULED

    def is_eligible(self, *, now: datetime) -> bool:
        return is_eligible_for_prediction(self.scheduled_start, now=now)

    def to_public_dict(self) -> dict[str, Any]:
        """API payload: includes internal ids for clients; UI must not require typing them."""
        return {
            "race_id": self.race_id,
            "race_number": self.race_number,
            "label": self.label,
            "scheduled_start": (
                self.scheduled_start.isoformat() if self.scheduled_start is not None else None
            ),
            "status": self.status,
            "time_known": self.scheduled_start is not None,
            "eligible_for_prediction": False,  # filled by service with `now`
        }


@dataclass(frozen=True, slots=True)
class Meeting:
    meeting_id: str
    display_date: str
    track: str
    races: tuple[ProgramRace, ...]
    city: str | None = None

    @property
    def location(self) -> str:
        return (self.city or self.track or "—").strip() or "—"

    def to_public_dict(self, *, include_races: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "meeting_id": self.meeting_id,
            "display_date": self.display_date,
            "track": self.track,
            "city": self.city,
            "location": self.location,
        }
        if include_races:
            payload["races"] = [r.to_public_dict() for r in self.races]
            payload["race_count"] = len(self.races)
        return payload


@dataclass(frozen=True, slots=True)
class FiveParrehProgramEvent:
    """Declared Five-Parreh product over exactly five future program races."""

    event_id: str
    display_date: str
    track: str
    title: str
    races: tuple[ProgramRace, ...]
    meeting_id: str | None = None
    city: str | None = None

    @property
    def race_ids(self) -> list[str]:
        return [r.race_id for r in self.races]

    @property
    def location(self) -> str:
        return (self.city or self.track or "—").strip() or "—"

    def is_future(self, *, now: datetime) -> bool:
        if len(self.races) != 5:
            return False
        return all(r.is_eligible(now=now) for r in self.races)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "meeting_id": self.meeting_id,
            "display_date": self.display_date,
            "track": self.track,
            "city": self.city,
            "location": self.location,
            "title": self.title,
            "races": [r.to_public_dict() for r in self.races],
        }
