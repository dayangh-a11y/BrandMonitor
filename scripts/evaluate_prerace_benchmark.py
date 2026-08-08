#!/usr/bin/env python3
"""Evaluate a frozen Pre-Race Benchmark after race results are known.

Does NOT modify the benchmark file.
Does NOT treat Relative Score Share as probability.

Example:
  python scripts/evaluate_prerace_benchmark.py \\
    --benchmark data/prerace/benchmarks/mashhad_week2_turkmen_1000m_2026-08-08.json \\
    --actual-json path/to/actual_finish.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prerace.evaluation import evaluate_benchmark_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument(
        "--actual-json",
        type=Path,
        required=True,
        help="JSON list of {horse_id, finish_position} or ordered [{horse_id}, ...] winner-first",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    actual = json.loads(args.actual_json.read_text(encoding="utf-8"))
    if isinstance(actual, dict) and "finish_order" in actual:
        race_ref = {k: v for k, v in actual.items() if k != "finish_order"}
        finish = actual["finish_order"]
    else:
        race_ref = None
        finish = actual

    out = args.out
    if out is None:
        out = Path("data/prerace/evaluations") / f"eval_{args.benchmark.stem}.json"

    evaluation = evaluate_benchmark_file(
        args.benchmark,
        finish,
        out_path=out,
        race_result_ref=race_ref,
    )
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
