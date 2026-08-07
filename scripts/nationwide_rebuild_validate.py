"""Post-collection: rebuild warehouse, identity, analytics; run validations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = Path("/workspace/output/historical/horse_racing.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH}")
os.environ.setdefault("CRAWL_ALLOWED_RACECOURSES", "*")

from src.analytics import build_analytics
from src.database import init_db, reset_engine, session_scope
from src.identity import build_horse_identity, duplicate_merge_report
from src.quality import run_quality_checks
from src.utils.settings import get_settings
from src.warehouse import build_warehouse, run_entity_resolution

ARTIFACTS = Path("/opt/cursor/artifacts")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def main() -> None:
    reset_engine()
    settings = get_settings()
    init_db(settings)

    with session_scope(settings) as session:
        wh = build_warehouse(session)
        er = run_entity_resolution(session)
        qc = run_quality_checks(session)
        print({"warehouse": wh, "entity_resolution": er, "quality": qc}, flush=True)

    with session_scope(settings) as session:
        ident = build_horse_identity(session)
        report = duplicate_merge_report(session)
        print({"identity": ident, "merge_summary": report["summary"]}, flush=True)
        (ARTIFACTS / "nationwide_identity_build.json").write_text(
            json.dumps(
                {"identity": ident, "merge_summary": report["summary"]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    with session_scope(settings) as session:
        anl = build_analytics(session)
        print({"analytics": anl}, flush=True)

    # Coverage + 100-horse audit
    subprocess.check_call(
        [sys.executable, str(ROOT / "scripts" / "nationwide_coverage_report.py")],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )

    # Identity + virtual race tests
    for test_mod in ("tests/test_identity.py", "tests/test_virtual_race.py", "tests/test_racecourses.py"):
        print(f"Running {test_mod} ...", flush=True)
        subprocess.check_call(
            [sys.executable, "-m", "pytest", test_mod, "-q"],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )


if __name__ == "__main__":
    main()
