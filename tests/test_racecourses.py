"""Racecourse registry + crawl scope filtering."""

from __future__ import annotations

import json

from src.crawler.discovery import discover_week_ids, discover_weeks
from src.racecourses import (
    GOLESTAN_CODES,
    ensure_racecourse,
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


def test_resolve_nationwide_cities() -> None:
    assert resolve_racecourse("تهران").code == "tehran"
    assert resolve_racecourse("یزد").code == "yazd"
    assert resolve_racecourse("اهواز").code == "ahvaz"
    assert resolve_racecourse("کیش").code == "kish"
    assert resolve_racecourse("انبارآلوم").code == "anbar-alum"
    assert resolve_racecourse("انبار آلوم").code == "anbar-alum"
    assert resolve_racecourse("مشهد").code == "mashhad"


def test_ensure_racecourse_synthesizes_unknown() -> None:
    course = ensure_racecourse("شهر جدید فرضی")
    assert course.code.startswith("ir-")
    assert course.name_fa == "شهر جدید فرضی"
    # Deterministic for the same label
    assert ensure_racecourse("شهر جدید فرضی").code == course.code


def test_golestan_coordinates_present() -> None:
    from src.racecourses import get_racecourse

    g = get_racecourse("gonbad-kavous")
    assert g and g.latitude and g.longitude
    assert get_racecourse("aq-qala").latitude
    assert get_racecourse("bandar-torkaman").longitude
    assert get_racecourse("tehran").latitude
    assert get_racecourse("mashhad").longitude


def test_normalize_strips_zwnj_and_spaces() -> None:
    assert normalize_track_key("آق‌ قلا") == normalize_track_key("آق قلا")
    assert normalize_track_key("بندر ترکمن") == normalize_track_key("بندرترکمن")


def test_default_allowlist_is_nationwide() -> None:
    assert parse_allowed_codes(None) is None
    assert parse_allowed_codes("") is None
    assert parse_allowed_codes("*") is None
    assert set(GOLESTAN_CODES) == {
        "gonbad-kavous",
        "aq-qala",
        "bandar-torkaman",
    }


def test_allowlist_rejects_other_tracks() -> None:
    allowed = parse_allowed_codes("gonbad-kavous,aq-qala,bandar-torkaman")
    assert is_racecourse_allowed("گنبدکاووس", allowed_codes=allowed)
    assert is_racecourse_allowed("آق قلا", allowed_codes=allowed)
    assert is_racecourse_allowed("بندرترکمن", allowed_codes=allowed)
    assert not is_racecourse_allowed("مشهد", allowed_codes=allowed)
    assert not is_racecourse_allowed("تهران", allowed_codes=allowed)


def test_nationwide_allows_all_locations() -> None:
    assert is_racecourse_allowed("مشهد", allowed_codes=None)
    assert is_racecourse_allowed("تهران", allowed_codes=None)
    assert is_racecourse_allowed("unknown-city", allowed_codes=None)


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


def test_discover_weeks_nationwide_keeps_all() -> None:
    leagues = [
        {
            "id": "L1",
            "location": {"name": "مشهد"},
            "weeks": [{"id": "week-mashhad"}],
        },
        {
            "id": "L2",
            "location": {"name": "تهران"},
            "weeks": [{"id": "week-tehran"}],
        },
    ]
    html = f'"leagues":{json.dumps(leagues, ensure_ascii=False)}'
    weeks = discover_weeks(html, allowed_codes=None)
    ids = {w.week_id for w in weeks}
    assert "week-mashhad" in ids
    assert "week-tehran" in ids


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
