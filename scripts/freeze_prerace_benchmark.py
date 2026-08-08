#!/usr/bin/env python3
"""Freeze Mashhad week-2 1000m ranking as an IMMUTABLE Pre-Race Benchmark.

Does not recalculate or alter ranking scores.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prerace.benchmark import (
    DEFAULT_BENCHMARK_DIR,
    build_mashhad_week2_1000m_benchmark,
    verify_benchmark_file,
    write_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_BENCHMARK_DIR / "mashhad_week2_turkmen_1000m_2026-08-08.json",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("/opt/cursor/artifacts/mashhad_week_ahead_1000m_ranking.json"),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--frozen-at-utc",
        default=None,
        help="Override freeze timestamp (ISO-8601). Default = now UTC.",
    )
    args = parser.parse_args()

    source = None
    if args.source.exists():
        source = json.loads(args.source.read_text(encoding="utf-8"))

    frozen_at = args.frozen_at_utc or datetime.now(timezone.utc).isoformat()
    benchmark = build_mashhad_week2_1000m_benchmark(
        frozen_at_utc=frozen_at,
        source_ranking=source,
    )
    path = write_benchmark(benchmark, args.out, force=args.force)

    # Mirror to artifacts (copy of immutable snapshot)
    art = Path("/opt/cursor/artifacts") / args.out.name
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    verify = verify_benchmark_file(path)
    print(
        json.dumps(
            {
                "status": "frozen",
                "path": str(path),
                "artifact_mirror": str(art),
                "verify": verify,
                "leans": benchmark["leans"],
                "horse_count": len(benchmark["horses"]),
                "no_prediction_probability": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
