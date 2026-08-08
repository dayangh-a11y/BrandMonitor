"""Unit tests for breeding productions parse + ranking."""

from __future__ import annotations

from src.breeding.productions import parse_productions_html
from src.breeding.report import build_breeding_value_report


SAMPLE_HTML = r"""
<html><body><script>
self.__next_f.push([1,"c:{\"data\":[{\"id\":\"kid1\",\"name\":\"کره۱\",\"blood\":\"TURKMEN\",\"sex\":\"MALE\",\"birthdate\":null,\"breed\":\"UNKNOWN\",\"p1\":2,\"p2\":1,\"p3\":0,\"starts\":10,\"ior\":0,\"mother\":{\"id\":\"dam1\",\"name\":\"مادیان\"},\"father\":{\"id\":\"sire1\",\"name\":\"نریان\"}}],\"page\":1,\"pageSize\":20,\"totalPages\":1}"])
</script></body></html>
"""


def test_parse_productions_html_extracts_offspring():
    parsed = parse_productions_html(SAMPLE_HTML)
    assert parsed["total_pages"] == 1
    assert len(parsed["offspring"]) == 1
    kid = parsed["offspring"][0]
    assert kid["name"] == "کره۱"
    assert kid["blood"] == "TURKMEN"
    assert kid["wins"] == 2
    assert kid["seconds"] == 1
    assert kid["starts"] == 10


def test_build_breeding_value_report_ranks_by_breed():
    harvest = [
        {
            "parent_source_id": "sire_a",
            "parent_entity_id": "src:sire_a",
            "parent_name": "نریان‌الف",
            "role": "SIRE",
            "harvest_status": "OK",
            "offspring_count": 3,
            "offspring": [
                {"blood": "TURKMEN", "wins": 3, "seconds": 0, "thirds": 0, "starts": 8},
                {"blood": "TURKMEN", "wins": 1, "seconds": 1, "thirds": 0, "starts": 5},
                {"blood": "TURKMEN", "wins": 0, "seconds": 0, "thirds": 1, "starts": 4},
            ],
        },
        {
            "parent_source_id": "sire_b",
            "parent_entity_id": "src:sire_b",
            "parent_name": "نریان‌ب",
            "role": "SIRE",
            "harvest_status": "OK",
            "offspring_count": 3,
            "offspring": [
                {"blood": "TURKMEN", "wins": 1, "seconds": 0, "thirds": 0, "starts": 6},
                {"blood": "TURKMEN", "wins": 1, "seconds": 0, "thirds": 0, "starts": 6},
                {"blood": "TURKMEN", "wins": 0, "seconds": 0, "thirds": 0, "starts": 4},
            ],
        },
        {
            "parent_source_id": "dam_a",
            "parent_entity_id": "src:dam_a",
            "parent_name": "مادیان‌الف",
            "role": "DAM",
            "harvest_status": "OK",
            "offspring_count": 3,
            "offspring": [
                {"blood": "TURKMEN", "wins": 2, "seconds": 2, "thirds": 0, "starts": 9},
                {"blood": "TURKMEN", "wins": 1, "seconds": 0, "thirds": 1, "starts": 5},
                {"blood": "TURKMEN", "wins": 0, "seconds": 1, "thirds": 0, "starts": 3},
            ],
        },
    ]
    report = build_breeding_value_report(harvest, top_n=5)
    turk = report["by_breed"]["TURKMEN"]
    assert turk["best_stallion_by_prv"]["parent_name"] == "نریان‌الف"
    assert turk["best_mare_by_prv"]["parent_name"] == "مادیان‌الف"
    assert report["headlines"][0]["breed"] == "ترکمن"
