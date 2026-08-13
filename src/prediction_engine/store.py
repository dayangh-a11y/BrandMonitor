"""In-memory index over a prediction-foundation observations JSONL.GZ file."""

from __future__ import annotations

import gzip
import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.prediction_foundation.baseline_eval import coverage_level
from src.prediction_foundation.freeze import assert_dataset_matches_freeze, load_freeze


def _default_warehouse_db() -> Path | None:
    raw = os.environ.get("WAREHOUSE_DB_PATH") or os.environ.get("DATABASE_PATH")
    if raw:
        return Path(raw)
    for cand in (
        Path("data/warehouse.db"),
        Path("data/brandmonitor.db"),
        Path("brandmonitor.db"),
    ):
        if cand.exists():
            return cand
    return None


def load_source_ratings(db_path: Path | None) -> dict[int, float | None]:
    """Join map: wh_race_results.id (result_id) → source_rating."""
    if db_path is None or not Path(db_path).exists():
        return {}
    ratings: dict[int, float | None] = {}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            for rid, rating in conn.execute(
                "SELECT id, source_rating FROM wh_race_results"
            ):
                ratings[int(rid)] = float(rating) if rating is not None else None
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    return ratings


class ObservationStore:
    """Load and index freeze observations for race/horse lookup."""

    def __init__(
        self,
        dataset_path: Path,
        *,
        freeze_path: Path | None = None,
        verify_freeze: bool = True,
        warehouse_db_path: Path | None = None,
    ) -> None:
        self.dataset_path = Path(dataset_path)
        self.freeze_path = Path(freeze_path) if freeze_path else None
        self.verify_freeze = verify_freeze
        self.warehouse_db_path = (
            Path(warehouse_db_path) if warehouse_db_path is not None else _default_warehouse_db()
        )
        self.freeze: dict[str, Any] = {}
        self.by_race: dict[int, list[dict[str, Any]]] = {}
        self.by_horse: dict[int, list[dict[str, Any]]] = {}
        self._loaded = False
        self.load_error: str | None = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def dataset_version(self) -> str:
        if self.freeze.get("dataset_version"):
            return str(self.freeze["dataset_version"])
        return "unknown"

    @property
    def ml_status(self) -> str:
        return str(self.freeze.get("ml_status") or "DO_NOT_TRAIN_YET")

    def load(self) -> None:
        if self._loaded:
            return
        if not self.dataset_path.exists():
            msg = (
                f"Prediction dataset not found: {self.dataset_path}. "
                "Restore data/prediction_foundation/datasets/observations.jsonl.gz "
                "matching freeze pf-v1.0.0-20260808 "
                "(do not substitute tests/fixtures/prediction_api/observations_fixture.jsonl.gz)."
            )
            self.load_error = msg
            raise FileNotFoundError(msg)

        if self.freeze_path and self.freeze_path.exists():
            self.freeze = load_freeze(self.freeze_path)
            if self.verify_freeze:
                assert_dataset_matches_freeze(self.freeze, self.dataset_path)
        elif self.freeze_path is None:
            # Prefer project LATEST freeze metadata for version string even when
            # verify is disabled (e.g. test fixture dataset).
            latest = Path("data/prediction_foundation/freezes/LATEST.json")
            if latest.exists():
                self.freeze = load_freeze(latest)

        ratings = load_source_ratings(self.warehouse_db_path)

        by_race: dict[int, list[dict[str, Any]]] = defaultdict(list)
        by_horse: dict[int, list[dict[str, Any]]] = defaultdict(list)

        with gzip.open(self.dataset_path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                row = dict(row)
                row["coverage_level"] = coverage_level(row)
                # Baseline B needs source_rating. Observations often omit it;
                # join from warehouse by result_id when available (same as eval).
                if row.get("source_rating") is None:
                    rid_result = row.get("result_id")
                    if rid_result is not None and int(rid_result) in ratings:
                        row["source_rating"] = ratings[int(rid_result)]
                rid = int(row["race_id"])
                hid = row.get("horse_id")
                by_race[rid].append(row)
                if hid is not None:
                    by_horse[int(hid)].append(row)

        self.by_race = dict(by_race)
        self.by_horse = dict(by_horse)
        self._loaded = True
        self.load_error = None

    def race_ids(self) -> list[int]:
        self.load()
        return sorted(self.by_race)

    def get_race_rows(self, race_id: int) -> list[dict[str, Any]] | None:
        self.load()
        rows = self.by_race.get(int(race_id))
        if not rows:
            return None
        return list(rows)

    def get_horse_rows(self, horse_id: int) -> list[dict[str, Any]] | None:
        self.load()
        rows = self.by_horse.get(int(horse_id))
        if not rows:
            return None
        return list(rows)
