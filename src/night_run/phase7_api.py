"""Phase 7 — API readiness contract (no HTTP server / no Telegram UI)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.night_run.paths import NIGHT_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


API_CONTRACT = {
    "api_version": "v1",
    "base_path": "/api/v1",
    "auth": "TBD (not implemented in Night Run)",
    "implementation_status": "CONTRACT_ONLY",
    "engine_binding": {
        "GET /race/{race_id}": "warehouse race conditions + field list by ids",
        "GET /race/{race_id}/ranking": "prediction_engine.service.rank_race",
        "GET /horse/{horse_id}": "id_horses + links",
        "GET /horse/{horse_id}/form": "get_horse_analysis.form",
        "GET /horse/{horse_id}/pedigree": "get_horse_analysis.pedigree",
        "GET /horse/{horse_id}/track-record": "get_horse_analysis.track_record",
        "GET /horse/{horse_id}/distance-record": "get_horse_analysis.distance_record",
        "GET /horse/{horse_id}/analysis": "prediction_engine.service.get_horse_analysis",
    },
    "endpoints": [
        {
            "method": "GET",
            "path": "/race/{race_id}",
            "path_params": {"race_id": "integer wh_races.id"},
            "response": {
                "race_id": "int",
                "as_of_date": "date",
                "race_conditions": "object",
                "horse_ids": "int[]",
                "provenance": "object",
                "timestamp_utc": "string",
            },
        },
        {
            "method": "GET",
            "path": "/race/{race_id}/ranking",
            "maps_to": "rank_race(race_id)",
            "response_ref": "prediction_engine_contract.json",
        },
        {
            "method": "GET",
            "path": "/horse/{horse_id}",
            "path_params": {"horse_id": "integer id_horses.horse_id"},
        },
        {"method": "GET", "path": "/horse/{horse_id}/form"},
        {"method": "GET", "path": "/horse/{horse_id}/pedigree"},
        {"method": "GET", "path": "/horse/{horse_id}/track-record"},
        {"method": "GET", "path": "/horse/{horse_id}/distance-record"},
        {"method": "GET", "path": "/horse/{horse_id}/analysis"},
    ],
    "rules": [
        "Telegram must call these endpoints / engine functions — no analytics only in bot code",
        "Identifiers are horse_id / race_id, never names as primary keys",
        "All responses JSON-serializable with provenance + data_quality + timestamp",
        "No betting endpoints in v1",
    ],
}


def run_phase7() -> dict[str, Any]:
    out = NIGHT_DIR / "phase7_api_readiness"
    out.mkdir(parents=True, exist_ok=True)
    doc = {
        "generated_at_utc": _utc_now(),
        "status": "CONTRACT_READY_IMPLEMENTATION_PENDING",
        "http_server_implemented": False,
        "contract": API_CONTRACT,
    }
    (out / "api_contract.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "API_READINESS.md").write_text(
        "\n".join(
            [
                "# Phase 7 — API Readiness",
                "",
                "- HTTP server: **not implemented** (contract only)",
                "- Engine functions: **available** (`src/prediction_engine`)",
                "- Telegram: must remain a thin client of this API/engine",
                "",
                "## Required operations",
                "",
                "- `GET /race/{race_id}`",
                "- `GET /race/{race_id}/ranking`",
                "- `GET /horse/{horse_id}`",
                "- `GET /horse/{horse_id}/form`",
                "- `GET /horse/{horse_id}/pedigree`",
                "- `GET /horse/{horse_id}/track-record`",
                "- `GET /horse/{horse_id}/distance-record`",
                "- `GET /horse/{horse_id}/analysis`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "status": "COMPLETE",
        "phase": 7,
        "http_implemented": False,
        "contract_ready": True,
        "output_dir": str(out),
    }
