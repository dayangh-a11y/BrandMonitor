"""Track Configuration — finishing straight length (not race distance / total circuit).

``straight_length_m`` is the length of the home straight from the final turn
to the finish line. It must never be confused with ``race_distance`` or a
full-circuit length.

Rules (product):
- Apply only when the race track confidently resolves to a known ``track_id``.
- Ambiguous city/venue names → do not apply (no guessing).
- Reference values are append-stable; conflicting new sources are reported,
  never silently overwrite prior values.
- Historical race/result rows are never overwritten.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from src.racecourses.registry import get_racecourse, resolve_racecourse

StraightCategory = Literal["Short", "Medium", "Long"]

SOURCE_LABEL = "visual_track_diagram"
SOURCE_NOTE = (
    "Extracted from a user-provided visual track diagram showing home-straight "
    "lengths (final turn → finish). Not race distance and not total track length."
)
DEFAULT_SOURCE_URL: str | None = None
DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True, slots=True)
class TrackConfiguration:
    """Immutable reference row for one racecourse."""

    track_id: str
    track_name: str
    city: str
    straight_length_m: int
    source: str = SOURCE_LABEL
    source_url: str | None = DEFAULT_SOURCE_URL
    source_confidence: float = DEFAULT_CONFIDENCE
    source_note: str = SOURCE_NOTE

    @property
    def straight_length_category(self) -> StraightCategory:
        return categorize_straight_length(self.straight_length_m)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["straight_length_category"] = self.straight_length_category
        return d


def categorize_straight_length(meters: int | float | None) -> StraightCategory | None:
    """Short <200, Medium 200–275, Long ≥276."""
    if meters is None:
        return None
    m = float(meters)
    if m < 200:
        return "Short"
    if m <= 275:
        return "Medium"
    return "Long"


# Canonical seed — keyed by registry racecourse_code (track_id).
# Venue marketing names are stored as track_name; city is the WH/city label.
TRACK_CONFIGURATIONS: tuple[TrackConfiguration, ...] = (
    TrackConfiguration(
        track_id="mashhad",
        track_name="ثامن مشهد",
        city="مشهد",
        straight_length_m=388,
    ),
    TrackConfiguration(
        track_id="aq-qala",
        track_name="آق‌قلا",
        city="آق قلا",
        straight_length_m=321,
    ),
    TrackConfiguration(
        track_id="tehran",
        track_name="نوروزآباد تهران",
        city="تهران",
        straight_length_m=278,
    ),
    TrackConfiguration(
        track_id="kish",
        track_name="کیش",
        city="کیش",
        straight_length_m=276,
    ),
    TrackConfiguration(
        track_id="gonbad-kavous",
        track_name="گنبدکاووس",
        city="گنبدکاووس",
        straight_length_m=263,
    ),
    TrackConfiguration(
        track_id="bandar-torkaman",
        track_name="شهدای بندرترکمن",
        city="بندرترکمن",
        straight_length_m=244,
    ),
    TrackConfiguration(
        track_id="ahvaz",
        track_name="نیرو اهواز",
        city="اهواز",
        straight_length_m=221,
    ),
    TrackConfiguration(
        track_id="yazd",
        track_name="صفائیه یزد",
        city="یزد",
        straight_length_m=138,
    ),
)

_BY_ID: dict[str, TrackConfiguration] = {c.track_id: c for c in TRACK_CONFIGURATIONS}

# Venue aliases that confidently map to a track_id (no ambiguous bare tokens).
VENUE_ALIASES: dict[str, str] = {
    "ثامن مشهد": "mashhad",
    "ثامن": "mashhad",
    "نوروزآباد تهران": "tehran",
    "نوروز آباد تهران": "tehran",
    "نوروزآباد": "tehran",
    "نوروز آباد": "tehran",
    "شهدای بندرترکمن": "bandar-torkaman",
    "شهدای بندر ترکمن": "bandar-torkaman",
    "نیرو اهواز": "ahvaz",
    "صفائیه یزد": "yazd",
    "صفائیه": "yazd",
}


@dataclass(frozen=True, slots=True)
class TrackContext:
    """Minimum Track Context for Performance Score / Finish Performance.

    ``straight_length_m`` is included only when the race confidently matches
    a configured track_id; otherwise it is None and must not be imputed.
    """

    race_distance: int | None
    straight_length_m: int | None
    straight_length_category: StraightCategory | None
    track_id: str | None
    track_name: str | None
    city: str | None
    breed: str | None
    horse_age: int | float | None
    weight: float | None
    starting_gate: int | None
    finish_position: int | None
    finish_time: str | float | None
    number_of_runners: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def has_track_configuration(self) -> bool:
        return self.straight_length_m is not None and self.track_id is not None


def get_track_configuration(track_id: str | None) -> TrackConfiguration | None:
    if not track_id:
        return None
    return _BY_ID.get(track_id)


def resolve_track_configuration(
    *,
    racecourse_code: str | None = None,
    track_name: str | None = None,
    city: str | None = None,
) -> TrackConfiguration | None:
    """Return config only on confident match; never guess.

    Match order:
    1. Exact ``racecourse_code`` / ``track_id``
    2. Venue alias (ثامن مشهد, نوروزآباد, …)
    3. Registry resolve of track_name or city → known code with config
    """
    if racecourse_code:
        cfg = _BY_ID.get(racecourse_code.strip())
        if cfg is not None:
            return cfg
        # Reject synthetic ir-* codes without config
        course = get_racecourse(racecourse_code.strip())
        if course is not None:
            cfg = _BY_ID.get(course.code)
            if cfg is not None:
                return cfg

    for label in (track_name, city):
        if not label or not str(label).strip():
            continue
        raw = str(label).strip()
        # Venue alias first (more specific than bare city)
        from src.racecourses.registry import normalize_track_key

        nk = normalize_track_key(raw)
        for alias, tid in VENUE_ALIASES.items():
            if normalize_track_key(alias) == nk:
                return _BY_ID.get(tid)
        course = resolve_racecourse(raw)
        if course is not None and course.code in _BY_ID:
            return _BY_ID[course.code]
    return None


def straight_length_features(
    *,
    racecourse_code: str | None = None,
    track_name: str | None = None,
    city: str | None = None,
) -> dict[str, Any]:
    """Feature dict for Feature Set. Empty when match is not confident."""
    cfg = resolve_track_configuration(
        racecourse_code=racecourse_code,
        track_name=track_name,
        city=city,
    )
    if cfg is None:
        return {
            "straight_length_m": None,
            "straight_length_category": None,
            "track_config_applied": False,
            "track_id": None,
        }
    return {
        "straight_length_m": cfg.straight_length_m,
        "straight_length_category": cfg.straight_length_category,
        "track_config_applied": True,
        "track_id": cfg.track_id,
        "track_config_source": cfg.source,
        "track_config_confidence": cfg.source_confidence,
    }


def build_track_context(
    *,
    racecourse_code: str | None = None,
    track_name: str | None = None,
    city: str | None = None,
    race_distance: int | None = None,
    breed: str | None = None,
    horse_age: int | float | None = None,
    weight: float | None = None,
    starting_gate: int | None = None,
    finish_position: int | None = None,
    finish_time: str | float | None = None,
    number_of_runners: int | None = None,
) -> TrackContext:
    cfg = resolve_track_configuration(
        racecourse_code=racecourse_code,
        track_name=track_name,
        city=city,
    )
    return TrackContext(
        race_distance=race_distance,
        straight_length_m=cfg.straight_length_m if cfg else None,
        straight_length_category=cfg.straight_length_category if cfg else None,
        track_id=cfg.track_id if cfg else None,
        track_name=cfg.track_name if cfg else track_name,
        city=cfg.city if cfg else city,
        breed=breed,
        horse_age=horse_age,
        weight=weight,
        starting_gate=starting_gate,
        finish_position=finish_position,
        finish_time=finish_time,
        number_of_runners=number_of_runners,
    )


def comparable_on_straight(
    a: TrackConfiguration | TrackContext | None,
    b: TrackConfiguration | TrackContext | None,
) -> bool:
    """True when both sides have config and same category (or identical meters).

    Cross-category comparisons require an explicit Track Configuration adjustment
    in the model; this helper flags when a raw comparison is unsafe.
    """
    def meters(x: Any) -> int | None:
        if x is None:
            return None
        if isinstance(x, TrackConfiguration):
            return x.straight_length_m
        return getattr(x, "straight_length_m", None)

    ma, mb = meters(a), meters(b)
    if ma is None or mb is None:
        return False
    return categorize_straight_length(ma) == categorize_straight_length(mb)


def propose_straight_length_update(
    track_id: str,
    new_straight_length_m: int,
    *,
    source: str,
    source_url: str | None = None,
    source_confidence: float | None = None,
) -> dict[str, Any]:
    """Report conflict without changing the stored reference value."""
    current = _BY_ID.get(track_id)
    if current is None:
        return {
            "status": "unknown_track",
            "track_id": track_id,
            "proposed_straight_length_m": new_straight_length_m,
            "applied": False,
        }
    if current.straight_length_m == new_straight_length_m:
        return {
            "status": "unchanged",
            "track_id": track_id,
            "straight_length_m": current.straight_length_m,
            "applied": False,
        }
    return {
        "status": "conflict_reported",
        "track_id": track_id,
        "current_straight_length_m": current.straight_length_m,
        "proposed_straight_length_m": new_straight_length_m,
        "current_source": current.source,
        "proposed_source": source,
        "proposed_source_url": source_url,
        "proposed_source_confidence": source_confidence,
        "applied": False,
        "message": (
            "Track Configuration is fixed until human confirmation; "
            "prior value retained."
        ),
    }


def configuration_table_rows() -> list[dict[str, Any]]:
    """Display rows: میدان | شهر | Straight Length | دسته | Source | Confidence."""
    rows = []
    for cfg in TRACK_CONFIGURATIONS:
        rows.append(
            {
                "میدان": cfg.track_name,
                "شهر": cfg.city,
                "Straight Length": cfg.straight_length_m,
                "دسته": cfg.straight_length_category,
                "Source": cfg.source,
                "Confidence": cfg.source_confidence,
                "track_id": cfg.track_id,
            }
        )
    return rows
