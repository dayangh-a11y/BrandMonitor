#!/usr/bin/env python3
"""Apply canonical birth_year correction for horse_id 1771 (read-safe for raw).

Does NOT:
- delete race results
- split horse_id 1771
- overwrite raw_horses / wh_horses birthdate

Does:
- set id_horses.birth_year = 2016
- store provenance in meta_json.birth_year_correction
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.database.session import session_scope
from src.identity.corrections import apply_birth_year_corrections


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with session_scope() as session:
        applied = apply_birth_year_corrections(session, dry_run=args.dry_run)
        print(json.dumps({"dry_run": args.dry_run, "applied": applied}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
