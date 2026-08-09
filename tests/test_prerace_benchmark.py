"""Tests for immutable Pre-Race Benchmark freeze + evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.prerace.benchmark import (
    build_mashhad_week2_1000m_benchmark,
    compute_content_sha256,
    load_benchmark,
    write_benchmark,
)
from src.prerace.evaluation import evaluate_benchmark


def test_freeze_is_immutable_write_once(tmp_path: Path):
    b = build_mashhad_week2_1000m_benchmark(frozen_at_utc="2026-08-08T17:20:00+00:00")
    path = tmp_path / "bench.json"
    write_benchmark(b, path)
    # second write identical OK
    write_benchmark(b, path)
    # altered content refused
    b2 = dict(b)
    b2["horses"] = list(b["horses"])
    b2["horses"] = [{**b["horses"][0], "final_score": 99.0}, *b["horses"][1:]]
    b2["content_sha256"] = compute_content_sha256(b2)
    with pytest.raises(FileExistsError):
        write_benchmark(b2, path)


def test_benchmark_sha_verifies():
    b = build_mashhad_week2_1000m_benchmark(frozen_at_utc="2026-08-08T17:20:00+00:00")
    assert b["content_sha256"] == compute_content_sha256(b)
    assert b["no_prediction_probability"] is True
    assert "probability" not in json.dumps(b["horses"]).lower()
    assert all(
        set(h.keys())
        >= {
            "horse_id",
            "horse",
            "final_score",
            "rank",
            "confidence",
            "historical_score",
            "recent_form_score",
            "track_score",
            "distance_score",
            "rating_score",
        }
        for h in b["horses"]
    )
    assert b["leans"]["WIN_LEAN"]["horse_id"] == 6348
    assert b["leans"]["EXACTA_LEAN"]["second"]["horse_id"] == 6323
    assert [x["horse_id"] for x in b["leans"]["TOP_3"]] == [6348, 6323, 7177]
    assert b["relative_score_share"][0]["relative_score_share_pct"] == 40.2


def test_evaluation_hits_and_skips_brier():
    b = build_mashhad_week2_1000m_benchmark(frozen_at_utc="2026-08-08T17:20:00+00:00")
    # Perfect outcome matching leans
    actual = [
        {"horse_id": 6348, "finish_position": 1},
        {"horse_id": 6323, "finish_position": 2},
        {"horse_id": 7177, "finish_position": 3},
        {"horse_id": 4090, "finish_position": 4},
        {"horse_id": 6330, "finish_position": 5},
        {"horse_id": 6917, "finish_position": 6},
        {"horse_id": 6690, "finish_position": 7},
        {"horse_id": 6995, "finish_position": 8},
        {"horse_id": 6733, "finish_position": 9},
    ]
    ev = evaluate_benchmark(b, actual_finish_order=actual)
    assert ev["metrics"]["Winner_Hit"] is True
    assert ev["metrics"]["Top_2_Hit"] is True
    assert ev["metrics"]["Top_3_Hit"] is True
    assert ev["metrics"]["Exacta_Hit"] is True
    assert ev["metrics"]["Rank_Correlation_Spearman"] == 1.0
    assert ev["metrics"]["Brier_Score"] is None
    assert ev["metrics"]["Calibration"] is None
    assert ev["has_real_probabilities"] is False
    assert ev["probability_metrics_status"]["Relative_Score_Share_used_as_probability"] is False


def test_load_detects_tamper(tmp_path: Path):
    b = build_mashhad_week2_1000m_benchmark(frozen_at_utc="2026-08-08T17:20:00+00:00")
    path = tmp_path / "bench.json"
    write_benchmark(b, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["horses"][0]["final_score"] = 1.0
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_benchmark(path)
