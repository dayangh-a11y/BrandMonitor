"""Shared parsers package."""

from src.parsers.html import (
    extract_json_after_marker,
    extract_next_flight_text,
    find_all_hrefs,
    safe_float,
    safe_int,
    soup_from_html,
)

__all__ = [
    "extract_json_after_marker",
    "extract_next_flight_text",
    "find_all_hrefs",
    "safe_float",
    "safe_int",
    "soup_from_html",
]
