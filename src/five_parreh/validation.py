"""Validation for Five-Parreh selections (Phase 1)."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from src.five_parreh.errors import FiveParrehValidationError
from src.five_parreh.models import HorsePick, RaceSelection

REQUIRED_RACE_COUNT = 5


def _normalize_horse_id(raw: Any) -> str:
    if raw is None:
        raise FiveParrehValidationError("Invalid horse identifier: horse_id is required")
    if isinstance(raw, bool):
        raise FiveParrehValidationError(f"Invalid horse identifier: {raw!r}")
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and not raw.is_integer():
            raise FiveParrehValidationError(f"Invalid horse identifier: {raw!r}")
        text = str(int(raw))
    else:
        text = str(raw).strip()
    if not text:
        raise FiveParrehValidationError("Invalid horse identifier: empty horse_id")
    return text


def _as_horse_pick(item: Any) -> HorsePick:
    if isinstance(item, HorsePick):
        return HorsePick(horse_id=_normalize_horse_id(item.horse_id), horse_name=item.horse_name)
    if isinstance(item, Mapping):
        if "horse_id" not in item:
            raise FiveParrehValidationError("Invalid horse identifier: missing horse_id")
        name = item.get("horse_name")
        return HorsePick(
            horse_id=_normalize_horse_id(item["horse_id"]),
            horse_name=None if name is None else str(name),
        )
    # Bare id string / int
    return HorsePick(horse_id=_normalize_horse_id(item))


def _as_race_selection(item: Any, *, index: int) -> RaceSelection:
    if isinstance(item, RaceSelection):
        race_id = str(item.race_id).strip()
        horses_raw: Sequence[Any] = item.horses
    elif isinstance(item, Mapping):
        if "race_id" not in item:
            raise FiveParrehValidationError(f"Race at index {index} is missing race_id")
        race_id = str(item["race_id"]).strip()
        if "horses" not in item:
            raise FiveParrehValidationError(f"Race {race_id!r} is missing horses")
        horses_raw = item["horses"]
    else:
        raise FiveParrehValidationError(
            f"Race at index {index} must be a mapping or RaceSelection, got {type(item).__name__}"
        )

    if not race_id:
        raise FiveParrehValidationError(f"Race at index {index} has empty race_id")

    if not isinstance(horses_raw, Sequence) or isinstance(horses_raw, (str, bytes)):
        raise FiveParrehValidationError(f"Race {race_id!r} horses must be a list")

    if len(horses_raw) == 0:
        raise FiveParrehValidationError(f"Race {race_id!r} has no selected horses (empty race)")

    picks: list[HorsePick] = []
    seen: set[str] = set()
    for h in horses_raw:
        pick = _as_horse_pick(h)
        if pick.horse_id in seen:
            raise FiveParrehValidationError(
                f"Race {race_id!r} has duplicate horse_id {pick.horse_id!r}"
            )
        seen.add(pick.horse_id)
        picks.append(pick)

    return RaceSelection(race_id=race_id, horses=tuple(picks))


def normalize_selections(selections: Iterable[Any] | Mapping[str, Any]) -> tuple[RaceSelection, ...]:
    """Normalize and validate input into exactly five race selections."""
    if isinstance(selections, Mapping):
        if "races" in selections:
            raw_races = selections["races"]
        else:
            raise FiveParrehValidationError("Selections mapping must include 'races'")
    else:
        raw_races = selections

    if not isinstance(raw_races, Sequence) or isinstance(raw_races, (str, bytes)):
        raise FiveParrehValidationError("Selections must be a sequence of exactly 5 races")

    races = list(raw_races)
    if len(races) != REQUIRED_RACE_COUNT:
        raise FiveParrehValidationError(
            f"Exactly {REQUIRED_RACE_COUNT} races required, got {len(races)}"
        )

    normalized = tuple(_as_race_selection(r, index=i) for i, r in enumerate(races))
    return normalized
