"""Domain models for race collection output (Pydantic)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class HorseEntry(BaseModel):
    """A horse as it appears in a race card / result."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    number: int | None = None
    age: int | None = None
    sex: str | None = None
    weight: float | None = None
    jockey: str | None = None
    trainer: str | None = None
    owner: str | None = None
    rating: float | None = None
    barrier: int | None = None
    finish_position: int | None = Field(default=None, alias="finishPosition")
    time: str | float | None = None
    margin: float | None = None
    odds: float | None = None
    horse_profile_url: str | None = Field(default=None, alias="horseProfileUrl")
    horse_id: str | None = Field(default=None, alias="horseId")


class Race(BaseModel):
    """Normalized race document written to Race.json."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    race: str | None = Field(default=None, description="Race name / class")
    date: date | datetime | str | None = None
    track: str = Field(..., description="Racecourse name (required)")
    racecourse_code: str = Field(
        ...,
        description="Stable racecourse code (e.g. gonbad-kavous); required",
    )
    province: str | None = None
    distance: int | None = None
    surface: str | None = None
    race_number: int | None = Field(default=None, alias="raceNumber")
    weather: str | None = None
    prize: Any | None = None
    # Source media items (Aparat/YouTube/photo-finish) from race payload
    media: list[dict[str, Any]] = Field(default_factory=list)
    source_url: str | None = Field(default=None, alias="sourceUrl")
    source_id: str | None = Field(default=None, alias="sourceId")
    horses: list[HorseEntry] = Field(default_factory=list)


class HorseHistoryEntry(BaseModel):
    """One historical race start for a horse."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    race_name: str | None = Field(default=None, alias="raceName")
    race_date: date | datetime | str | None = Field(default=None, alias="raceDate")
    track: str | None = None
    race_number: int | None = Field(default=None, alias="raceNumber")
    distance: int | None = None
    surface: str | None = None
    number: int | None = None
    weight: float | None = None
    jockey: str | None = None
    trainer: str | None = None
    owner: str | None = None
    rating: float | None = None
    barrier: int | None = None
    finish_position: int | None = Field(default=None, alias="finishPosition")
    time: str | float | None = None
    margin: float | None = None
    odds: float | None = None
    race_url: str | None = Field(default=None, alias="raceUrl")


class HorseProfile(BaseModel):
    """Horse profile metadata."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    horse_id: str | None = Field(default=None, alias="horseId")
    name: str
    sex: str | None = None
    birthdate: date | datetime | str | None = None
    profile_url: str | None = Field(default=None, alias="profileUrl")
    sire: str | None = None
    dam: str | None = None


class HorseHistory(BaseModel):
    """Normalized horse history document written to HorseHistory.json."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    horse: HorseProfile
    history: list[HorseHistoryEntry] = Field(default_factory=list)


class RaceListItem(BaseModel):
    """Summary row for a race listing page."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    title: str | None = None
    date: date | datetime | str | None = None
    track: str | None = None
    url: str
    source_id: str | None = Field(default=None, alias="sourceId")
