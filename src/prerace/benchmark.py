"""Immutable Pre-Race Benchmark snapshots.

A benchmark freezes a ranking at a point in time. It must not be silently
rewritten. Post-race evaluation is a separate artifact.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_BENCHMARK_DIR = Path("data/prerace/benchmarks")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Stable bytes for hashing (excludes mutable wrapper fields if needed)."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256_hex(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def freeze_payload_hash_body(benchmark: dict[str, Any]) -> dict[str, Any]:
    """Fields that define immutability (exclude verification envelope)."""
    return {
        "benchmark_id": benchmark["benchmark_id"],
        "immutable": True,
        "frozen_at_utc": benchmark["frozen_at_utc"],
        "data_cutoff_utc": benchmark["data_cutoff_utc"],
        "label": benchmark["label"],
        "race": benchmark["race"],
        "leans": benchmark["leans"],
        "horses": benchmark["horses"],
        "relative_score_share": benchmark["relative_score_share"],
        "scoring_notes": benchmark["scoring_notes"],
        "source_ranking_artifact": benchmark.get("source_ranking_artifact"),
        "no_prediction_probability": True,
    }


def compute_content_sha256(benchmark: dict[str, Any]) -> str:
    return sha256_hex(freeze_payload_hash_body(benchmark))


def build_mashhad_week2_1000m_benchmark(
    *,
    frozen_at_utc: str | None = None,
    source_ranking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Freeze the already-published Mashhad week-2 1000m ranking.

    Does NOT recalculate scores. Copies the frozen ranking values as-is.
    """
    ts = frozen_at_utc or utc_now_iso()

    # Exact values from the frozen pre-race ranking (do not recompute).
    horses = [
        {
            "horse_id": 6348,
            "horse": "ژیوان",
            "final_score": 85.6,
            "rank": 1,
            "confidence": "HIGH",
            "historical_score": 88.0,
            "recent_form_score": 88.0,
            "track_score": 88.0,
            "distance_score": 88.0,
            "rating_score": 40.0,
        },
        {
            "horse_id": 6323,
            "horse": "آرکان شورچه",
            "final_score": 75.64,
            "rank": 2,
            "confidence": "HIGH",
            "historical_score": 71.77,
            "recent_form_score": 81.99,
            "track_score": 88.0,
            "distance_score": 71.77,
            "rating_score": 40.0,
        },
        {
            "horse_id": 7177,
            "horse": "نوردخت آراد",
            "final_score": 71.62,
            "rank": 3,
            "confidence": "MEDIUM",
            "historical_score": 72.1,
            "recent_form_score": 72.56,
            "track_score": None,
            "distance_score": 67.86,
            "rating_score": 76.67,
        },
        {
            "horse_id": 4090,
            "horse": "بای بای صوفیان",
            "final_score": 68.7,
            "rank": 4,
            "confidence": "HIGH",
            "historical_score": 58.47,
            "recent_form_score": 64.81,
            "track_score": 88.0,
            "distance_score": 88.0,
            "rating_score": 26.67,
        },
        {
            "horse_id": 6330,
            "horse": "فرتینا",
            "final_score": 63.42,
            "rank": 5,
            "confidence": "HIGH",
            "historical_score": 63.98,
            "recent_form_score": 63.65,
            "track_score": 64.0,
            "distance_score": 75.45,
            "rating_score": 13.33,
        },
        {
            "horse_id": 6917,
            "horse": "ویتو صوفیان",
            "final_score": 61.2,
            "rank": 6,
            "confidence": "MEDIUM",
            "historical_score": 58.02,
            "recent_form_score": 50.45,
            "track_score": None,
            "distance_score": 83.18,
            "rating_score": 63.33,
        },
        {
            "horse_id": 6690,
            "horse": "یاد رخشان",
            "final_score": 59.86,
            "rank": 7,
            "confidence": "HIGH",
            "historical_score": 57.6,
            "recent_form_score": 57.1,
            "track_score": None,
            "distance_score": 71.94,
            "rating_score": 46.67,
        },
        {
            "horse_id": 6995,
            "horse": "الین ناز",
            "final_score": 48.93,
            "rank": 8,
            "confidence": "MEDIUM",
            "historical_score": 49.03,
            "recent_form_score": 48.75,
            "track_score": None,
            "distance_score": 49.03,
            "rating_score": None,
        },
        {
            "horse_id": 6733,
            "horse": "پهلوان مهرانی",
            "final_score": 48.15,
            "rank": 9,
            "confidence": "MEDIUM",
            "historical_score": 49.84,
            "recent_form_score": 53.62,
            "track_score": None,
            "distance_score": 41.6,
            "rating_score": 30.0,
        },
    ]

    # Relative Score Share (NOT a probability). Copied from ranking artifact shares.
    relative_score_share = [
        {"horse_id": 6348, "horse": "ژیوان", "relative_score_share_pct": 40.2},
        {"horse_id": 6323, "horse": "آرکان شورچه", "relative_score_share_pct": 17.5},
        {"horse_id": 7177, "horse": "نوردخت آراد", "relative_score_share_pct": 12.5},
        {"horse_id": 4090, "horse": "بای بای صوفیان", "relative_score_share_pct": 9.8},
        {"horse_id": 6330, "horse": "فرتینا", "relative_score_share_pct": 6.3},
        {"horse_id": 6917, "horse": "ویتو صوفیان", "relative_score_share_pct": 5.3},
        {"horse_id": 6690, "horse": "یاد رخشان", "relative_score_share_pct": 4.7},
        {"horse_id": 6995, "horse": "الین ناز", "relative_score_share_pct": 1.9},
        {"horse_id": 6733, "horse": "پهلوان مهرانی", "relative_score_share_pct": 1.8},
    ]

    if source_ranking is not None:
        # Optional integrity check against source artifact values (no rewrite).
        by_id = {h["horse_id"]: h for h in horses}
        for row in source_ranking.get("ranking", []):
            hid = row["horse_id"]
            if hid not in by_id:
                raise ValueError(f"Source ranking horse_id={hid} missing from freeze template")
            if float(row["Final_Score"]) != float(by_id[hid]["final_score"]):
                raise ValueError(
                    f"Freeze refuses to alter ranking: horse_id={hid} "
                    f"source={row['Final_Score']} frozen={by_id[hid]['final_score']}"
                )

    benchmark: dict[str, Any] = {
        "benchmark_id": "mashhad-week2-turkmen-1000m-2026-08-08",
        "immutable": True,
        "schema_version": "1.0.0",
        "label": "PRE-RACE BENCHMARK — Mashhad Week 2 Turkmen +3 1000m Open Field",
        "frozen_at_utc": ts,
        "data_cutoff_utc": ts,
        "data_cutoff_policy": (
            "No race result, card update, or warehouse row with published/updated time "
            "after data_cutoff_utc may be used to alter this benchmark. "
            "This snapshot freezes scores already computed; it does not re-query live DB."
        ),
        "race": {
            "track": "مشهد",
            "distance_m": 1000,
            "breed": "ترکمن",
            "age_condition": "+3",
            "field_type": "open",
            "meeting": "هفته ۲ / پیش‌ثبت‌نام",
            "field_size": 9,
            "status": "upcoming_at_freeze",
        },
        "leans": {
            "WIN_LEAN": {"horse_id": 6348, "horse": "ژیوان"},
            "EXACTA_LEAN": {
                "first": {"horse_id": 6348, "horse": "ژیوان"},
                "second": {"horse_id": 6323, "horse": "آرکان شورچه"},
            },
            "TOP_3": [
                {"horse_id": 6348, "horse": "ژیوان", "rank": 1},
                {"horse_id": 6323, "horse": "آرکان شورچه", "rank": 2},
                {"horse_id": 7177, "horse": "نوردخت آراد", "rank": 3},
            ],
        },
        "horses": horses,
        "relative_score_share": relative_score_share,
        "relative_score_share_note": (
            "Relative Score Share is a normalization of Final_Score across the field. "
            "It is NOT a win probability and must not be used as Probability in evaluation "
            "(Brier/Calibration require real probabilities)."
        ),
        "scoring_notes": {
            "method": "PRE-RACE HISTORICAL + CONTEXTUAL RANKING",
            "not_a_prediction": True,
            "prediction_probability_produced": False,
            "ranking_altered_at_freeze": False,
        },
        "source_ranking_artifact": (
            "/opt/cursor/artifacts/mashhad_week_ahead_1000m_ranking.json"
            if source_ranking is not None
            else None
        ),
        "no_prediction_probability": True,
    }
    content_sha = compute_content_sha256(benchmark)
    benchmark["content_sha256"] = content_sha
    benchmark["immutability"] = {
        "write_once": True,
        "content_sha256": content_sha,
        "verify_instruction": (
            "Recompute sha256 over freeze_payload_hash_body(benchmark); "
            "must equal content_sha256. Do not overwrite file."
        ),
    }
    return benchmark


def write_benchmark(
    benchmark: dict[str, Any],
    path: Path,
    *,
    force: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("content_sha256") != benchmark.get("content_sha256"):
            raise FileExistsError(
                f"Immutable benchmark exists at {path}. Refusing overwrite "
                f"(existing sha={existing.get('content_sha256')}, "
                f"new sha={benchmark.get('content_sha256')}). Pass force=True only for recovery."
            )
        # identical content — leave as-is
        return path
    # Write once
    path.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # sidecar lock marker
    lock = path.with_suffix(path.suffix + ".immutable")
    lock.write_text(
        json.dumps(
            {
                "path": str(path),
                "content_sha256": benchmark["content_sha256"],
                "frozen_at_utc": benchmark["frozen_at_utc"],
                "immutable": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def load_benchmark(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = data.get("content_sha256")
    actual = compute_content_sha256(data)
    if expected != actual:
        raise ValueError(
            f"Benchmark integrity failure: stored sha={expected} recomputed={actual}"
        )
    return data


def verify_benchmark_file(path: Path) -> dict[str, Any]:
    data = load_benchmark(path)
    return {
        "path": str(path),
        "ok": True,
        "benchmark_id": data["benchmark_id"],
        "frozen_at_utc": data["frozen_at_utc"],
        "content_sha256": data["content_sha256"],
        "immutable": data.get("immutable", False),
    }
