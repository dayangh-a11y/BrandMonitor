"""Tests for durable canonical birth_year corrections."""

from __future__ import annotations

import json
from pathlib import Path

from src.identity.corrections import load_birth_year_corrections


def test_birth_year_corrections_registry_has_1771():
    rows = load_birth_year_corrections(Path("data/identity/birth_year_corrections.json"))
    assert rows
    hit = next(r for r in rows if r.get("horse_id") == 1771)
    assert hit["old_value"] == 2023
    assert hit["new_value"] == 2016
    assert hit["source"] == "inferred_from_race_age_sequence"
    assert hit["confidence"] in {"MEDIUM", "HIGH"}
    assert hit["preserve_raw"] is True
    evidence = hit["evidence"]
    assert evidence["mode_implied_birth_year"] == 2016
    assert len(evidence["race_dates"]) == 8
    assert len(evidence["payload_age_sequence"]) == 8


def test_registry_is_valid_json_list():
    raw = Path("data/identity/birth_year_corrections.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, list)
