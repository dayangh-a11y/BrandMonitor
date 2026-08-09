"""Data models for Five-Parreh combinations (Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class HorsePick:
    """One selected horse in a race."""

    horse_id: str
    horse_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"horse_id": self.horse_id}
        if self.horse_name is not None:
            out["horse_name"] = self.horse_name
        return out


@dataclass(frozen=True, slots=True)
class RaceSelection:
    """Selected horses for one of the five consecutive races."""

    race_id: str
    horses: tuple[HorsePick, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "race_id": self.race_id,
            "horses": [h.to_dict() for h in self.horses],
        }


@dataclass(frozen=True, slots=True)
class Combination:
    """One Five-Parreh ticket: exactly one horse from each of five races."""

    race_1: HorsePick
    race_2: HorsePick
    race_3: HorsePick
    race_4: HorsePick
    race_5: HorsePick
    index: int = 0

    def horses(self) -> tuple[HorsePick, HorsePick, HorsePick, HorsePick, HorsePick]:
        return (self.race_1, self.race_2, self.race_3, self.race_4, self.race_5)

    def horse_ids(self) -> tuple[str, str, str, str, str]:
        return tuple(h.horse_id for h in self.horses())  # type: ignore[return-value]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "race_1": self.race_1.to_dict(),
            "race_2": self.race_2.to_dict(),
            "race_3": self.race_3.to_dict(),
            "race_4": self.race_4.to_dict(),
            "race_5": self.race_5.to_dict(),
            "horse_ids": list(self.horse_ids()),
        }


@dataclass(frozen=True, slots=True)
class CombinationSummary:
    """Counts and cost only — no ranking or probability."""

    race_count: int
    selections_per_race: tuple[int, ...]
    total_combinations: int
    price_per_combination: int | float | None
    total_cost: int | float | None
    race_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "race_count": self.race_count,
            "selections_per_race": list(self.selections_per_race),
            "total_combinations": self.total_combinations,
            "price_per_combination": self.price_per_combination,
            "total_cost": self.total_cost,
            "race_ids": list(self.race_ids),
        }


@dataclass(frozen=True, slots=True)
class FiveParrehResult:
    """Full Phase-1 result: summary plus optional combination list."""

    summary: CombinationSummary
    combinations: tuple[Combination, ...]
    selections: tuple[RaceSelection, ...]

    def to_dict(self, *, include_combinations: bool = True) -> dict[str, Any]:
        out = self.summary.to_dict()
        out["selections"] = [s.to_dict() for s in self.selections]
        if include_combinations:
            out["combinations"] = [c.to_dict() for c in self.combinations]
        else:
            out["combinations"] = None
            out["combinations_omitted"] = True
        return out
