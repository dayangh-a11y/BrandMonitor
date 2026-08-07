"""Racecourse registry and crawl-scope filtering (expandable allowlist)."""

from src.racecourses.registry import (
    DEFAULT_ALLOWED_CODES,
    GOLESTAN_CODES,
    RACECOURSES,
    Racecourse,
    ensure_racecourse,
    get_racecourse,
    is_code_allowed,
    is_racecourse_allowed,
    normalize_track_key,
    parse_allowed_codes,
    resolve_racecourse,
    synthesize_racecourse,
)
from src.racecourses.scope import (
    OutOfScopeRacecourseError,
    allowed_codes_from_settings,
    ensure_track_in_scope,
)

__all__ = [
    "DEFAULT_ALLOWED_CODES",
    "GOLESTAN_CODES",
    "OutOfScopeRacecourseError",
    "RACECOURSES",
    "Racecourse",
    "allowed_codes_from_settings",
    "ensure_racecourse",
    "ensure_track_in_scope",
    "get_racecourse",
    "is_code_allowed",
    "is_racecourse_allowed",
    "normalize_track_key",
    "parse_allowed_codes",
    "resolve_racecourse",
    "synthesize_racecourse",
]
