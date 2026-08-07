"""Racecourse registry + crawl scope filtering."""

from __future__ import annotations

import json

from src.crawler.discovery import discover_week_ids, discover_weeks
from src.racecourses import (
    DEFAULT_ALLOWED_CODES,
    is_racecourse_allowed,
    normalize_track_key,
    parse_allowed_codes,
    resolve_racecourse,
)


def test_resolve_golestan_aliases() -> None:
    assert resolve_racecourse("گنبدکاووس").code == "gonbad-kavous"
    assert resolve_racecourse("گنبد کاووس").code == "gonbad-kavous"
    assert resolve_racecourse("آق‌ قلا").code == "aq-qala"
    assert resolve_racecourse("آق قلا").code == "aq-qala"
    assert resolve_racecourse("بندرترکمن").code == "bandar-torkaman"
    assert resolve_racecourse("بندر ترکمن").code == "bandar-torkaman"
    assert resolve_racecourse("مشهد") is None


def test_golestan_coordinates_present() -> None:
    from src.racecourses import get_racecourse

    g = get_racecourse("gonbad-kavous")
    assert g and g.latitude and g.longitude
    assert get_racecourse("aq-qala").latitude
    assert get_racecourse("bandar-torkaman").longitude


def test_normalize_strips_zwnj_and_spaces() -> None:
    assert normalize_track_key("آق‌ قلا") == normalize_track_key("آق قلا")
    assert normalize_track_key("بندر ترکمن") == normalize_track_key("بندرترکمن")


def test_default_allowlist_is_golestan_triad() -> None:
    codes = parse_allowed_codes(None)
    assert codes == frozenset(DEFAULT_ALLOWED_CODES)
    assert "gonbad-kavous" in codes
    assert "aq-qala" in codes
    assert "bandar-torkaman" in codes
    assert parse_allowed_codes("*") is None


def test_allowlist_rejects_other_tracks() -> None:
    allowed = parse_allowed_codes("gonbad-kavous,aq-qala,bandar-torkaman")
    assert is_racecourse_allowed("گنبدکاووس", allowed_codes=allowed)
    assert is_racecourse_allowed("آق قلا", allowed_codes=allowed)
    assert is_racecourse_allowed("بندرترکمن", allowed_codes=allowed)
    assert not is_racecourse_allowed("مشهد", allowed_codes=allowed)
    assert not is_racecourse_allowed("تهران", allowed_codes=allowed)


def test_discover_weeks_filters_out_of_scope_locations() -> None:
    leagues = [
        {
            "id": "L1",
            "location": {"name": "مشهد"},
            "weeks": [{"id": "week-mashhad"}],
        },
        {
            "id": "L2",
            "location": {"name": "گنبدکاووس"},
            "weeks": [{"id": "week-gonbad"}],
        },
        {
            "id": "L3",
            "location": {"name": "آق قلا"},
            "weeks": [{"id": "week-aq"}],
        },
    ]
    html = f'"leagues":{json.dumps(leagues, ensure_ascii=False)}'
    allowed = parse_allowed_codes("gonbad-kavous,aq-qala,bandar-torkaman")
    weeks = discover_weeks(html, allowed_codes=allowed)
    ids = {w.week_id for w in weeks}
    assert "week-gonbad" in ids
    assert "week-aq" in ids
    assert "week-mashhad" not in ids


def test_discover_week_ids_unfiltered_keeps_all() -> None:
    leagues = [
        {
            "id": "L1",
            "location": {"name": "مشهد"},
            "weeks": [{"id": "week-mashhad"}],
        }
    ]
    html = (
        '<a href="/racecards/weekhref1"></a>'
        f'"leagues":{json.dumps(leagues, ensure_ascii=False)}'
    )
    ids = discover_week_ids(html)
    assert "weekhref1" in ids
    assert "week-mashhad" in ids
