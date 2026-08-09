"""Future Five-Parreh *event* domain for Telegram (not the combination engine).

A Five-Parreh event is a FUTURE betting product: a meeting-linked event with
exactly five designated races that have not started yet.

This module does NOT:
- generate Cartesian products (that stays in ``src.five_parreh``)
- run prediction / scoring / rank_race
- invent events from race_id arithmetic or historical freeze races
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


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

    @property
    def race_ids(self) -> list[str]:
        return [r.race_id for r in self.races]

    def is_future(self, *, now: datetime) -> bool:
        """Eligible only when all designated races are still in the future."""
        if len(self.races) != REQUIRED_RACE_COUNT:
            return False
        return all(r.is_future(now=now) for r in self.races)


class FiveParrehEventSource(Protocol):
    """Race-program / ops data source for declared Five-Parreh events."""

    def list_events(self) -> list[FiveParrehEvent]:
        """Return declared events (may include past); caller filters to future."""


class JsonFiveParrehEventSource:
    """Load events from a JSON file. Missing file ⇒ empty (no fabricated events)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def list_events(self) -> list[FiveParrehEvent]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return parse_events_document(raw)


class InMemoryFiveParrehEventSource:
    def __init__(self, events: list[FiveParrehEvent] | None = None) -> None:
        self._events = list(events or [])

    def list_events(self) -> list[FiveParrehEvent]:
        return list(self._events)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_event(raw: dict[str, Any]) -> FiveParrehEvent:
    event_id = str(raw.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("event_id is required")
    races_raw = raw.get("races")
    if not isinstance(races_raw, list):
        raise ValueError(f"event {event_id}: races must be a list")
    races: list[FiveParrehEventRace] = []
    for i, item in enumerate(races_raw):
        if not isinstance(item, dict):
            raise ValueError(f"event {event_id}: race[{i}] must be an object")
        rid = str(item.get("race_id") or "").strip()
        if not rid:
            raise ValueError(f"event {event_id}: race[{i}] missing race_id")
        label = str(item.get("label") or f"کورس {i + 1}").strip()
        if "scheduled_start" not in item:
            raise ValueError(f"event {event_id}: race {rid} missing scheduled_start")
        races.append(
            FiveParrehEventRace(
                race_id=rid,
                label=label,
                scheduled_start=_parse_dt(item["scheduled_start"]),
            )
        )
    return FiveParrehEvent(
        event_id=event_id,
        display_date=str(raw.get("display_date") or "").strip() or "—",
        track=str(raw.get("track") or "").strip() or "—",
        city=(None if raw.get("city") is None else str(raw.get("city")).strip()),
        title=str(raw.get("title") or "پنج‌پره").strip() or "پنج‌پره",
        races=tuple(races),
    )


def parse_events_document(raw: Any) -> list[FiveParrehEvent]:
    if not isinstance(raw, dict):
        raise ValueError("events document must be an object")
    items = raw.get("events")
    if items is None:
        items = []
    if not isinstance(items, list):
        raise ValueError("events must be a list")
    return [parse_event(item) for item in items if isinstance(item, dict)]


def event_has_exactly_five_races(event: FiveParrehEvent) -> bool:
    return len(event.races) == REQUIRED_RACE_COUNT


def reject_if_any_race_completed(event: FiveParrehEvent, *, now: datetime) -> bool:
    """Return True if event must be rejected (any race already started/completed)."""
    return any(not r.is_future(now=now) for r in event.races)


def list_future_events(
    source: FiveParrehEventSource,
    *,
    now: datetime | None = None,
) -> list[FiveParrehEvent]:
    """Future-only events with exactly five designated races.

    Does not invent events from freeze race lists or race_id sequences.
    """
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
    # Stable order: soonest first race, then event_id
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
