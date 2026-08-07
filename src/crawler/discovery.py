"""Discover historical week IDs and per-round race URLs from asbdavani HTML."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

from loguru import logger

from src.asbdavani.constants import (
    BASE_URL,
    absolute_url,
    location_from_week_and_leagues,
    parse_race_url,
)
from src.asbdavani.parsers.race import build_race_url, parse_race_list_html
from src.parsers.html import extract_json_after_marker, find_all_hrefs
from src.racecourses import is_racecourse_allowed, resolve_racecourse
from src.utils.retry import ParseError


@dataclass(frozen=True, slots=True)
class DiscoveredWeek:
    week_id: str
    location: str | None = None
    league_id: str | None = None
    week_name: str | None = None

    @property
    def racecourse_code(self) -> str | None:
        course = resolve_racecourse(self.location)
        return course.code if course else None


def discover_weeks(
    html: str,
    *,
    allowed_codes: frozenset[str] | None | object = ...,
) -> list[DiscoveredWeek]:
    """
    Discover racecard weeks with optional racecourse filtering.

    ``allowed_codes``:
      - ellipsis (default): no filter (caller may filter)
      - frozenset: only matching known racecourses
      - None: nationwide (``*``) — all weeks
    """
    by_id: dict[str, DiscoveredWeek] = {}

    def _put(
        week_id: str,
        *,
        location: str | None = None,
        league_id: str | None = None,
        week_name: str | None = None,
    ) -> None:
        existing = by_id.get(week_id)
        if existing is None:
            by_id[week_id] = DiscoveredWeek(
                week_id=week_id,
                location=location,
                league_id=league_id,
                week_name=week_name,
            )
            return
        # Prefer richer metadata when merging sources
        by_id[week_id] = DiscoveredWeek(
            week_id=week_id,
            location=location or existing.location,
            league_id=league_id or existing.league_id,
            week_name=week_name or existing.week_name,
        )

    for item in parse_race_list_html(html, BASE_URL):
        if item.get("sourceId"):
            _put(item["sourceId"])

    for href in find_all_hrefs(html, r"/racecards/[A-Za-z0-9]+"):
        week_id, _ = parse_race_url(absolute_url(href))
        if week_id:
            _put(week_id)

    try:
        leagues = extract_json_after_marker(html, '"leagues":')
        if isinstance(leagues, list):
            for league in leagues:
                if not isinstance(league, dict):
                    continue
                loc = (league.get("location") or {}).get("name")
                league_id = league.get("id")
                for week in league.get("weeks") or []:
                    if isinstance(week, dict) and week.get("id"):
                        _put(
                            str(week["id"]),
                            location=loc,
                            league_id=str(league_id) if league_id else None,
                            week_name=week.get("name"),
                        )
                    elif isinstance(week, str):
                        _put(week, location=loc, league_id=str(league_id) if league_id else None)
    except ParseError:
        logger.debug("No leagues payload while discovering weeks")

    try:
        active = extract_json_after_marker(html, '"activeWeeks":')
        if isinstance(active, list):
            for week in active:
                if isinstance(week, dict) and week.get("id"):
                    loc = location_from_week_and_leagues(week, None)
                    _put(
                        str(week["id"]),
                        location=loc or week.get("location"),
                        league_id=str(week["leagueId"]) if week.get("leagueId") else None,
                        week_name=week.get("name"),
                    )
    except ParseError:
        pass

    weeks = sorted(by_id.values(), key=lambda w: w.week_id)

    if allowed_codes is ...:
        logger.info("Discovered {} weeks (unfiltered)", len(weeks))
        return weeks

    # When filtering: keep weeks with known allowed location; also keep
    # weeks with unknown location so the week handler can resolve later.
    kept: list[DiscoveredWeek] = []
    skipped = 0
    for week in weeks:
        if week.location is None:
            kept.append(week)
            continue
        if is_racecourse_allowed(week.location, allowed_codes=allowed_codes):  # type: ignore[arg-type]
            kept.append(week)
        else:
            skipped += 1

    logger.info(
        "Discovered {} weeks in scope (skipped {} out-of-scope with known location)",
        len(kept),
        skipped,
    )
    return kept


def discover_week_ids(
    html: str,
    *,
    allowed_codes: frozenset[str] | None | object = ...,
) -> list[str]:
    """Backward-compatible week-id list (optionally scoped)."""
    return [w.week_id for w in discover_weeks(html, allowed_codes=allowed_codes)]


def week_url(week_id: str) -> str:
    return absolute_url(f"/racecards/{week_id}")


def location_from_week_html(html: str) -> str | None:
    """Resolve racecourse / location name from a week or race page HTML."""
    try:
        week = extract_json_after_marker(html, '_weekInfo":')
    except ParseError:
        try:
            week = extract_json_after_marker(html, '"_weekInfo":')
        except ParseError:
            return None

    leagues: list[dict[str, Any]] | None = None
    try:
        leagues_obj = extract_json_after_marker(html, '"leagues":')
        if isinstance(leagues_obj, list):
            leagues = leagues_obj
    except ParseError:
        pass

    return location_from_week_and_leagues(week, leagues)


def discover_race_urls_from_week_html(html: str, week_url_or_id: str) -> list[str]:
    """
    Expand a week page into per-round race URLs using `_weekInfo.races[].round`.
    """
    week_id, _ = parse_race_url(week_url_or_id)
    if not week_id:
        # bare id
        if "/" not in week_url_or_id and "?" not in week_url_or_id:
            week_id = week_url_or_id
        else:
            raise ParseError(f"Cannot parse week id from {week_url_or_id!r}")

    try:
        week = extract_json_after_marker(html, '_weekInfo":')
    except ParseError:
        week = extract_json_after_marker(html, '"_weekInfo":')

    races = week.get("races") or []
    rounds: set[int] = set()
    for race in races:
        if not isinstance(race, dict):
            continue
        rnd = race.get("round")
        if rnd is None:
            continue
        try:
            rounds.add(int(rnd))
        except (TypeError, ValueError):
            continue

    urls = [build_race_url(week_id, rnd) for rnd in sorted(rounds)]
    logger.info("Week {} expanded to {} race URLs", week_id, len(urls))
    return urls


def normalize_job_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(fragment=""))
