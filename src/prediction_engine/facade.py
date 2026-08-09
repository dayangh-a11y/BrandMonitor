"""Read-only freeze-backed prediction façade using existing baseline rank_race."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.prediction_foundation.baseline_eval import (
    BASELINE_NAMES,
    race_missing_level,
    rank_race,
    score_A_historical,
    score_B_rating,
    score_C_recent_form,
    score_D_contextual,
)
from src.prediction_engine.horse_directory import (
    HorseNameDirectory,
    build_default_horse_directory,
)
from src.prediction_engine.store import ObservationStore

SCORERS = {
    "A": score_A_historical,
    "B": score_B_rating,
    "C": score_C_recent_form,
    "D": score_D_contextual,
}

DEFAULT_DATASET = Path("data/prediction_foundation/datasets/observations.jsonl.gz")
DEFAULT_FREEZE = Path("data/prediction_foundation/freezes/LATEST.json")


def _row_warnings(row: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    cov = row.get("coverage_level")
    if cov == "LOW":
        warnings.append("low_feature_coverage")
    if row.get("flag__result_quality") in {"MISSING_FINISH", "INVALID_FINISH"}:
        warnings.append(f"result_quality:{row.get('flag__result_quality')}")
    if row.get("flag__unresolved_identity") is True:
        warnings.append("unresolved_identity")
    if row.get("flag__birth_year_confidence") == "LOW":
        warnings.append("missing_or_weak_birth_year")
    if row.get("pred_score") is None:
        warnings.append("score_unavailable_insufficient_features")
    return warnings


def _row_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose existing feature values used by baselines — not new scores."""
    keys = [
        ("career_avg_finish", "career_avg_finish__value"),
        ("career_win_rate", "career_win_rate__value"),
        ("career_top3_rate", "career_top3_rate__value"),
        ("avg_finish_last5", "avg_finish_last5__value"),
        ("win_rate_last5", "win_rate_last5__value"),
        ("form_trend", "form_trend__value"),
        ("track_win_rate", "track_win_rate__value"),
        ("win_rate_same_distance", "win_rate_same_distance__value"),
        ("breed_win_rate", "breed_win_rate__value"),
        ("trainer_win_rate_prior", "trainer_win_rate_prior__value"),
        ("source_rating", "source_rating"),
        ("coverage_level", "coverage_level"),
    ]
    out: list[dict[str, Any]] = []
    for label, key in keys:
        if key in row and row[key] is not None:
            out.append({"metric": label, "value": row[key]})
    return out


def _horse_name(row: dict[str, Any]) -> str | None:
    # Freeze observations do not include display names.
    for key in ("horse_name", "display_name", "name"):
        if row.get(key):
            return str(row[key])
    return None


class FreezeBackedEngine:
    """Minimum façade: race lookup + baseline ``rank_race`` + horse analysis."""

    def __init__(
        self,
        store: ObservationStore,
        *,
        default_baseline: str = "A",
        horse_directory: HorseNameDirectory | None = None,
    ) -> None:
        if default_baseline not in SCORERS:
            raise ValueError(f"Unknown baseline {default_baseline!r}")
        self.store = store
        self.default_baseline = default_baseline
        self.horse_directory = horse_directory or HorseNameDirectory()

    @classmethod
    def from_paths(
        cls,
        dataset_path: Path | None = None,
        freeze_path: Path | None = None,
        *,
        verify_freeze: bool = True,
        default_baseline: str = "A",
        horse_name_index_path: Path | None = None,
    ) -> FreezeBackedEngine:
        store = ObservationStore(
            Path(dataset_path or DEFAULT_DATASET),
            freeze_path=Path(freeze_path) if freeze_path else DEFAULT_FREEZE,
            verify_freeze=verify_freeze,
        )
        directory = build_default_horse_directory(index_path=horse_name_index_path)
        return cls(store, default_baseline=default_baseline, horse_directory=directory)

    @property
    def dataset_version(self) -> str:
        self.store.load()
        return self.store.dataset_version

    @property
    def ml_status(self) -> str:
        self.store.load()
        return self.store.ml_status

    def list_races(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """List freeze race summaries (no scoring changes)."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        ids = self.store.race_ids()
        total = len(ids)
        page = ids[offset : offset + limit]
        races: list[dict[str, Any]] = []
        for rid in page:
            race = self.get_race(rid)
            if not race:
                continue
            races.append(
                {
                    "race_id": race["race_id"],
                    "race_date": race.get("race_date"),
                    "track": race.get("track"),
                    "distance": race.get("distance"),
                    "breed": race.get("breed"),
                    "field_size": race.get("field_size"),
                    "split": race.get("split"),
                }
            )
        return {
            "dataset_version": self.dataset_version,
            "ml_status": self.ml_status,
            "total": total,
            "offset": offset,
            "limit": limit,
            "races": races,
        }

    def get_race(self, race_id: int) -> dict[str, Any] | None:
        rows = self.store.get_race_rows(race_id)
        if not rows:
            return None
        head = rows[0]
        horses = []
        for r in sorted(rows, key=lambda x: int(x.get("result_id") or 0)):
            horses.append(
                {
                    "horse_id": r.get("horse_id"),
                    "warehouse_horse_id": r.get("warehouse_horse_id"),
                    "result_id": r.get("result_id"),
                    "horse_name": _horse_name(r),
                    "split": r.get("split"),
                    "coverage_level": r.get("coverage_level"),
                }
            )
        return {
            "race_id": int(race_id),
            "dataset_version": self.dataset_version,
            "race_date": head.get("race_date"),
            "track": head.get("race_track__value"),
            "distance": head.get("race_distance__value"),
            "breed": head.get("race_breed__value") or head.get("breed__value"),
            "race_class": head.get("race_class__value"),
            "field_size": len(rows),
            "split": head.get("split"),
            "data_completeness": race_missing_level(rows),
            "horses": horses,
        }

    def rank_race(self, race_id: int, *, baseline: str | None = None) -> dict[str, Any] | None:
        """Run existing ``baseline_eval.rank_race`` on freeze rows for one race.

        ``probability`` is always null — baselines produce SCORE/RANK only.
        """
        rows = self.store.get_race_rows(race_id)
        if not rows:
            return None
        baseline_id = (baseline or self.default_baseline).upper()
        scorer = SCORERS.get(baseline_id)
        if scorer is None:
            raise ValueError(f"Unknown baseline {baseline_id!r}; choose A|B|C|D")

        # IMPORTANT: call existing rank_race unchanged.
        ranked = rank_race(list(rows), scorer)

        prediction = []
        for row in ranked:
            prediction.append(
                {
                    "rank": row["pred_rank"],
                    "horse_id": row.get("horse_id"),
                    "warehouse_horse_id": row.get("warehouse_horse_id"),
                    "result_id": row.get("result_id"),
                    "horse_name": _horse_name(row),
                    "score": row.get("pred_score"),
                    "probability": None,
                    "evidence": _row_evidence(row),
                    "warnings": _row_warnings(row),
                    "coverage_level": row.get("coverage_level"),
                    "split": row.get("split"),
                }
            )

        return {
            "race_id": int(race_id),
            "dataset_version": self.dataset_version,
            "ml_status": self.ml_status,
            "baseline": baseline_id,
            "baseline_name": BASELINE_NAMES.get(baseline_id),
            "data_completeness": race_missing_level(rows),
            "probability_note": (
                "Baselines produce SCORE/RANK only. probability is null; "
                "score must not be interpreted as a probability."
            ),
            "prediction": prediction,
        }

    def search_horses(self, name: str, *, limit: int = 20) -> dict[str, Any]:
        """Search horses by display name. Does not change analysis/scoring logic."""
        q = (name or "").strip()
        if not q:
            raise ValueError("name is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self.store.load()
        # Prefer horses that exist in the freeze dataset (analyzable via GET /horses/{id}).
        hits = self.horse_directory.search(q, limit=max(limit * 5, limit))
        results = []
        for rec in hits:
            if int(rec.horse_id) not in self.store.by_horse:
                continue
            results.append(rec.to_search_dict())
            if len(results) >= limit:
                break
        return {
            "query": q,
            "count": len(results),
            "horses": results,
            "dataset_version": self.dataset_version,
        }

    def get_horse_analysis(self, horse_id: int) -> dict[str, Any] | None:
        """Horse analysis from freeze observations only (no new scoring model)."""
        rows = self.store.get_horse_rows(horse_id)
        if not rows:
            return None
        rows_sorted = sorted(rows, key=lambda r: str(r.get("race_date") or ""))
        latest = rows_sorted[-1]
        directory_rec = self.horse_directory.get(int(horse_id))
        directory_name = directory_rec.horse_name if directory_rec else None

        appearances = []
        for r in rows_sorted:
            appearances.append(
                {
                    "race_id": r.get("race_id"),
                    "result_id": r.get("result_id"),
                    "race_date": r.get("race_date"),
                    "track": r.get("race_track__value"),
                    "distance": r.get("race_distance__value"),
                    "breed": r.get("race_breed__value") or r.get("breed__value"),
                    "split": r.get("split"),
                    "coverage_level": r.get("coverage_level"),
                    "target_finish": r.get("target__target_finish"),
                    "target_win": r.get("target__target_win"),
                    "target_top3": r.get("target__target_top3"),
                }
            )
        warnings = _row_warnings(latest)
        return {
            "horse_id": int(horse_id),
            "horse_name": _horse_name(latest) or directory_name,
            "dataset_version": self.dataset_version,
            "ml_status": self.ml_status,
            "observation_count": len(rows_sorted),
            "latest_race_id": latest.get("race_id"),
            "latest_race_date": latest.get("race_date"),
            "latest_features": _row_evidence(latest),
            "warnings": warnings,
            "evidence": _row_evidence(latest),
            "appearances": appearances,
            "note": (
                "Freeze-backed descriptive analysis from observation features. "
                "Does not emit win probability."
            ),
        }
