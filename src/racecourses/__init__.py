"""Racecourse registry and crawl-scope filtering (expandable allowlist)."""

from src.racecourses.registry import (
    DEFAULT_ALLOWED_CODES,
    RACECOURSES,
    Racecourse,
    get_racecourse,
    is_code_allowed,
    is_racecourse_allowed,
    normalize_track_key,
    parse_allowed_codes,
    resolve_racecourse,
)
from src.racecourses.scope import (
    OutOfScopeRacecourseError,
    allowed_codes_from_settings,
    ensure_track_in_scope,
)

__all__ = [
    "DEFAULT_ALLOWED_CODES",
    "OutOfScopeRacecourseError",
    "RACECOURSES",
    "Racecourse",
    "allowed_codes_from_settings",
    "ensure_track_in_scope",
    "get_racecourse",
    "is_code_allowed",
    "is_racecourse_allowed",
    "normalize_track_key",
    "parse_allowed_codes",
    "resolve_racecourse",
]
