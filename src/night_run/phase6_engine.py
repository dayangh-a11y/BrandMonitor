"""Phase 6 — Prediction Engine contract + smoke validation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.night_run.paths import DB_PATH, NIGHT_DIR
from src.prediction_engine.contract import CONTRACT_VERSION, RANK_RACE_OUTPUT_SCHEMA
from src.prediction_engine.service import get_horse_analysis, rank_race


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase6() -> dict[str, Any]:
    out = NIGHT_DIR / "phase6_prediction_engine"
    out.mkdir(parents=True, exist_ok=True)

    contract = {
        "methodology_version": CONTRACT_VERSION,
        "generated_at_utc": _utc_now(),
        "input": {"race_id": "integer (wh_races.id)"},
        "output_schema": RANK_RACE_OUTPUT_SCHEMA,
        "operations": {
            "rank_race": "src.prediction_engine.service.rank_race",
            "get_horse_analysis": "src.prediction_engine.service.get_horse_analysis",
        },
        "rules": [
            "score is NOT a probability unless calibrated=true (currently false)",
            "stable horse_id / race_id identifiers",
            "every horse row has confidence, data_quality, evidence, feature_summary",
            "no Telegram imports or UI coupling",
            "no betting data",
            "features use only information before race cutoff",
        ],
    }
    (out / "prediction_engine_contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Smoke: pick a race with a known field
    sample = None
    warnings = []
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            """
            SELECT race_id, COUNT(*) AS n FROM wh_race_results
            GROUP BY race_id HAVING n BETWEEN 6 AND 12
            ORDER BY race_id DESC LIMIT 1
            """
        ).fetchone()
        conn.close()
        if row:
            rid = int(row[0])
            sample = rank_race(rid, db_path=DB_PATH)
            (out / "sample_rank_race.json").write_text(
                json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            if sample.get("top_pick") and sample["top_pick"].get("horse_id"):
                ha = get_horse_analysis(int(sample["top_pick"]["horse_id"]), db_path=DB_PATH)
                (out / "sample_horse_analysis.json").write_text(
                    json.dumps(ha, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
        else:
            warnings.append("No suitable sample race found")
    else:
        warnings.append("DB missing")

    required_keys = set(RANK_RACE_OUTPUT_SCHEMA["required"])
    ok = bool(sample) and required_keys.issubset(set(sample.keys()))
    status = {
        "status": "COMPLETE" if ok else "COMPLETE_WITH_WARNINGS",
        "phase": 6,
        "contract_version": CONTRACT_VERSION,
        "smoke_ok": ok,
        "sample_race_id": sample.get("race_id") if sample else None,
        "warnings": warnings,
        "output_dir": str(out),
        "generated_at_utc": _utc_now(),
    }
    (out / "phase6_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "PHASE6_REPORT.md").write_text(
        "\n".join(
            [
                "# Phase 6 — Prediction Engine Contract",
                "",
                f"- Version: `{CONTRACT_VERSION}`",
                f"- Smoke OK: **{ok}**",
                f"- Sample race_id: `{status['sample_race_id']}`",
                "",
                "Interface is API-ready and Telegram-agnostic.",
                "Scores are ranks/scores, not calibrated probabilities.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return status
