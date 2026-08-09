"""In-memory Five-Parreh conversation state (no secrets / minimal PII)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class FiveParrehSession:
    """Per-user temporary selection state for one future Five-Parreh event."""

    event_id: str | None = None
    event_title: str | None = None
    event_track: str | None = None
    event_display_date: str | None = None
    race_ids: list[str] = field(default_factory=list)
    race_labels: dict[str, str] = field(default_factory=dict)
    # race_id -> ordered unique horse ids
    horses_by_race: dict[str, list[str]] = field(default_factory=dict)
    # pick_event → confirm_event → pick_horses → confirm
    step: str = "pick_event"
    race_index: int = 0  # 0..4 within locked race_ids
    candidates: list[dict] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()

    def current_race_id(self) -> str | None:
        if 0 <= self.race_index < len(self.race_ids):
            return self.race_ids[self.race_index]
        return None

    def current_race_label(self) -> str:
        rid = self.current_race_id()
        if not rid:
            return "—"
        return self.race_labels.get(rid) or f"مسابقه {rid}"

    def selected_for_current(self) -> list[str]:
        rid = self.current_race_id()
        if not rid:
            return []
        return list(self.horses_by_race.get(rid, []))

    def toggle_horse(self, horse_id: str) -> None:
        rid = self.current_race_id()
        if not rid:
            return
        horse_id = str(horse_id).strip()
        if not horse_id:
            return
        current = list(self.horses_by_race.get(rid, []))
        if horse_id in current:
            current = [h for h in current if h != horse_id]
        else:
            current.append(horse_id)
        self.horses_by_race[rid] = current
        self.touch()

    def selections_per_race(self) -> list[int]:
        return [len(self.horses_by_race.get(rid, [])) for rid in self.race_ids]

    def total_combinations_estimate(self) -> int | None:
        counts = self.selections_per_race()
        if len(counts) != 5 or any(c < 1 for c in counts):
            return None
        total = 1
        for c in counts:
            total *= c
        return total

    def to_api_payload(self) -> list[dict]:
        races = []
        for rid in self.race_ids:
            horses = self.horses_by_race.get(rid) or []
            races.append({"race_id": str(rid), "horses": list(horses)})
        return races


class HorseLookupStore:
    """Tracks users who were asked to type a horse name (no IDs)."""

    def __init__(self, *, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = ttl_seconds
        self._waiting: dict[int, float] = {}

    def ask(self, user_id: int) -> None:
        self._waiting[user_id] = time.time()

    def clear(self, user_id: int) -> None:
        self._waiting.pop(user_id, None)

    def is_waiting(self, user_id: int) -> bool:
        started = self._waiting.get(user_id)
        if started is None:
            return False
        if time.time() - started > self.ttl_seconds:
            self._waiting.pop(user_id, None)
            return False
        return True


@dataclass
class HorseVsSession:
    """Per-user state for pairwise horse comparison in one future race."""

    step: str = "pick_meeting"  # pick_meeting → pick_race → pick_a → pick_b
    meeting_id: str | None = None
    race_id: str | None = None
    race_label: str | None = None
    race_number: int | None = None
    display_date: str | None = None
    track: str | None = None
    horse_a_id: str | None = None
    horse_a_name: str | None = None
    candidates: list[dict] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


class HorseVsStore:
    def __init__(self, *, ttl_seconds: int = 1800) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[int, HorseVsSession] = {}

    def get(self, user_id: int) -> HorseVsSession | None:
        session = self._sessions.get(user_id)
        if not session:
            return None
        if time.time() - session.updated_at > self.ttl_seconds:
            self._sessions.pop(user_id, None)
            return None
        return session

    def set(self, user_id: int, session: HorseVsSession) -> HorseVsSession:
        session.touch()
        self._sessions[user_id] = session
        return session

    def clear(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)


class SessionStore:
    def __init__(self, *, ttl_seconds: int = 1800) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[int, FiveParrehSession] = {}

    def get(self, user_id: int) -> FiveParrehSession | None:
        session = self._sessions.get(user_id)
        if not session:
            return None
        if time.time() - session.updated_at > self.ttl_seconds:
            self._sessions.pop(user_id, None)
            return None
        return session

    def set(self, user_id: int, session: FiveParrehSession) -> FiveParrehSession:
        session.touch()
        self._sessions[user_id] = session
        return session

    def clear(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)

    def get_or_create(self, user_id: int) -> FiveParrehSession:
        existing = self.get(user_id)
        if existing:
            return existing
        return self.set(user_id, FiveParrehSession())
