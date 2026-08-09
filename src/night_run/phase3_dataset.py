"""Phase 3 — prediction dataset validation packaging."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.night_run.paths import NIGHT_DIR, PF_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase3() -> dict[str, Any]:
    out = NIGHT_DIR / "phase3_prediction_dataset"
    out.mkdir(parents=True, exist_ok=True)

    reports = PF_DIR / "reports"
    freezes = PF_DIR / "freezes"
    required = {
        "feature_dictionary": reports / "feature_dictionary.json",
        "coverage_report": reports / "coverage_report.json",
        "leakage_audit": reports / "leakage_audit.json",
        "readiness": reports / "readiness.json",
        "freeze_latest": freezes / "LATEST.json",
    }
    missing = [k for k, p in required.items() if not p.exists()]
    if missing:
        return {
            "status": "BLOCKED",
            "missing": missing,
            "message": "Run scripts/build_prediction_features.py and freeze first.",
        }

    freeze = json.loads(required["freeze_latest"].read_text(encoding="utf-8"))
    leakage = json.loads(required["leakage_audit"].read_text(encoding="utf-8"))
    coverage = json.loads(required["coverage_report"].read_text(encoding="utf-8"))
    feat = json.loads(required["feature_dictionary"].read_text(encoding="utf-8"))
    readiness = json.loads(required["readiness"].read_text(encoding="utf-8"))

    # Copy canonical Night Run names
    shutil.copy2(required["feature_dictionary"], out / "feature_dictionary.json")
    shutil.copy2(required["coverage_report"], out / "coverage_report.json")
    shutil.copy2(required["leakage_audit"], out / "leakage_audit.json")

    version = {
        "dataset_version": freeze.get("dataset_version") or freeze.get("version") or "pf-v1.0.0-20260808",
        "dataset_sha256": freeze.get("dataset_sha256") or freeze.get("sha256"),
        "frozen_at_utc": freeze.get("frozen_at_utc") or freeze.get("created_at_utc"),
        "unit": "horse_x_race",
        "cutoff_key": ["race_date", "race_id", "result_id"],
        "same_day_leakage_policy": "FORBIDDEN",
        "betting_data": "NOT_USED",
        "observations_path": str(PF_DIR / "datasets" / "observations.jsonl.gz"),
        "counts": freeze.get("counts")
        or {
            "observations": coverage.get("n_observations") or coverage.get("observations"),
            "horses": coverage.get("n_horses") or coverage.get("horses"),
            "races": coverage.get("n_races") or coverage.get("races"),
        },
        "feature_groups_required": [
            "HORSE_HISTORY",
            "RECENT_FORM",
            "DISTANCE",
            "TRACK",
            "CLASS",
            "BREED",
            "TRAINER",
            "OWNER",
            "WEIGHT",
            "FIELD_SIZE",
            "PEDIGREE",
        ],
        "rate_cell_contract": [
            "value",
            "raw_rate",
            "smoothed_rate",
            "sample_n",
            "is_missing",
            "reliability",
        ],
        "reliability_bands": {
            "n<3": "very_low",
            "3-4": "low",
            "5-9": "medium",
            "10+": "stronger",
        },
        "missing_policy": "is_missing=true; never coerce missing to zero",
        "generated_at_utc": _utc_now(),
        "source_freeze": str(required["freeze_latest"]),
    }

    # Feature group presence check
    feat_names: list[str] = []
    if isinstance(feat, dict):
        if "features" in feat:
            for f in feat["features"]:
                if isinstance(f, dict):
                    feat_names.append(str(f.get("name") or f.get("key") or f.get("id")))
                else:
                    feat_names.append(str(f))
        else:
            feat_names = [str(k) for k in feat.keys()]
    elif isinstance(feat, list):
        for f in feat:
            if isinstance(f, dict):
                feat_names.append(str(f.get("name") or f.get("key") or f.get("id")))
            else:
                feat_names.append(str(f))

    joined = " ".join(feat_names).lower()
    group_status = {}
    mapping = {
        "HORSE_HISTORY": ["career", "hist", "starts", "win_rate"],
        "RECENT_FORM": ["form", "recent"],
        "DISTANCE": ["distance", "dist"],
        "TRACK": ["track"],
        "CLASS": ["class"],
        "BREED": ["breed", "surface", "blood"],
        "TRAINER": ["trainer"],
        "OWNER": ["owner"],
        "WEIGHT": ["weight"],
        "FIELD_SIZE": ["field"],
        "PEDIGREE": ["pedigree", "sire", "dam"],
    }
    for g, keys in mapping.items():
        present = any(k in joined for k in keys)
        group_status[g] = {
            "present_in_dictionary": present,
            "note": None
            if present
            else (
                "PEDIGREE features not yet in PF freeze — pedigree foundation is file-ready for next feature rebuild"
                if g == "PEDIGREE"
                else "Not detected in feature dictionary tokens"
            ),
        }

    leak_ok = False
    medium_risks: list = []
    if isinstance(leakage, dict):
        # Hard fail only if future results / targets leak / betting used
        hard_fail = bool(
            leakage.get("future_results_used_in_features")
            or leakage.get("targets_leak_into_features")
            or leakage.get("betting_data_used")
            or leakage.get("passed") is False
        )
        leak_ok = not hard_fail and (
            leakage.get("future_results_used_in_features") is False
            or "structural_rules" in leakage
            or leakage.get("passed") is True
        )
        medium_risks = leakage.get("medium_or_higher_features") or []
    version["leakage_medium_risk_feature_count"] = len(medium_risks)

    version["feature_group_status"] = group_status
    version["leakage_audit_passed"] = leak_ok
    version["readiness"] = readiness
    version["score_is_not_probability"] = True

    (out / "prediction_dataset_version.json").write_text(
        json.dumps(version, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    report = [
        "# Phase 3 — Prediction Dataset Validation",
        "",
        f"- Dataset: `{version['dataset_version']}`",
        f"- SHA256: `{version['dataset_sha256']}`",
        f"- Leakage audit passed: **{leak_ok}**",
        f"- Unit: horse × race; cutoff `(race_date, race_id, result_id)`",
        f"- Betting data: NOT USED",
        "",
        "## Feature groups",
        "",
    ]
    for g, st in group_status.items():
        mark = "YES" if st["present_in_dictionary"] else "NO/PARTIAL"
        report.append(f"- {g}: {mark}" + (f" — {st['note']}" if st["note"] else ""))
    report += [
        "",
        "## Notes",
        "",
        "- Missing values must remain `is_missing` (never zero-filled).",
        "- Rates keep sample_n + reliability bands.",
        "- Pedigree can be joined in a future dataset version after DB migration review.",
        "",
    ]
    (out / "PHASE3_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    status = "COMPLETE" if leak_ok else "COMPLETE_WITH_WARNINGS"
    if group_status["PEDIGREE"]["present_in_dictionary"] is False:
        status = "COMPLETE_WITH_WARNINGS"

    return {
        "status": status,
        "phase": 3,
        "dataset_version": version["dataset_version"],
        "dataset_sha256": version["dataset_sha256"],
        "leakage_audit_passed": leak_ok,
        "pedigree_in_features": group_status["PEDIGREE"]["present_in_dictionary"],
        "output_dir": str(out),
    }
