"""Build leakage-safe horse×race feature dataset (read-only vs warehouse DB)."""

from __future__ import annotations

import csv
import gzip
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from src.prediction_foundation.baselines import baseline_manifest
from src.prediction_foundation.compute import compute_features, compute_targets
from src.prediction_foundation.dictionary import FEATURE_DICTIONARY, TARGET_DICTIONARY
from src.prediction_foundation.leakage import run_leakage_audit
from src.prediction_foundation.readiness import assess_readiness
from src.prediction_foundation.split import assign_time_splits
from src.prediction_foundation.types import ObservationBundle, ObservationKeys

DEFAULT_DB = Path("output/historical/horse_racing.db")
DEFAULT_OUT = Path("data/prediction_foundation")


def _connect(db_path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    return c


def _load_rows(c: sqlite3.Connection) -> list[dict[str, Any]]:
    """Load all result rows with race context (read-only)."""
    sql = """
    SELECT
      r.id AS result_id,
      r.race_id,
      r.horse_id AS warehouse_horse_id,
      r.trainer_id,
      r.owner_id,
      r.weight,
      r.finish_position,
      r.source_rating,
      rac.race_date,
      rac.track,
      rac.distance AS distance_wh,
      rr.distance AS distance_raw,
      rac.surface,
      rac.name AS race_name,
      l.horse_id AS permanent_horse_id,
      cls.class_code,
      cls.age_restriction,
      ih.birth_year,
      ih.meta_json AS horse_meta_json
    FROM wh_race_results r
    JOIN wh_races rac ON rac.id = r.race_id
    LEFT JOIN raw_races rr ON rr.id = rac.raw_race_id
    LEFT JOIN id_horse_links l ON l.warehouse_horse_id = r.horse_id
    LEFT JOIN id_horses ih ON ih.horse_id = l.horse_id
    LEFT JOIN std_race_classifications cls ON cls.race_id = rac.id
    ORDER BY rac.race_date ASC, r.race_id ASC, r.id ASC
    """
    rows = []
    for row in c.execute(sql):
        d = dict(row)
        dist = d["distance_wh"] if d["distance_wh"] is not None else d["distance_raw"]
        d["distance"] = int(dist) if dist is not None else None
        d["race_date_obj"] = date.fromisoformat(str(d["race_date"])[:10])
        rows.append(d)
    return rows


def _quality_flags(row: dict[str, Any]) -> dict[str, Any]:
    meta = {}
    if row.get("horse_meta_json"):
        try:
            meta = json.loads(row["horse_meta_json"]) if isinstance(row["horse_meta_json"], str) else row["horse_meta_json"]
        except Exception:
            meta = {}
    by_corr = meta.get("birth_year_correction") if isinstance(meta, dict) else None
    birth_conf = "HIGH" if by_corr else ("MEDIUM" if row.get("birth_year") else "LOW")
    identity_conf = "HIGH" if row.get("permanent_horse_id") else "LOW"
    finish = row.get("finish_position")
    if finish is None:
        result_q = "MISSING_FINISH"
    elif int(finish) < 1:
        result_q = "INVALID_FINISH"
    else:
        result_q = "OK"
    return {
        "identity_confidence": identity_conf,
        "birth_year_confidence": birth_conf,
        "result_quality": result_q,
        "trainer_identity_quality": "OK" if row.get("trainer_id") else "MISSING",
        "owner_identity_quality": "OK" if row.get("owner_id") else "MISSING",
        "distance_quality": "OK" if row.get("distance") is not None else "MISSING",
        "class_quality": "OK" if row.get("class_code") else "MISSING_STRUCTURED",
        "unresolved_identity": row.get("permanent_horse_id") is None,
    }


def build_observations(
    rows: list[dict[str, Any]],
    *,
    max_rows: int | None = None,
) -> list[ObservationBundle]:
    # Field sizes
    field_size: dict[int, int] = Counter(r["race_id"] for r in rows)

    # Histories keyed for incremental prior scans
    by_horse: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_trainer: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_owner: dict[int, list[dict[str, Any]]] = defaultdict(list)

    # Global priors from all finishes for EB (approximation; ideally TRAIN-only)
    wins = sum(1 for r in rows if r.get("finish_position") == 1)
    top3 = sum(
        1
        for r in rows
        if r.get("finish_position") is not None and int(r["finish_position"]) in (1, 2, 3)
    )
    valid = sum(1 for r in rows if r.get("finish_position") is not None and int(r["finish_position"]) >= 1)
    win_prior = wins / valid if valid else 0.12
    top3_prior = top3 / valid if valid else 0.33

    unique_dates = sorted({str(r["race_date"])[:10] for r in rows})
    split_map = assign_time_splits(unique_dates)

    bundles: list[ObservationBundle] = []
    leakage_violations = 0

    for i, row in enumerate(rows):
        if max_rows is not None and i >= max_rows:
            break
        wh = int(row["warehouse_horse_id"])
        race_date = row["race_date_obj"]
        race_date_s = race_date.isoformat()

        horse_priors = [
            p
            for p in by_horse.get(wh, [])
            if (p["race_date"], p["race_id"], p["result_id"])
            < (race_date, int(row["race_id"]), int(row["result_id"]))
        ]
        trainer_id = row.get("trainer_id")
        owner_id = row.get("owner_id")
        trainer_priors = (
            [
                p
                for p in by_trainer.get(int(trainer_id), [])
                if (p["race_date"], p["race_id"], p["result_id"])
                < (race_date, int(row["race_id"]), int(row["result_id"]))
            ]
            if trainer_id is not None
            else []
        )
        owner_priors = (
            [
                p
                for p in by_owner.get(int(owner_id), [])
                if (p["race_date"], p["race_id"], p["result_id"])
                < (race_date, int(row["race_id"]), int(row["result_id"]))
            ]
            if owner_id is not None
            else []
        )

        # Leakage assert — priors must be strictly earlier in (date, race_id, result_id)
        cur_key = (race_date, int(row["race_id"]), int(row["result_id"]))
        for p in horse_priors:
            if (p["race_date"], p["race_id"], p["result_id"]) >= cur_key:
                leakage_violations += 1

        keys = ObservationKeys(
            result_id=int(row["result_id"]),
            race_id=int(row["race_id"]),
            horse_id=int(row["permanent_horse_id"]) if row.get("permanent_horse_id") is not None else None,
            warehouse_horse_id=wh,
            race_date=race_date_s,
            track=row.get("track"),
            distance=row.get("distance"),
            surface=row.get("surface"),
            race_name=row.get("race_name"),
            class_code=row.get("class_code"),
            age_category=row.get("age_restriction"),
            trainer_id=int(trainer_id) if trainer_id is not None else None,
            owner_id=int(owner_id) if owner_id is not None else None,
            weight=float(row["weight"]) if row.get("weight") is not None else None,
            field_size=int(field_size.get(int(row["race_id"]), 0)),
            finish_position=int(row["finish_position"])
            if row.get("finish_position") is not None
            else None,
        )

        feats = compute_features(
            keys,
            horse_priors=horse_priors,
            trainer_priors=trainer_priors,
            owner_priors=owner_priors,
            win_prior=win_prior,
            top3_prior=top3_prior,
        )
        # Targets AFTER features — never fed into compute_features
        targets = compute_targets(keys.finish_position)
        flags = _quality_flags(row)
        bundle = ObservationBundle(
            keys=keys,
            features=feats,
            flags=flags,
            targets=targets,
            split=split_map.get(race_date_s),
        )
        bundles.append(bundle)

        # Append current row into histories AFTER feature computation
        hist_row = {
            "race_date": race_date,
            "race_id": int(row["race_id"]),
            "result_id": int(row["result_id"]),
            "finish": keys.finish_position,
            "track": keys.track,
            "dist": keys.distance,
            "surface": keys.surface,
            "class_code": keys.class_code,
        }
        by_horse[wh].append(hist_row)
        if trainer_id is not None:
            by_trainer[int(trainer_id)].append(hist_row)
        if owner_id is not None:
            by_owner[int(owner_id)].append(hist_row)

    if leakage_violations:
        raise RuntimeError(f"Leakage violations detected: {leakage_violations}")

    return bundles


def _coverage_report(bundles: list[ObservationBundle]) -> dict[str, Any]:
    if not bundles:
        return {"features": []}
    names = [f["feature"] for f in FEATURE_DICTIONARY]
    rows = []
    n = len(bundles)
    for name in names:
        missing = 0
        reliable = 0
        for b in bundles:
            cell = b.features.get(name)
            if cell is None or cell.is_missing:
                missing += 1
            else:
                if cell.reliability in ("MEDIUM", "HIGH") or cell.sample_n is None:
                    # non-rate value features without sample still count available
                    if cell.reliability in ("MEDIUM", "HIGH"):
                        reliable += 1
                    elif cell.sample_n is None:
                        reliable += 1
                    elif cell.sample_n >= 5:
                        reliable += 1
        available = n - missing
        rows.append(
            {
                "feature": name,
                "available_pct": round(100.0 * available / n, 2),
                "missing_pct": round(100.0 * missing / n, 2),
                "reliable_pct": round(100.0 * reliable / n, 2),
            }
        )
    return {"observation_n": n, "features": rows}


def _counts(bundles: list[ObservationBundle], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "horse_race_observations": len(bundles),
        "unique_permanent_horses": len({b.keys.horse_id for b in bundles if b.keys.horse_id is not None}),
        "unique_warehouse_horses": len({b.keys.warehouse_horse_id for b in bundles}),
        "races": len({b.keys.race_id for b in bundles}),
        "tracks": len({b.keys.track for b in bundles if b.keys.track}),
        "trainers": len({b.keys.trainer_id for b in bundles if b.keys.trainer_id is not None}),
        "owners": len({b.keys.owner_id for b in bundles if b.keys.owner_id is not None}),
        "split_counts": dict(Counter(b.split for b in bundles)),
        "date_min": min((b.keys.race_date for b in bundles), default=None),
        "date_max": max((b.keys.race_date for b in bundles), default=None),
    }


def _write_jsonl_gz(path: Path, bundles: list[ObservationBundle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for b in bundles:
            f.write(json.dumps(b.to_flat_row(), ensure_ascii=False) + "\n")


def _write_csv_sample(path: Path, bundles: list[ObservationBundle], limit: int = 5000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample = bundles[:limit]
    if not sample:
        return
    rows = [b.to_flat_row() for b in sample]
    keys = sorted({k for r in rows for k in r.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_prediction_foundation(
    *,
    db_path: Path = DEFAULT_DB,
    out_dir: Path = DEFAULT_OUT,
    max_rows: int | None = None,
    write_full_jsonl: bool = True,
) -> dict[str, Any]:
    """
    Build feature dataset + reports. Does NOT modify the database.
    Does NOT train ML.
    """
    out_dir = Path(out_dir)
    reports_dir = out_dir / "reports"
    datasets_dir = out_dir / "datasets"
    reports_dir.mkdir(parents=True, exist_ok=True)
    datasets_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading warehouse rows from {} (read-only)", db_path)
    c = _connect(Path(db_path))
    try:
        rows = _load_rows(c)
    finally:
        c.close()

    logger.info("Building observations from {} result rows", len(rows))
    bundles = build_observations(rows, max_rows=max_rows)
    logger.info("Built {} observations", len(bundles))

    coverage = _coverage_report(bundles)
    counts = _counts(bundles, rows)
    leakage = run_leakage_audit()
    class_ok = sum(1 for b in bundles if not b.features["race_class"].is_missing)
    linked = sum(1 for b in bundles if b.keys.horse_id is not None)
    n = max(1, len(bundles))
    readiness = assess_readiness(
        observation_count=len(bundles),
        coverage=coverage,
        leakage=leakage,
        class_available_pct=100.0 * class_ok / n,
        linked_horse_pct=100.0 * linked / n,
    )

    # Persist dictionary + reports
    (reports_dir / "feature_dictionary.json").write_text(
        json.dumps(
            {"features": FEATURE_DICTIONARY, "targets": TARGET_DICTIONARY},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "coverage_report.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (reports_dir / "observation_counts.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (reports_dir / "leakage_audit.json").write_text(
        json.dumps(leakage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (reports_dir / "baselines.json").write_text(
        json.dumps(baseline_manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (reports_dir / "readiness.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Datasets (file outputs only)
    sample_csv = datasets_dir / "observations_sample.csv"
    _write_csv_sample(sample_csv, bundles, limit=500)
    full_path = None
    if write_full_jsonl:
        full_path = datasets_dir / "observations.jsonl.gz"
        logger.info("Writing full dataset {}", full_path)
        _write_jsonl_gz(full_path, bundles)

    # Markdown summary
    md = _markdown_summary(counts, coverage, leakage, readiness)
    (reports_dir / "prediction_foundation_report.md").write_text(md, encoding="utf-8")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "db_modified": False,
        "ml_trained": False,
        "observation_count": len(bundles),
        "counts": counts,
        "readiness": readiness,
        "outputs": {
            "feature_dictionary": str(reports_dir / "feature_dictionary.json"),
            "coverage_report": str(reports_dir / "coverage_report.json"),
            "observation_counts": str(reports_dir / "observation_counts.json"),
            "leakage_audit": str(reports_dir / "leakage_audit.json"),
            "baselines": str(reports_dir / "baselines.json"),
            "readiness": str(reports_dir / "readiness.json"),
            "report_md": str(reports_dir / "prediction_foundation_report.md"),
            "sample_csv": str(sample_csv),
            "full_jsonl_gz": str(full_path) if full_path else None,
        },
    }
    (reports_dir / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _markdown_summary(
    counts: dict[str, Any],
    coverage: dict[str, Any],
    leakage: dict[str, Any],
    readiness: dict[str, Any],
) -> str:
    lines = [
        "# Prediction Foundation Report",
        "",
        "## Observation counts",
        "",
        f"- horse×race observations: **{counts['horse_race_observations']}**",
        f"- unique permanent horses: **{counts['unique_permanent_horses']}**",
        f"- races: **{counts['races']}**",
        f"- tracks: **{counts['tracks']}**",
        f"- trainers: **{counts['trainers']}**",
        f"- date range: {counts['date_min']} → {counts['date_max']}",
        f"- splits: `{counts['split_counts']}`",
        "",
        "## Readiness",
        "",
        f"**Can we create a leakage-safe training dataset?** "
        f"**{readiness['can_create_leakage_safe_training_dataset']}**",
        "",
        "### Blockers",
    ]
    if readiness["blockers"]:
        lines.extend([f"- {b}" for b in readiness["blockers"]])
    else:
        lines.append("- none")
    lines += ["", "### Warnings"]
    if readiness["warnings"]:
        lines.extend([f"- {w}" for w in readiness["warnings"][:20]])
    else:
        lines.append("- none")
    lines += ["", "## Leakage audit (MEDIUM+ features)", ""]
    for f in leakage.get("medium_or_higher_features", []):
        lines.append(f"- `{f['feature']}` — {f['leakage_risk']}")
    lines += ["", "## Coverage (selected)", "", "| Feature | Available % | Missing % | Reliable % |", "|---|---:|---:|---:|"]
    # show sparse / important features
    interesting = {
        "career_win_rate",
        "avg_finish_last5",
        "win_rate_same_distance",
        "track_win_rate",
        "class_win_rate",
        "trainer_win_rate_prior",
        "owner_win_rate_prior",
        "race_class",
        "assigned_weight",
        "field_size",
    }
    for row in coverage.get("features", []):
        if row["feature"] in interesting:
            lines.append(
                f"| {row['feature']} | {row['available_pct']} | {row['missing_pct']} | {row['reliable_pct']} |"
            )
    lines += [
        "",
        "## Policy",
        "",
        "- DB not modified",
        "- ML not trained",
        "- Betting data not used",
        "- Targets isolated from features",
        "- Chronological splits only",
        "",
    ]
    return "\n".join(lines) + "\n"
