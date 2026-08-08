"""Tests for speed history parse and fastest-by-breed ranking."""

from __future__ import annotations

from src.speed.history import is_plausible_timed_start, parse_history_html
from src.speed.report import build_fastest_report


SAMPLE_HTML = r"""
<html><body><script>
self.__next_f.push([1,"c:{\"data\":[{\"id\":\"r1\",\"rank\":1,\"time\":57500,\"isRun\":true,\"entranceRating\":10,\"race\":{\"id\":\"race1\",\"name\":\"آزمایش\",\"week\":{\"id\":\"w1\",\"name\":\"هفته 1 گنبدکاووس 1403\",\"date\":\"2024-01-01T00:00:00.000Z\"},\"plan\":{\"distance\":1000,\"blood\":null,\"name\":\"1000\"}}}],\"page\":1,\"pageSize\":20,\"totalPages\":1}"])
</script></body></html>
"""


def test_parse_history_html_times():
    parsed = parse_history_html(SAMPLE_HTML)
    assert parsed["total_pages"] == 1
    assert len(parsed["starts"]) == 1
    st = parsed["starts"][0]
    assert st["time_s"] == 57.5
    assert st["distance"] == 1000
    assert st["speed_mps"] == 17.3913
    assert st["time_fmt"] == "57.500"


def test_build_fastest_report_ranks_by_breed():
    harvest = [
        {
            "source_id": "h1",
            "name": "سریع۱",
            "blood": "TURKMEN",
            "harvest_status": "OK",
            "timed_starts_count": 3,
            "starts": [
                {"distance": 1000, "time_s": 58.0, "time_fmt": "58.000", "speed_mps": 17.2414, "race_date": "2024-01-01", "track": "گنبدکاووس", "finish_position": 1, "race_name": "a"},
                {"distance": 1000, "time_s": 59.0, "time_fmt": "59.000", "speed_mps": 16.9492, "race_date": "2024-01-02", "track": "گنبدکاووس", "finish_position": 2, "race_name": "b"},
                {"distance": 1200, "time_s": 72.0, "time_fmt": "1:12.000", "speed_mps": 16.6667, "race_date": "2024-01-03", "track": "گنبدکاووس", "finish_position": 1, "race_name": "c"},
            ],
        },
        {
            "source_id": "h2",
            "name": "سریع۲",
            "blood": "TURKMEN",
            "harvest_status": "OK",
            "timed_starts_count": 3,
            "starts": [
                {"distance": 1000, "time_s": 57.0, "time_fmt": "57.000", "speed_mps": 17.5439, "race_date": "2024-02-01", "track": "آق‌قلا", "finish_position": 1, "race_name": "d"},
                {"distance": 1000, "time_s": 58.5, "time_fmt": "58.500", "speed_mps": 17.0940, "race_date": "2024-02-02", "track": "آق‌قلا", "finish_position": 1, "race_name": "e"},
                {"distance": 1000, "time_s": 58.8, "time_fmt": "58.800", "speed_mps": 17.0068, "race_date": "2024-02-03", "track": "آق‌قلا", "finish_position": 3, "race_name": "f"},
            ],
        },
    ]
    # mark plausible
    for row in harvest:
        for st in row["starts"]:
            assert is_plausible_timed_start(st)

    report = build_fastest_report(harvest, top_n=5)
    turk = report["by_breed"]["TURKMEN"]
    assert turk["top_by_peak_speed"][0]["name"] == "سریع۲"
    assert turk["records_by_distance"]["1000"][0]["name"] == "سریع۲"
    assert turk["records_by_distance"]["1000"][0]["time_fmt"] == "57.000"
