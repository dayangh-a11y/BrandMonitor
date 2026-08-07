"""Discover historical week IDs and per-round race URLs from asbdavani HTML."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

from loguru import logger

from src.asbdavani.constants import BASE_URL, absolute_url, parse_race_url
from src.asbdavani.parsers.race import build_race_url, parse_race_list_html
from src.parsers.html import extract_json_after_marker, find_all_hrefs
from src.utils.retry import ParseError


def discover_week_ids(html: str) -> list[str]:
    """
    Discover all racecard week IDs from the listing page.

    Combines:
    - visible /racecards/{id} hrefs
    - leagues[].weeks[].id embedded in Next.js RSC payload (historical archive)
    """
    ids: set[str] = set()

    for item in parse_race_list_html(html, BASE_URL):
        if item.get("sourceId"):
            ids.add(item["sourceId"])

    # Href fallback (path segment)
    for href in find_all_hrefs(html, r"/racecards/[A-Za-z0-9]+"):
        week_id, _ = parse_race_url(absolute_url(href))
        if week_id:
            ids.add(week_id)

    # Deep archive from leagues payload
    try:
        leagues = extract_json_after_marker(html, '"leagues":')
        if isinstance(leagues, list):
            for league in leagues:
                if not isinstance(league, dict):
                    continue
                for week in league.get("weeks") or []:
                    if isinstance(week, dict) and week.get("id"):
                        ids.add(str(week["id"]))
                    elif isinstance(week, str):
                        ids.add(week)
    except ParseError:
        logger.debug("No leagues payload while discovering week ids")

    # activeWeeks on page
    try:
        active = extract_json_after_marker(html, '"activeWeeks":')
        if isinstance(active, list):
            for week in active:
                if isinstance(week, dict) and week.get("id"):
                    ids.add(str(week["id"]))
    except ParseError:
        pass

    result = sorted(ids)
    logger.info("Discovered {} week ids from racecards HTML", len(result))
    return result


def week_url(week_id: str) -> str:
    return absolute_url(f"/racecards/{week_id}")


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
