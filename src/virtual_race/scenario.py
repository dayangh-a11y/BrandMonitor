"""Virtual race scenario — hypothetical card, no database race_id required."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass
class VirtualHorseEntry:
    """One runner on a hypothetical card."""

    # Identity — prefer IDs; name+signals used via Identity Engine when needed
    horse_id: int | None = None  # warehouse wh_horses.id
    permanent_horse_id: int | None = None  # id_horses.horse_id
    name: str | None = None
    sire: str | None = None
    dam: str | None = None
    age: int | None = None
    sex: str | None = None
    owner: str | None = None
    source_horse_id: str | None = None

    # Card overlays
    cloth: int | None = None  # draw / number
    weight: float | None = None
    draw: int | None = None  # barrier; cloth used if draw unset
    jockey: str | None = None
    trainer: str | None = None
    rating: float | None = None
    odds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class VirtualRaceScenario:
    """Temporary virtual race — never requires wh_races row."""

    horses: list[VirtualHorseEntry]
    distance: int | None = None
    race_class: str | None = None
    track: str | None = None  # surface / going label
    track_condition: str | None = None
    weather: dict[str, Any] | None = None
    racecourse: str | None = None  # code or Persian name
    racecourse_code: str | None = None
    date: str | date | None = None
    race_name: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def as_of_date(self) -> date | None:
        if self.date is None:
            return None
        if isinstance(self.date, date):
            return self.date
        text = str(self.date).strip()[:10]
        try:
            y, m, d = text.split("-")
            return date(int(y), int(m), int(d))
        except (TypeError, ValueError):
            return None

    def weather_dict(self) -> dict[str, Any] | None:
        wx = dict(self.weather or {})
        if self.track_condition and "track_condition" not in wx:
            wx["track_condition"] = self.track_condition
        if self.track and "track" not in wx:
            wx["track"] = self.track
        return wx or None

    def to_dict(self) -> dict[str, Any]:
        return {
            "horses": [h.to_dict() for h in self.horses],
            "distance": self.distance,
            "race_class": self.race_class,
            "track": self.track,
            "track_condition": self.track_condition,
            "weather": self.weather,
            "racecourse": self.racecourse,
            "racecourse_code": self.racecourse_code,
            "date": str(self.date) if self.date else None,
            "race_name": self.race_name,
            "meta": self.meta,
        }


def scenario_from_dict(data: dict[str, Any]) -> VirtualRaceScenario:
    """Parse JSON/dict input into a VirtualRaceScenario."""
    raw_horses = data.get("horses") or data.get("runners") or []
    horses: list[VirtualHorseEntry] = []
    for i, row in enumerate(raw_horses):
        if isinstance(row, str):
            horses.append(VirtualHorseEntry(name=row, cloth=i + 1))
            continue
        if not isinstance(row, dict):
            continue
        horses.append(
            VirtualHorseEntry(
                horse_id=row.get("horse_id") or row.get("warehouse_horse_id"),
                permanent_horse_id=row.get("permanent_horse_id") or row.get("id_horse_id"),
                name=row.get("name") or row.get("horse") or row.get("horse_name"),
                sire=row.get("sire"),
                dam=row.get("dam"),
                age=row.get("age"),
                sex=row.get("sex"),
                owner=row.get("owner"),
                source_horse_id=row.get("source_horse_id") or row.get("source_id"),
                cloth=row.get("cloth") or row.get("number") or row.get("draw"),
                weight=row.get("weight"),
                draw=row.get("draw") or row.get("barrier"),
                jockey=row.get("jockey"),
                trainer=row.get("trainer"),
                rating=row.get("rating") or row.get("source_rating") or row.get("ior"),
                odds=row.get("odds"),
            )
        )
    wx = data.get("weather")
    if isinstance(wx, str):
        wx = {"weather_condition": wx}
    return VirtualRaceScenario(
        horses=horses,
        distance=data.get("distance"),
        race_class=data.get("race_class") or data.get("class") or data.get("class_code"),
        track=data.get("track"),
        track_condition=data.get("track_condition") or data.get("going"),
        weather=wx if isinstance(wx, dict) else None,
        racecourse=data.get("racecourse") or data.get("track_name"),
        racecourse_code=data.get("racecourse_code") or data.get("course"),
        date=data.get("date") or data.get("race_date"),
        race_name=data.get("race_name") or data.get("name"),
        meta=dict(data.get("meta") or {}),
    )
