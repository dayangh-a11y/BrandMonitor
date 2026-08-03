#!/usr/bin/env python3
"""Build Postal Intelligence Platform database and export sample artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from postal.build import build_postal_intelligence
from postal.dashboard import export_all_dashboards
from postal.db import PostalIntelligenceDB
from postal.export import export_sample_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build BrandMonitor Postal Intelligence Platform")
    parser.add_argument("--db", default="data/postal_intelligence.db")
    parser.add_argument("--out", default="output/postal_intelligence")
    args = parser.parse_args()

    summary = build_postal_intelligence(db_path=args.db)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    pi = PostalIntelligenceDB(args.db)
    pi.connect()
    export_sample_outputs(pi, out_dir)
    export_all_dashboards(pi, out_dir / "dashboards")
    pi.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote artifacts to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
