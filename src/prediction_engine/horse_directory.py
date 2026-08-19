"""Searchable horse-name directory for the HTTP API (not Telegram-DB access).

Names are loaded from optional identity sidecars / pedigree links. Freeze
observations often lack display names; this directory fills that gap without
changing scoring or analysis logic.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


_WS_RE = re.compile(r"\s+")


def normalize_horse_name(value: str) -> str:
    """Lightweight normalize for Persian/Latin search (no heavy deps)."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    # Common Persian/Arabic Yeh/Kaf variants
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.casefold()
    text = _WS_RE.sub(" ", text)
    return text


@dataclass(frozen=True, slots=True)
class HorseNameRecord:
    horse_id: int
    horse_name: str
    breed: str | None = None
    sex: str | None = None
    birth_year: int | None = None
    aliases: tuple[str, ...] = ()

    def to_search_dict(self) -> dict[str, Any]:
        return {
            "horse_id": self.horse_id,
            "horse_name": self.horse_name,
            "breed": self.breed,
            "sex": self.sex,
            "birth_year": self.birth_year,
        }


class HorseNameDirectory:
    """In-memory name → horse_id index."""

    def __init__(self, records: Iterable[HorseNameRecord] | None = None) -> None:
        self._by_id: dict[int, HorseNameRecord] = {}
        for rec in records or []:
            self.add(rec)

    def add(self, rec: HorseNameRecord) -> None:
        existing = self._by_id.get(rec.horse_id)
        if existing is None:
            self._by_id[rec.horse_id] = rec
            return
        # Merge aliases / fill missing fields; keep first non-empty name.
        aliases = tuple(
            dict.fromkeys(
                [*(existing.aliases or ()), existing.horse_name, rec.horse_name, *(rec.aliases or ())]
            )
        )
        self._by_id[rec.horse_id] = HorseNameRecord(
            horse_id=rec.horse_id,
            horse_name=existing.horse_name or rec.horse_name,
            breed=existing.breed or rec.breed,
            sex=existing.sex or rec.sex,
            birth_year=existing.birth_year if existing.birth_year is not None else rec.birth_year,
            aliases=tuple(a for a in aliases if a and a != (existing.horse_name or rec.horse_name)),
        )

    def __len__(self) -> int:
        return len(self._by_id)

    def get(self, horse_id: int) -> HorseNameRecord | None:
        return self._by_id.get(int(horse_id))

    def search(self, name: str, *, limit: int = 20) -> list[HorseNameRecord]:
        q = normalize_horse_name(name)
        if not q or limit < 1:
            return []
        exact: list[HorseNameRecord] = []
        partial: list[HorseNameRecord] = []
        for rec in self._by_id.values():
            candidates = [rec.horse_name, *rec.aliases]
            norms = [normalize_horse_name(c) for c in candidates if c]
            if any(n == q for n in norms):
                exact.append(rec)
            elif any(q in n or n in q for n in norms if n):
                partial.append(rec)
        # Stable: exact first, then shorter names, then horse_id
        exact.sort(key=lambda r: (len(r.horse_name), r.horse_id))
        partial.sort(key=lambda r: (len(r.horse_name), r.horse_id))
        out = exact + [r for r in partial if r not in exact]
        return out[:limit]


def load_records_from_mapping_file(path: Path) -> list[HorseNameRecord]:
    """Load ``{\"horses\":[{\"horse_id\", \"horse_name\", ...}]}`` sidecars."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("horses") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    out: list[HorseNameRecord] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            hid = int(item.get("horse_id"))
        except (TypeError, ValueError):
            continue
        name = str(item.get("horse_name") or item.get("display_name") or item.get("name") or "").strip()
        if not name:
            continue
        aliases_raw = item.get("aliases") or []
        aliases = tuple(str(a).strip() for a in aliases_raw if str(a).strip())
        by = item.get("birth_year")
        try:
            birth_year = int(by) if by is not None else None
        except (TypeError, ValueError):
            birth_year = None
        out.append(
            HorseNameRecord(
                horse_id=hid,
                horse_name=name,
                breed=(None if item.get("breed") is None else str(item.get("breed"))),
                sex=(None if item.get("sex") is None else str(item.get("sex"))),
                birth_year=birth_year,
                aliases=aliases,
            )
        )
    return out


def load_records_from_pedigree_entities(path: Path) -> list[HorseNameRecord]:
    """Use pedigree entity ``linked_horse_id`` + ``canonical_name`` when available."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    entities = raw.get("entities") if isinstance(raw, dict) else None
    if not isinstance(entities, list):
        return []
    out: list[HorseNameRecord] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        linked = ent.get("linked_horse_id")
        if linked is None:
            continue
        try:
            hid = int(linked)
        except (TypeError, ValueError):
            continue
        name = str(ent.get("canonical_name") or "").strip()
        if not name:
            continue
        raw_names = ent.get("raw_names") or []
        aliases = tuple(str(a).strip() for a in raw_names if str(a).strip() and str(a).strip() != name)
        by = ent.get("birth_year")
        try:
            birth_year = int(by) if by is not None else None
        except (TypeError, ValueError):
            birth_year = None
        out.append(
            HorseNameRecord(
                horse_id=hid,
                horse_name=name,
                breed=(None if ent.get("breed") is None else str(ent.get("breed"))),
                sex=(None if ent.get("sex") is None else str(ent.get("sex"))),
                birth_year=birth_year,
                aliases=aliases,
            )
        )
    return out


def build_default_horse_directory(
    *,
    index_path: Path | None = None,
    pedigree_entities_path: Path | None = None,
) -> HorseNameDirectory:
    directory = HorseNameDirectory()
    pedigree_path = pedigree_entities_path or Path("data/pedigree/pedigree_entities.json")
    for rec in load_records_from_pedigree_entities(pedigree_path):
        directory.add(rec)
    if index_path is None:
        index_path = Path("data/identity/horse_name_index.json")
    for rec in load_records_from_mapping_file(index_path):
        directory.add(rec)
    return directory
