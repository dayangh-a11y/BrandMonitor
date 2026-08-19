"""Parse asbdavani horse pedigree chart HTML into structured ancestors.

Source pages: ``/performance/horses/{id}/pedigree``

Chart convention (observed):
- Column 0 = parents (generation 1): blue rowspan-8 = sire, red rowspan-8 = dam
- Column 1 = grandparents (generation 2)
- Blue cells ≈ male line; red cells ≈ female line
- Empty slots are ``#`` / ``-``

Never invent missing ancestors — return null.
"""

from __future__ import annotations

import re
from typing import Any

_SUBJECT_RE = re.compile(
    r'content="پدیگری اسب\s*([^"|]+?)\s*(?:\||")'
)
_TABLE_RE = re.compile(r"<table[\s\S]*?</table>", re.I)
_ROW_RE = re.compile(r"<tr[\s\S]*?</tr>", re.I)
_CELL_RE = re.compile(r"<t[dh]([^>]*)>([\s\S]*?)</t[dh]>", re.I)
_ROWSPAN_RE = re.compile(r'rowspan="(\d+)"', re.I)
_LINK_RE = re.compile(r'href="([^"]+)"[^>]*>([^<]*)')
_SID_RE = re.compile(r"/performance/horses/([^/]+)/")


def _cell_info(attrs: str, content: str) -> dict[str, Any]:
    if "blue" in attrs:
        sex_color = "blue"
    elif "red" in attrs:
        sex_color = "red"
    else:
        sex_color = "other"
    rs = _ROWSPAN_RE.search(attrs)
    rowspan = int(rs.group(1)) if rs else 1
    name: str | None = None
    source_id: str | None = None
    external: str | None = None
    for href, text in _LINK_RE.findall(content):
        text = text.strip()
        if "pedigreequery.com" in href:
            external = href
            continue
        if text in ("پدیگری", ""):
            continue
        if "/performance/horses/" in href and text and text != "-":
            mm = _SID_RE.search(href)
            source_id = mm.group(1) if mm else None
            name = text
        elif href == "#" and text == "-":
            name = None
    if name is None:
        plain = re.sub(r"<[^>]+>", "", content).replace("پدیگری", "").strip()
        if plain and plain != "-":
            name = plain
    return {
        "sex_color": sex_color,
        "rowspan": rowspan,
        "name": name,
        "source_id": source_id,
        "external": external,
    }


def _pack(cell: dict[str, Any] | None) -> dict[str, Any] | None:
    if not cell or not cell.get("name"):
        return None
    sex_hint = None
    if cell["sex_color"] == "blue":
        sex_hint = "M"
    elif cell["sex_color"] == "red":
        sex_hint = "F"
    return {
        "name": str(cell["name"]).strip(),
        "source_id": cell.get("source_id"),
        "external_url": cell.get("external"),
        "sex_hint": sex_hint,
    }


def _place_cells(table_html: str) -> list[tuple[int, int, dict[str, Any]]]:
    rows = _ROW_RE.findall(table_html)
    occ: set[tuple[int, int]] = set()
    placements: list[tuple[int, int, dict[str, Any]]] = []
    r_idx = 0
    for row in rows:
        cells = _CELL_RE.findall(row)
        col = 0
        for attrs, content in cells:
            cell = _cell_info(attrs, content)
            while (r_idx, col) in occ:
                col += 1
            for dr in range(cell["rowspan"]):
                occ.add((r_idx + dr, col))
            placements.append((r_idx, col, cell))
            col += 1
        r_idx += 1
    return placements


def parse_pedigree_html(html: str, subject_source_id: str) -> dict[str, Any]:
    """Return structured pedigree for one subject horse from page HTML."""
    m = _SUBJECT_RE.search(html)
    subject_name = m.group(1).strip() if m else None

    tables = _TABLE_RE.findall(html)
    if not tables:
        return {
            "subject_source_id": subject_source_id,
            "subject_name": subject_name,
            "sire": None,
            "dam": None,
            "sire_sire": None,
            "sire_dam": None,
            "dam_sire": None,
            "dam_dam": None,
            "parse_status": "NO_TABLE",
            "named_ancestor_count": 0,
        }

    placements = _place_cells(tables[0])
    gen1 = [(r, c, cell) for r, c, cell in placements if c == 0]
    gen2 = [(r, c, cell) for r, c, cell in placements if c == 1]

    sire = next(
        (cell for r, c, cell in gen1 if cell["sex_color"] == "blue" and cell["rowspan"] >= 8),
        None,
    )
    dam = next(
        (cell for r, c, cell in gen1 if cell["sex_color"] == "red" and cell["rowspan"] >= 8),
        None,
    )
    sire_sire = next(
        (
            cell
            for r, c, cell in gen2
            if r < 8 and cell["sex_color"] == "blue" and cell["rowspan"] >= 4
        ),
        None,
    )
    sire_dam = next(
        (
            cell
            for r, c, cell in gen2
            if r < 8 and cell["sex_color"] == "red" and cell["rowspan"] >= 4
        ),
        None,
    )
    dam_sire = next(
        (
            cell
            for r, c, cell in gen2
            if r >= 8 and cell["sex_color"] == "blue" and cell["rowspan"] >= 4
        ),
        None,
    )
    dam_dam = next(
        (
            cell
            for r, c, cell in gen2
            if r >= 8 and cell["sex_color"] == "red" and cell["rowspan"] >= 4
        ),
        None,
    )

    packed = {
        "sire": _pack(sire),
        "dam": _pack(dam),
        "sire_sire": _pack(sire_sire),
        "sire_dam": _pack(sire_dam),
        "dam_sire": _pack(dam_sire),
        "dam_dam": _pack(dam_dam),
    }
    named = sum(1 for v in packed.values() if v is not None)
    return {
        "subject_source_id": subject_source_id,
        "subject_name": subject_name,
        **packed,
        "parse_status": "OK" if named else "EMPTY_CHART",
        "named_ancestor_count": named,
    }
