#!/usr/bin/env python3
"""Harvest official company information from official websites only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.official.website_harvester import harvest_all


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/official_harvest")
    args = parser.parse_args()
    summary = harvest_all(args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
