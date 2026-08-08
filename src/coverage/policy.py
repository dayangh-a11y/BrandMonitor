"""Source priority and enrichment gate for coverage-first phase."""

from __future__ import annotations

# Lower rank = higher trust when two sources conflict.
# Never auto-overwrite warehouse without recording CovSourceConflict.
DEFAULT_SOURCE_PRIORITIES: list[tuple[str, int, str]] = [
    ("asbdavani", 10, "Primary racecards HTML — official heat/result cards"),
    ("mosharekat", 20, "Race-day discovery via external_id; results may be thinner"),
    ("asbdavani_horse_history", 30, "History rows — good for discovering missing weeks"),
    ("federation_calendar", 40, "Provincial/federation calendars (manual/PDF ingest)"),
    ("manual", 90, "Human adjudicated"),
]

# Phase-1 entities only — enrichment blocked until coverage gate opens.
PHASE1_CORE_FIELDS = (
    "race_day",
    "heat",
    "result",
    "horse",
    "trainer",
    "owner",
    "breed",
    "race_date_gregorian",
    "race_date_jalali",
    "track",
)

BLOCKED_ENRICHMENT = (
    "pedigree",
    "birthdate",
    "age",
    "weather",
    "features",
    "video_analytics",
)

# Proxy threshold for allowing enrichment (real-world completeness estimate).
DEFAULT_COVERAGE_GATE_PCT = 70.0


def preferred_source(source_a: str, source_b: str, priorities: dict[str, int] | None = None) -> str | None:
    """Return higher-priority source name, or None if tied/unknown."""
    pri = priorities or {s: r for s, r, _ in DEFAULT_SOURCE_PRIORITIES}
    ra = pri.get(source_a)
    rb = pri.get(source_b)
    if ra is None and rb is None:
        return None
    if ra is None:
        return source_b
    if rb is None:
        return source_a
    if ra == rb:
        return None
    return source_a if ra < rb else source_b
