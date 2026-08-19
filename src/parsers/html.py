"""Shared HTML / RSC JSON extraction utilities."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup
from loguru import logger

from src.utils.retry import ParseError


def unescape_js_string_fragment(text: str) -> str:
    """Unescape common JS string escapes used in Next.js flight payloads."""
    out: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch == "\\" and i + 1 < length:
            nxt = text[i + 1]
            if nxt == '"':
                out.append('"')
                i += 2
            elif nxt == "n":
                out.append("\n")
                i += 2
            elif nxt == "t":
                out.append("\t")
                i += 2
            elif nxt == "/":
                out.append("/")
                i += 2
            elif nxt == "\\":
                out.append("\\")
                i += 2
            elif nxt == "u" and i + 5 < length:
                out.append(chr(int(text[i + 2 : i + 6], 16)))
                i += 6
            else:
                out.append(ch)
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def extract_next_flight_text(html: str) -> str:
    """Concatenate and unescape all Next.js `self.__next_f.push([1,"..."])` payloads."""
    parts = re.findall(
        r"self\.__next_f\.push\(\[1,\"((?:\\.|[^\"\\])*)\"\]\)",
        html,
    )
    if not parts:
        # Fallback: unescape whole document (still useful for fixtures)
        return unescape_js_string_fragment(html)
    return unescape_js_string_fragment("".join(parts))


def extract_balanced_json_object(text: str, start_index: int = 0) -> str:
    """Extract a JSON object starting at the first `{` at/after start_index."""
    i = text.find("{", start_index)
    if i < 0:
        raise ParseError("No JSON object start found")

    depth = 0
    in_str = False
    esc = False
    for j, ch in enumerate(text[i:], i):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    raise ParseError("Unbalanced JSON object")


def extract_balanced_json_value(text: str, start_index: int = 0) -> Any:
    """Extract and parse the next JSON value (object or array) from text."""
    i = start_index
    while i < len(text) and text[i] in " \t\r\n:":
        i += 1
    if i >= len(text):
        raise ParseError("No JSON value found")

    if text[i] == "{":
        raw = extract_balanced_json_object(text, i)
        return json.loads(raw)

    if text[i] == "[":
        depth = 0
        in_str = False
        esc = False
        for j, ch in enumerate(text[i:], i):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return json.loads(text[i : j + 1])
        raise ParseError("Unbalanced JSON array")

    raise ParseError(f"Unsupported JSON value start: {text[i]!r}")


def extract_json_after_marker(html: str, marker: str) -> Any:
    """
    Find `marker` in HTML or in unescaped Next.js flight text, then parse the
    following JSON value (object or array).
    """
    candidates = [html, extract_next_flight_text(html)]
    last_error: Exception | None = None

    for text in candidates:
        idx = text.find(marker)
        if idx < 0:
            # Try common escaped form inside raw HTML
            escaped = marker.replace('"', '\\"')
            idx = text.find(escaped)
            if idx >= 0:
                text = unescape_js_string_fragment(text[idx:])
                idx = text.find(marker)
                if idx < 0:
                    idx = 0
                    # after unescape, marker should be at start-ish
                    found = text.find(marker)
                    if found >= 0:
                        idx = found
                    else:
                        continue
            else:
                continue

        fragment = text[idx:]
        value_start = 0
        if fragment.startswith(marker):
            value_start = len(marker)
        elif ":" in marker:
            colon = fragment.find(":")
            value_start = colon + 1 if colon >= 0 else 0

        try:
            return extract_balanced_json_value(fragment, value_start)
        except (json.JSONDecodeError, ParseError) as exc:
            last_error = exc
            continue

    raise ParseError(f"Invalid JSON after marker {marker}: {last_error}")


def soup_from_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.debug("Could not parse float from {!r}", value)
        return None


def safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            logger.debug("Could not parse int from {!r}", value)
            return None


def find_all_hrefs(html: str, pattern: str) -> list[str]:
    soup = soup_from_html(html)
    regex = re.compile(pattern)
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if regex.search(href):
            links.append(href)
    return links
