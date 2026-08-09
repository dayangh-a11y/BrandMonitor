"""Race-program helpers for Telegram Five-Parreh UX.

Consecutive races = next races in the same meeting (same date + track),
ordered by program order (race_id ascending within the meeting).

Does NOT use race_id+1 arithmetic. Does NOT generate combinations.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def meeting_key(race: dict[str, Any]) -> tuple[str, str]:
    return (str(race.get("race_date") or "").strip(), str(race.get("track") or "").strip())


def _race_sort_key(race: dict[str, Any]) -> tuple:
    rid = race.get("race_id")
    try:
        rid_n = int(rid)
    except (TypeError, ValueError):
        rid_n = 0
    return (rid_n, str(rid))


def group_meetings(races: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group races by meeting and sort each meeting in program order."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for race in races:
        if race.get("race_id") is None:
            continue
        grouped[meeting_key(race)].append(race)
    for key in grouped:
        grouped[key] = sorted(grouped[key], key=_race_sort_key)
    return dict(grouped)


def consecutive_from_start(
    races: list[dict[str, Any]],
    start_race_id: int | str,
    *,
    count: int = 5,
) -> list[dict[str, Any]] | None:
    """Return exactly ``count`` consecutive races in the same meeting, or None."""
    if count < 1:
        return None
    start_id = str(start_race_id)
    meetings = group_meetings(races)
    for meeting_races in meetings.values():
        ids = [str(r.get("race_id")) for r in meeting_races]
        if start_id not in ids:
            continue
        idx = ids.index(start_id)
        window = meeting_races[idx : idx + count]
        if len(window) != count:
            return None
        # Guard: entire window must stay in this meeting (slice already ensures).
        return window
    return None


def valid_starting_races(
    races: list[dict[str, Any]],
    *,
    count: int = 5,
) -> list[dict[str, Any]]:
    """Starting races that have ``count`` consecutive races remaining in-meeting."""
    starts: list[dict[str, Any]] = []
    meetings = group_meetings(races)
    for meeting_races in meetings.values():
        if len(meeting_races) < count:
            continue
        # Only indices where a full window fits.
        for i in range(0, len(meeting_races) - count + 1):
            starts.append(meeting_races[i])
    # Stable order: by meeting date/track then race_id (already per-meeting sorted).
    return sorted(starts, key=lambda r: (meeting_key(r), _race_sort_key(r)))


def race_ids(window: list[dict[str, Any]]) -> list[str]:
    return [str(r.get("race_id")) for r in window]
