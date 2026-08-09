"""Five-Parreh *event* helpers — thin adapter over ``src.race_program``.

A Five-Parreh event is a FUTURE betting product: exactly five designated
races that have not started yet, declared in the shared race program.

This module does NOT:
- generate Cartesian products (that stays in ``src.five_parreh``)
- run prediction / scoring / rank_race
- invent events from race_id arithmetic or historical freeze races
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from src.race_program.loader import parse_program_document
from src.race_program.models import FiveParrehProgramEvent, ProgramRace
from src.race_program.service import RaceProgramService, load_race_program

REQUIRED_RACE_COUNT = 5


@dataclass(frozen=True, slots=True)
class FiveParrehEventRace:
    race_id: str
    label: str
    scheduled_start: datetime

    def is_future(self, *, now: datetime) -> bool:
        return self.scheduled_start > now


@dataclass(frozen=True, slots=True)
class FiveParrehEvent:
    event_id: str
    display_date: str
    track: str
    title: str
    races: tuple[FiveParrehEventRace, ...]
    city: str | None = None
    meeting_id: str | None = None

    @property
    def race_ids(self) -> list[str]:
        return [r.race_id for r in self.races]

    def is_future(self, *, now: datetime) -> bool:
        if len(self.races) != REQUIRED_RACE_COUNT:
            return False
        return all(r.is_future(now=now) for r in self.races)


class FiveParrehEventSource(Protocol):
    def list_events(self) -> list[FiveParrehEvent]:
        """Return declared events (may include past); caller filters to future."""


def _to_telegram_race(race: ProgramRace) -> FiveParrehEventRace | None:
    if race.scheduled_start is None:
        return None
    return FiveParrehEventRace(
        race_id=race.race_id,
        label=race.label,
        scheduled_start=race.scheduled_start,
    )


def _to_telegram_event(event: FiveParrehProgramEvent) -> FiveParrehEvent | None:
    races: list[FiveParrehEventRace] = []
    for race in event.races:
        converted = _to_telegram_race(race)
        if converted is None:
            return None
        races.append(converted)
    return FiveParrehEvent(
        event_id=event.event_id,
        display_date=event.display_date,
        track=event.track,
        title=event.title,
        city=event.city,
        meeting_id=event.meeting_id,
        races=tuple(races),
    )


class JsonFiveParrehEventSource:
    """Load from the shared race-program JSON (legacy ``events`` still accepted)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def list_events(self) -> list[FiveParrehEvent]:
        service = load_race_program(self.path)
        out: list[FiveParrehEvent] = []
        for event in service.events:
            converted = _to_telegram_event(event)
            if converted is not None:
                out.append(converted)
        return out


class InMemoryFiveParrehEventSource:
    def __init__(self, events: list[FiveParrehEvent] | None = None) -> None:
        self._events = list(events or [])

    def list_events(self) -> list[FiveParrehEvent]:
        return list(self._events)


def parse_events_document(raw: Any) -> list[FiveParrehEvent]:
    """Parse legacy or unified race-program documents into Telegram event objects."""
    service = RaceProgramService.from_document(raw)
    out: list[FiveParrehEvent] = []
    for event in service.events:
        converted = _to_telegram_event(event)
        if converted is not None:
            out.append(converted)
    return out


def parse_event(raw: dict[str, Any]) -> FiveParrehEvent:
    events = parse_events_document({"events": [raw]})
    if not events:
        raise ValueError("could not parse event (missing scheduled_start?)")
    return events[0]


def event_has_exactly_five_races(event: FiveParrehEvent) -> bool:
    return len(event.races) == REQUIRED_RACE_COUNT


def reject_if_any_race_completed(event: FiveParrehEvent, *, now: datetime) -> bool:
    return any(not r.is_future(now=now) for r in event.races)


def list_future_events(
    source: FiveParrehEventSource,
    *,
    now: datetime | None = None,
) -> list[FiveParrehEvent]:
    """Future-only events with exactly five designated races (shared eligibility rule)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    out: list[FiveParrehEvent] = []
    for event in source.list_events():
        if not event_has_exactly_five_races(event):
            continue
        if reject_if_any_race_completed(event, now=now):
            continue
        if not event.is_future(now=now):
            continue
        out.append(event)
    return sorted(out, key=lambda e: (e.races[0].scheduled_start, e.event_id))


def get_event_by_id(
    source: FiveParrehEventSource,
    event_id: str,
    *,
    now: datetime | None = None,
) -> FiveParrehEvent | None:
    event_id = str(event_id).strip()
    for event in list_future_events(source, now=now):
        if event.event_id == event_id:
            return event
    return None


def event_from_api_payload(payload: dict[str, Any]) -> FiveParrehEvent:
    """Build a Telegram event view from ``GET /race-program/five-parreh/{id}``."""
    races: list[FiveParrehEventRace] = []
    for i, item in enumerate(payload.get("races") or []):
        if not isinstance(item, dict):
            continue
        start_raw = item.get("scheduled_start")
        if not start_raw:
            continue
        text = str(start_raw)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        start = datetime.fromisoformat(text)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        races.append(
            FiveParrehEventRace(
                race_id=str(item.get("race_id") or ""),
                label=str(item.get("label") or f"کورس {item.get('race_number') or i + 1}"),
                scheduled_start=start.astimezone(timezone.utc),
            )
        )
    return FiveParrehEvent(
        event_id=str(payload.get("event_id") or ""),
        display_date=str(payload.get("display_date") or "—"),
        track=str(payload.get("track") or "—"),
        city=(None if payload.get("city") is None else str(payload.get("city"))),
        title=str(payload.get("title") or "پنج‌پره"),
        meeting_id=(None if payload.get("meeting_id") is None else str(payload.get("meeting_id"))),
        races=tuple(races),
    )


# Re-export for clarity that discovery shares race_program parsing.
__all__ = [
    "FiveParrehEvent",
    "FiveParrehEventRace",
    "FiveParrehEventSource",
    "InMemoryFiveParrehEventSource",
    "JsonFiveParrehEventSource",
    "REQUIRED_RACE_COUNT",
    "event_from_api_payload",
    "event_has_exactly_five_races",
    "get_event_by_id",
    "list_future_events",
    "parse_event",
    "parse_events_document",
    "parse_program_document",
    "reject_if_any_race_completed",
]
