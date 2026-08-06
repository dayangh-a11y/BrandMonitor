"""Unit tests for RSC / HTML JSON extraction helpers."""

from __future__ import annotations

import json

import pytest

from src.parsers.html import (
    extract_json_after_marker,
    unescape_js_string_fragment,
)
from src.utils.retry import ParseError


def test_unescape_js_string_fragment() -> None:
    raw = r'{\"name\":\"تست\",\"n\":1}'
    assert unescape_js_string_fragment(raw) == '{"name":"تست","n":1}'


def test_extract_week_info_from_escaped_payload() -> None:
    week = {
        "id": "week1",
        "name": "هفته 1 مشهد 1405",
        "date": "2026-08-07T00:00:00.000Z",
        "races": [
            {
                "id": "r1",
                "round": 1,
                "name": "مبتدی",
                "plan": {"distance": 1000, "blood": "TURKMEN"},
                "prize": {"name": "P", "prizes": [{"rank": 1, "prize": 1000}]},
                "raceHorses": [],
            }
        ],
    }
    embedded = json.dumps(week, ensure_ascii=False).replace('"', r'\"')
    html = f'<script>self.__next_f.push([1,"x:["_weekInfo\\":{embedded}]"])</script>'
    # Build a more realistic fragment
    html = (
        '<script>self.__next_f.push([1,"'
        + r'$L18",null,{"_weekInfo\":'
        + embedded
        + r',"raceNumber\":1}'
        + '"])</script>'
    )
    parsed = extract_json_after_marker(html, '_weekInfo":')
    assert parsed["id"] == "week1"
    assert parsed["races"][0]["round"] == 1


def test_extract_marker_missing() -> None:
    with pytest.raises(ParseError):
        extract_json_after_marker("<html></html>", '_weekInfo":')
