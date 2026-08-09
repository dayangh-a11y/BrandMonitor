"""In-memory Five-Parreh conversation state (no secrets / minimal PII)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class FiveParrehSession:
    """Per-user temporary selection state for exactly five races."""

    race_ids: list[str] = field(default_factory=list)
    # race_id -> ordered unique horse ids
    horses_by_race: dict[str, list[str]] = field(default_factory=dict)
    # pick_start → confirm_block → pick_horses → confirm
    step: str = "pick_start"
    race_index: int = 0  # 0..4 within locked race_ids
    candidates: list[dict] = field(default_factory=list)
    catalog: list[dict] = field(default_factory=list)  # races fetched for meeting resolution
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()

    def current_race_id(self) -> str | None:
        if 0 <= self.race_index < len(self.race_ids):
            return self.race_ids[self.race_index]
        return None

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
