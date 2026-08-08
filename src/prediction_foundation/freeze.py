"""Immutable freeze metadata for the prediction foundation dataset."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DATASET = Path("data/prediction_foundation/datasets/observations.jsonl.gz")
DEFAULT_FREEZE_DIR = Path("data/prediction_foundation/freezes")
FEATURE_DICT = Path("data/prediction_foundation/reports/feature_dictionary.json")
COUNTS = Path("data/prediction_foundation/reports/observation_counts.json")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def freeze_dataset(
    *,
    dataset_path: Path = DEFAULT_DATASET,
    out_dir: Path = DEFAULT_FREEZE_DIR,
    db_path: Path = Path("output/historical/horse_racing.db"),
    version: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    ts = datetime.now(timezone.utc)
    version = version or f"pf-v1.0.0-{ts.strftime('%Y%m%d')}"
    dataset_sha = sha256_file(dataset_path)
    dict_sha = sha256_file(FEATURE_DICT) if FEATURE_DICT.exists() else None
    db_sha = sha256_file(db_path) if db_path.exists() else None
    counts = json.loads(COUNTS.read_text(encoding="utf-8")) if COUNTS.exists() else {}

    freeze = {
        "dataset_version": version,
        "immutable": True,
        "frozen_at_utc": ts.isoformat(),
        "dataset_path": str(dataset_path),
        "dataset_sha256": dataset_sha,
        "dataset_bytes": dataset_path.stat().st_size,
        "source_db_path": str(db_path) if db_path.exists() else None,
        "source_db_sha256": db_sha,
        "feature_dictionary_path": str(FEATURE_DICT) if FEATURE_DICT.exists() else None,
        "feature_dictionary_sha256": dict_sha,
        "feature_dictionary_version": "1.0.0",
        "observation_count": counts.get("horse_race_observations"),
        "horse_count": counts.get("unique_permanent_horses"),
        "race_count": counts.get("races"),
        "train_count": counts.get("split_counts", {}).get("TRAIN"),
        "validation_count": counts.get("split_counts", {}).get("VALIDATION"),
        "test_count": counts.get("split_counts", {}).get("TEST"),
        "date_min": counts.get("date_min"),
        "date_max": counts.get("date_max"),
        "notes": [
            "Frozen dataset must not change during baseline evaluation.",
            "Baseline evaluation reads this sha256 and refuses mismatch.",
            "No ML training in this phase.",
        ],
        "ml_status": "DO_NOT_TRAIN_YET",
    }
    freeze["content_sha256"] = hashlib.sha256(
        json.dumps(
            {k: freeze[k] for k in freeze if k != "content_sha256"},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{version}.json"
    lock_path = out_dir / f"{version}.json.immutable"
    latest = out_dir / "LATEST.json"

    if out_path.exists() and not force:
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        if existing.get("dataset_sha256") != dataset_sha:
            raise FileExistsError(
                f"Freeze {out_path} exists with different dataset sha. Refusing overwrite."
            )
        return existing

    out_path.write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lock_path.write_text(
        json.dumps(
            {
                "dataset_version": version,
                "dataset_sha256": dataset_sha,
                "frozen_at_utc": freeze["frozen_at_utc"],
                "immutable": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    latest.write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return freeze


def load_freeze(path: Path | None = None) -> dict[str, Any]:
    path = path or (DEFAULT_FREEZE_DIR / "LATEST.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assert_dataset_matches_freeze(freeze: dict[str, Any], dataset_path: Path | None = None) -> None:
    dataset_path = Path(dataset_path or freeze["dataset_path"])
    actual = sha256_file(dataset_path)
    if actual != freeze["dataset_sha256"]:
        raise RuntimeError(
            f"Frozen dataset sha mismatch: freeze={freeze['dataset_sha256']} actual={actual}. "
            "Dataset changed after freeze — abort evaluation."
        )
