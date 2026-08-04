#!/usr/bin/env python3
"""Build / refresh the dedicated Iran Post module export under docs/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from postal.iran_post.provider import IranPostModule


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Iran Post dedicated module bundle")
    parser.add_argument(
        "--db",
        default=None,
        help="Path to postal_intelligence.db (default: POSTAL_DB_PATH or data/...)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "docs" / "postal_intelligence" / "iran_post"),
        help="Output directory for JSON exports",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    module = IranPostModule(db_path=args.db)
    bundle = module.export_bundle()

    (out_dir / "catalog.json").write_text(
        json.dumps(bundle["catalog"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "snapshot.json").write_text(
        json.dumps(bundle["snapshot"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "national_ranking.json").write_text(
        json.dumps(bundle["national_ranking"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "fair_comparison.json").write_text(
        json.dumps(bundle["fair_comparison_default"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    national = bundle["national_ranking"]
    fair = bundle["fair_comparison_default"]
    print(f"Wrote Iran Post module exports → {out_dir}")
    print(f"  national companies: {len(national.get('rows') or [])}")
    print(f"  national warnings: {len(national.get('warnings') or [])}")
    print(f"  fair eligible: {fair.get('eligible')} common_cities={len(fair.get('common_cities') or [])}")
    print(f"  fair warnings: {len(fair.get('warnings') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
