"""Horse identity profile — attributes used for multi-signal matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.identity.normalize import normalize_name, normalize_sex


@dataclass
class HorseQuery:
    """Lookup request from a race card or user query — never name alone."""

    name: str | None = None
    sire: str | None = None
    dam: str | None = None
    age: int | None = None
    sex: str | None = None
    owner: str | None = None
    trainer: str | None = None
    source_horse_id: str | None = None
    as_of_date: date | None = None

    def normalized_name(self) -> str:
        return normalize_name(self.name)

    def normalized_sex(self) -> str | None:
        return normalize_sex(self.sex)


@dataclass
class HorseProfile:
    """Identity attributes for one warehouse horse row (pre-merge)."""

    warehouse_horse_id: int
    name: str
    source: str | None = None
    source_horse_id: str | None = None
    sex: str | None = None
    birthdate: date | None = None
    birth_year: int | None = None
    age_years: int | None = None  # observed/derived age
    sire: str | None = None
    dam: str | None = None
    owners: list[str] = field(default_factory=list)
    trainers: list[str] = field(default_factory=list)
    starts: int = 0
    # Historical race continuity (warehouse race dates + course codes)
    race_dates: list[date] = field(default_factory=list)
    racecourse_codes: list[str] = field(default_factory=list)

    def normalized_name(self) -> str:
        return normalize_name(self.name)

    def normalized_sex(self) -> str | None:
        return normalize_sex(self.sex)

    def primary_owner(self) -> str | None:
        return self.owners[0] if self.owners else None

    def primary_trainer(self) -> str | None:
        return self.trainers[0] if self.trainers else None

    def effective_birth_year(self) -> int | None:
        if self.birth_year is not None:
            return int(self.birth_year)
        if self.birthdate is not None:
            return int(self.birthdate.year)
        return None

    def to_meta(self) -> dict[str, Any]:
        return {
            "warehouse_horse_id": self.warehouse_horse_id,
            "name": self.name,
            "source": self.source,
            "source_horse_id": self.source_horse_id,
            "sex": self.normalized_sex(),
            "birthdate": self.birthdate.isoformat() if self.birthdate else None,
            "birth_year": self.effective_birth_year(),
            "age_years": self.age_years,
            "sire": self.sire,
            "dam": self.dam,
            "owners": self.owners[:5],
            "trainers": self.trainers[:5],
            "starts": self.starts,
            "race_dates": [d.isoformat() for d in self.race_dates[:20]],
            "racecourse_codes": sorted(set(self.racecourse_codes))[:12],
        }
