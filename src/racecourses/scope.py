"""Crawl-scope helpers and out-of-scope signal."""

from __future__ import annotations

from src.racecourses.registry import (
    Racecourse,
    is_code_allowed,
    is_racecourse_allowed,
    parse_allowed_codes,
    resolve_racecourse,
)
from src.utils.settings import Settings


class OutOfScopeRacecourseError(Exception):
    """Raised when a race/week is outside the configured racecourse allowlist."""

    def __init__(
        self,
        *,
        track: str | None,
        racecourse_code: str | None = None,
        message: str | None = None,
    ) -> None:
        self.track = track
        self.racecourse_code = racecourse_code
        super().__init__(
            message
            or f"Racecourse out of crawl scope: track={track!r} code={racecourse_code!r}"
        )


def allowed_codes_from_settings(settings: Settings) -> frozenset[str] | None:
    return parse_allowed_codes(settings.crawl_allowed_racecourses)


def ensure_track_in_scope(
    track: str | None,
    *,
    settings: Settings,
    racecourse_code: str | None = None,
) -> Racecourse | None:
    """
    Validate track against allowlist.

    Returns the resolved Racecourse when in scope (may be None only if
    allowlist is ``*`` and track is unknown). Raises OutOfScopeRacecourseError
    when filtered out.
    """
    allowed = allowed_codes_from_settings(settings)
    course = resolve_racecourse(track) if track else None
    code = racecourse_code or (course.code if course else None)

    if allowed is None:
        return course

    if code and is_code_allowed(code, allowed_codes=allowed):
        return course or resolve_racecourse(track)

    if is_racecourse_allowed(track, allowed_codes=allowed):
        return resolve_racecourse(track)

    raise OutOfScopeRacecourseError(track=track, racecourse_code=code)
