#!/usr/bin/env python3
"""Master Night Run orchestrator — foundation phases, no Telegram UI, no ML training."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.night_run.phase1_pedigree import run_phase1
from src.night_run.phase2_quality import run_phase2
from src.night_run.phase3_dataset import run_phase3
from src.night_run.phase4_baselines import run_phase4
from src.night_run.phase5_ml_gate import run_phase5
from src.night_run.phase6_engine import run_phase6
from src.night_run.phase7_api import run_phase7
from src.night_run.phase8_telegram import run_phase8
from src.night_run.phase9_final import run_phase9
from src.night_run.paths import NIGHT_DIR


def main() -> int:
    results: dict = {}
    print("=== PHASE 1 Pedigree ===", flush=True)
    results["phase_1"] = run_phase1()
    print(json.dumps(results["phase_1"], ensure_ascii=False)[:500], flush=True)

    print("=== PHASE 2 Data quality ===", flush=True)
    results["phase_2"] = run_phase2()
    print(json.dumps(results["phase_2"], ensure_ascii=False)[:500], flush=True)

    print("=== PHASE 3 Dataset validation ===", flush=True)
    results["phase_3"] = run_phase3()
    print(json.dumps(results["phase_3"], ensure_ascii=False)[:500], flush=True)

    print("=== PHASE 4 Baselines ===", flush=True)
    results["phase_4"] = run_phase4()
    print(json.dumps(results["phase_4"], ensure_ascii=False)[:500], flush=True)

    print("=== PHASE 5 ML gate ===", flush=True)
    results["phase_5"] = run_phase5(results.get("phase_4"))
    print(json.dumps(results["phase_5"], ensure_ascii=False)[:500], flush=True)

    print("=== PHASE 6 Prediction engine ===", flush=True)
    results["phase_6"] = run_phase6()
    print(json.dumps(results["phase_6"], ensure_ascii=False)[:500], flush=True)

    print("=== PHASE 7 API readiness ===", flush=True)
    results["phase_7"] = run_phase7()
    print(json.dumps(results["phase_7"], ensure_ascii=False)[:500], flush=True)

    print("=== PHASE 8 Telegram design ===", flush=True)
    results["phase_8"] = run_phase8()
    print(json.dumps(results["phase_8"], ensure_ascii=False)[:500], flush=True)

    print("=== PHASE 9 Final report ===", flush=True)
    status = run_phase9(results)
    (NIGHT_DIR / "night_run_phases.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "READY_FOR_TELEGRAM": status["READY_FOR_TELEGRAM"],
        "READY_FOR_ML": status["READY_FOR_ML"],
        "PEDIGREE_READY": status["PEDIGREE_READY"],
        "BASELINE_VALIDATED": status["BASELINE_VALIDATED"],
        "FINAL_SYSTEM_STATUS": status["FINAL_SYSTEM_STATUS"],
        "out": str(NIGHT_DIR),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
