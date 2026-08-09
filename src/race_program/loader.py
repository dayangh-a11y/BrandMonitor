"""Load race-program JSON documents (no DB access)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.race_program.models import (
    STATUS_SCHEDULED,
    STATUS_UNKNOWN_TIME,
    FiveParrehProgramEvent,
    Meeting,
    ProgramRace,
)


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _race_from_dict(item: dict[str, Any], *, index: int) -> ProgramRace:
    rid = str(item.get("race_id") or "").strip()
    if not rid:
        raise ValueError(f"race[{index}] missing race_id")
    try:
        race_number = int(item.get("race_number") if item.get("race_number") is not None else index + 1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"race {rid}: invalid race_number") from exc
    label = str(item.get("label") or f"کورس {race_number}").strip() or f"کورس {race_number}"
    scheduled = parse_datetime(item.get("scheduled_start") or item.get("scheduled_start_time"))
    status = str(item.get("status") or "").strip() or (
        STATUS_UNKNOWN_TIME if scheduled is None else STATUS_SCHEDULED
    )
    if scheduled is None:
        status = STATUS_UNKNOWN_TIME
    return ProgramRace(
        race_id=rid,
        race_number=race_number,
        label=label,
        scheduled_start=scheduled,
        status=status,
    )


def parse_meeting(raw: dict[str, Any]) -> Meeting:
    meeting_id = str(raw.get("meeting_id") or "").strip()
    if not meeting_id:
        raise ValueError("meeting_id is required")
    races_raw = raw.get("races")
    if not isinstance(races_raw, list) or not races_raw:
        raise ValueError(f"meeting {meeting_id}: races must be a non-empty list")
    races = [_race_from_dict(item, index=i) for i, item in enumerate(races_raw) if isinstance(item, dict)]
    if not races:
        raise ValueError(f"meeting {meeting_id}: no valid races")
    return Meeting(
        meeting_id=meeting_id,
        display_date=str(raw.get("display_date") or "").strip() or "—",
        track=str(raw.get("track") or "").strip() or "—",
        city=(None if raw.get("city") is None else str(raw.get("city")).strip()),
        races=tuple(races),
    )


def _meeting_from_legacy_event(raw: dict[str, Any]) -> Meeting:
    """Convert legacy Five-Parreh ``events[]`` entry into a meeting."""
    event_id = str(raw.get("event_id") or "").strip() or "legacy"
    races_raw = raw.get("races")
    if not isinstance(races_raw, list):
        raise ValueError(f"legacy event {event_id}: races must be a list")
    meeting_id = str(raw.get("meeting_id") or f"mtg-{event_id}").strip()
    races = []
    for i, item in enumerate(races_raw):
        if not isinstance(item, dict):
            continue
        races.append(_race_from_dict(item, index=i))
    return Meeting(
        meeting_id=meeting_id,
        display_date=str(raw.get("display_date") or "").strip() or "—",
        track=str(raw.get("track") or "").strip() or "—",
        city=(None if raw.get("city") is None else str(raw.get("city")).strip()),
        races=tuple(races),
    )


def parse_five_parreh_event(
    raw: dict[str, Any],
    *,
    meetings_by_id: dict[str, Meeting],
) -> FiveParrehProgramEvent:
    event_id = str(raw.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("event_id is required")

    # Prefer explicit races list (legacy + full declarations).
    if isinstance(raw.get("races"), list) and raw["races"]:
        races = [
            _race_from_dict(item, index=i)
            for i, item in enumerate(raw["races"])
            if isinstance(item, dict)
        ]
        meeting_id = (
            None if raw.get("meeting_id") is None else str(raw.get("meeting_id")).strip() or None
        )
        return FiveParrehProgramEvent(
            event_id=event_id,
            meeting_id=meeting_id,
            display_date=str(raw.get("display_date") or "").strip() or "—",
            track=str(raw.get("track") or "").strip() or "—",
            city=(None if raw.get("city") is None else str(raw.get("city")).strip()),
            title=str(raw.get("title") or "پنج‌پره").strip() or "پنج‌پره",
            races=tuple(races),
        )

    meeting_id = str(raw.get("meeting_id") or "").strip()
    if not meeting_id or meeting_id not in meetings_by_id:
        raise ValueError(f"event {event_id}: meeting_id required when races omitted")
    meeting = meetings_by_id[meeting_id]
    race_ids = raw.get("race_ids")
    if race_ids is None:
        # Default: first five races of the meeting (must be exactly five).
        selected = list(meeting.races)
    else:
        if not isinstance(race_ids, list):
            raise ValueError(f"event {event_id}: race_ids must be a list")
        by_id = {r.race_id: r for r in meeting.races}
        selected = []
        for rid in race_ids:
            key = str(rid).strip()
            if key not in by_id:
                raise ValueError(f"event {event_id}: race_id {key} not in meeting {meeting_id}")
            selected.append(by_id[key])
    return FiveParrehProgramEvent(
        event_id=event_id,
        meeting_id=meeting_id,
        display_date=str(raw.get("display_date") or meeting.display_date).strip() or meeting.display_date,
        track=str(raw.get("track") or meeting.track).strip() or meeting.track,
        city=(
            meeting.city
            if raw.get("city") is None
            else str(raw.get("city")).strip()
        ),
        title=str(raw.get("title") or "پنج‌پره").strip() or "پنج‌پره",
        races=tuple(selected),
    )


def parse_program_document(raw: Any) -> tuple[list[Meeting], list[FiveParrehProgramEvent]]:
    if not isinstance(raw, dict):
        raise ValueError("race program document must be an object")

    meetings: list[Meeting] = []
    if isinstance(raw.get("meetings"), list):
        for item in raw["meetings"]:
            if isinstance(item, dict):
                meetings.append(parse_meeting(item))

    # Legacy Five-Parreh-only documents: each event becomes a meeting + FP event.
    legacy_events = raw.get("events")
    if isinstance(legacy_events, list):
        for item in legacy_events:
            if not isinstance(item, dict):
                continue
            meeting = _meeting_from_legacy_event(item)
            # Avoid duplicate meeting_ids if both sections present.
            if all(m.meeting_id != meeting.meeting_id for m in meetings):
                meetings.append(meeting)

    by_id = {m.meeting_id: m for m in meetings}
    fp_events: list[FiveParrehProgramEvent] = []

    if isinstance(raw.get("five_parreh_events"), list):
        for item in raw["five_parreh_events"]:
            if isinstance(item, dict):
                fp_events.append(parse_five_parreh_event(item, meetings_by_id=by_id))

    if isinstance(legacy_events, list):
        for item in legacy_events:
            if not isinstance(item, dict):
                continue
            # Skip if already declared under five_parreh_events with same id.
            eid = str(item.get("event_id") or "").strip()
            if eid and any(e.event_id == eid for e in fp_events):
                continue
            fp_events.append(parse_five_parreh_event(item, meetings_by_id=by_id))

    return meetings, fp_events


def load_program_file(path: Path) -> tuple[list[Meeting], list[FiveParrehProgramEvent]]:
    path = Path(path)
    if not path.exists():
        return [], []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return parse_program_document(raw)
