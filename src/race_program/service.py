"""Race-program service: upcoming meetings and Five-Parreh events."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from src.race_program.eligibility import (
    DEFAULT_UPCOMING_DAYS,
    ensure_utc,
    is_eligible_for_prediction,
    is_within_upcoming_window,
    utc_now,
)
from src.race_program.loader import load_program_file, parse_program_document
from src.race_program.models import (
    STATUS_COMPLETED,
    STATUS_STARTED,
    STATUS_UNKNOWN_TIME,
    FiveParrehProgramEvent,
    Meeting,
    ProgramRace,
)


def load_race_program(path: Path | None) -> RaceProgramService:
    if path is None:
        return RaceProgramService(meetings=[], events=[])
    meetings, events = load_program_file(path)
    return RaceProgramService(meetings=meetings, events=events)


class RaceProgramService:
    """In-memory race program. Telegram must access this via HTTP API only."""

    def __init__(
        self,
        *,
        meetings: list[Meeting] | None = None,
        events: list[FiveParrehProgramEvent] | None = None,
    ) -> None:
        self.meetings = list(meetings or [])
        self.events = list(events or [])
        self._by_meeting = {m.meeting_id: m for m in self.meetings}
        self._by_race: dict[str, tuple[Meeting, ProgramRace]] = {}
        for meeting in self.meetings:
            for race in meeting.races:
                self._by_race[race.race_id] = (meeting, race)

    @classmethod
    def from_document(cls, raw: Any) -> RaceProgramService:
        meetings, events = parse_program_document(raw)
        return cls(meetings=meetings, events=events)

    def get_meeting(self, meeting_id: str) -> Meeting | None:
        return self._by_meeting.get(str(meeting_id).strip())

    def get_race(self, race_id: str) -> tuple[Meeting, ProgramRace] | None:
        return self._by_race.get(str(race_id).strip())

    def annotate_race(self, race: ProgramRace, *, now: datetime) -> dict[str, Any]:
        payload = race.to_public_dict()
        eligible = is_eligible_for_prediction(race.scheduled_start, now=now)
        status = race.status
        if race.scheduled_start is None:
            status = STATUS_UNKNOWN_TIME
        elif not eligible:
            # Started or completed — both are ineligible for prediction.
            status = STATUS_STARTED if status not in {STATUS_COMPLETED, STATUS_STARTED} else status
        payload["status"] = status
        payload["eligible_for_prediction"] = eligible
        return payload

    def list_upcoming_meetings(
        self,
        *,
        now: datetime | None = None,
        days: int = DEFAULT_UPCOMING_DAYS,
    ) -> list[dict[str, Any]]:
        """Meetings that still have ≥1 eligible race within the upcoming window.

        Historical freeze races are never included — only declared program races
        with ``scheduled_start > now``.
        """
        now_utc = ensure_utc(now or utc_now())
        days = max(0, int(days))
        out: list[dict[str, Any]] = []
        for meeting in self.meetings:
            eligible_races: list[dict[str, Any]] = []
            earliest: datetime | None = None
            for race in meeting.races:
                if race.scheduled_start is None:
                    continue
                if not is_eligible_for_prediction(race.scheduled_start, now=now_utc):
                    continue
                if not is_within_upcoming_window(race.scheduled_start, now=now_utc, days=days):
                    continue
                eligible_races.append(self.annotate_race(race, now=now_utc))
                if earliest is None or race.scheduled_start < earliest:
                    earliest = race.scheduled_start
            if not eligible_races:
                continue
            # Stable order by race_number for UX.
            eligible_races.sort(key=lambda r: (int(r.get("race_number") or 0), str(r.get("race_id"))))
            payload = meeting.to_public_dict(include_races=False)
            payload["races"] = eligible_races
            payload["race_count"] = len(eligible_races)
            payload["_sort_start"] = earliest.isoformat() if earliest else ""
            out.append(payload)
        out.sort(key=lambda m: (m.get("_sort_start") or "", m.get("meeting_id") or ""))
        for item in out:
            item.pop("_sort_start", None)
        return out

    def meeting_detail(
        self,
        meeting_id: str,
        *,
        now: datetime | None = None,
        prediction_only: bool = True,
    ) -> dict[str, Any] | None:
        meeting = self.get_meeting(meeting_id)
        if meeting is None:
            return None
        now_utc = ensure_utc(now or utc_now())
        races = []
        for race in meeting.races:
            annotated = self.annotate_race(race, now=now_utc)
            if prediction_only and not annotated["eligible_for_prediction"]:
                continue
            races.append(annotated)
        races.sort(key=lambda r: (int(r.get("race_number") or 0), str(r.get("race_id"))))
        payload = meeting.to_public_dict(include_races=False)
        payload["races"] = races
        payload["race_count"] = len(races)
        return payload

    def list_future_five_parreh_events(
        self,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now_utc = ensure_utc(now or utc_now())
        out: list[FiveParrehProgramEvent] = []
        for event in self.events:
            if len(event.races) != 5:
                continue
            if not event.is_future(now=now_utc):
                continue
            out.append(event)

        def sort_key(e: FiveParrehProgramEvent) -> tuple[str, str]:
            start = e.races[0].scheduled_start
            return (start.isoformat() if start else "9999", e.event_id)

        out.sort(key=sort_key)
        return [e.to_public_dict() for e in out]

    def get_future_five_parreh_event(
        self,
        event_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        event_id = str(event_id).strip()
        for item in self.list_future_five_parreh_events(now=now):
            if item.get("event_id") == event_id:
                return item
        return None

    def upcoming_payload(
        self,
        *,
        now: datetime | None = None,
        days: int = DEFAULT_UPCOMING_DAYS,
    ) -> dict[str, Any]:
        meetings = self.list_upcoming_meetings(now=now, days=days)
        return {
            "days": days,
            "count": len(meetings),
            "meetings": meetings,
            "message": (
                None
                if meetings
                else "در ۷ روز آینده مسابقه‌ای برای پیش‌بینی ثبت نشده است."
                if days == 7
                else f"در {days} روز آینده مسابقه‌ای برای پیش‌بینی ثبت نشده است."
            ),
        }
