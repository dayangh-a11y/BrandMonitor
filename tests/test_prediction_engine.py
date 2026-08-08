"""Smoke tests for prediction engine contract."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.prediction_engine.service import get_horse_analysis, rank_race

DB = Path("output/historical/horse_racing.db")


@pytest.mark.skipif(not DB.exists(), reason="historical DB missing")
def test_rank_race_contract_keys():
    conn = sqlite3.connect(str(DB))
    row = conn.execute(
        "SELECT race_id FROM wh_race_results GROUP BY race_id HAVING COUNT(*)>=5 ORDER BY race_id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row
    out = rank_race(int(row[0]), db_path=DB)
    for k in (
        "race_id",
        "as_of_date",
        "race_conditions",
        "horses",
        "top_pick",
        "top_3",
        "alternate",
        "warnings",
        "methodology_version",
    ):
        assert k in out
    assert out.get("score_is_probability") is False
    if out["horses"]:
        h = out["horses"][0]
        assert "horse_id" in h and "score" in h and "confidence" in h and "evidence" in h


@pytest.mark.skipif(not DB.exists(), reason="historical DB missing")
def test_horse_analysis_uses_horse_id():
    conn = sqlite3.connect(str(DB))
    row = conn.execute(
        "SELECT horse_id FROM id_horses WHERE status='active' OR status IS NULL LIMIT 1"
    ).fetchone()
    conn.close()
    out = get_horse_analysis(int(row[0]), db_path=DB)
    assert out["horse_id"] == int(row[0])
    assert "form" in out and "pedigree" in out
