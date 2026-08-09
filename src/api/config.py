"""API settings (CORS + freeze-backed dataset paths)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.utils.settings import Settings as AppSettings

# Canonical freeze body (gitignored). Never substitute the API test fixture in production.
CANONICAL_DATASET_PATH = Path("data/prediction_foundation/datasets/observations.jsonl.gz")
FIXTURE_DATASET_PATH = Path("tests/fixtures/prediction_api/observations_fixture.jsonl.gz")


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_title: str = "Horse Racing Prediction API"
    api_version: str = "0.1.0"
    # Comma-separated origins; use "*" only for local/dev.
    api_cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000")
    api_cors_allow_credentials: bool = False

    prediction_dataset_path: Path = CANONICAL_DATASET_PATH
    prediction_freeze_path: Path = Path("data/prediction_foundation/freezes/LATEST.json")
    # Production default: verify sha256 against freeze and require dataset at startup.
    # Fixture/test mode: set PREDICTION_VERIFY_FREEZE=false and point
    # PREDICTION_DATASET_PATH at tests/fixtures/prediction_api/observations_fixture.jsonl.gz.
    prediction_verify_freeze: bool = True
    prediction_default_baseline: str = "A"

    def cors_origins_list(self) -> list[str]:
        raw = [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]
        return raw or ["http://localhost:3000"]

    @property
    def is_production_dataset_mode(self) -> bool:
        """True when freeze verification is enabled (default production path)."""
        return bool(self.prediction_verify_freeze)


def get_api_settings() -> APISettings:
    return APISettings()


def get_app_settings() -> AppSettings:
    return AppSettings()


def _path_looks_like_fixture(path: Path) -> bool:
    text = str(path).replace("\\", "/")
    return "tests/fixtures/" in text or path.name == "observations_fixture.jsonl.gz"


def missing_production_dataset_message(dataset_path: Path, freeze_path: Path) -> str:
    expected_sha = "unknown"
    dataset_version = "pf-v1.0.0-20260808"
    try:
        from src.prediction_foundation.freeze import load_freeze

        freeze = load_freeze(freeze_path)
        expected_sha = str(freeze.get("dataset_sha256") or expected_sha)
        dataset_version = str(freeze.get("dataset_version") or dataset_version)
    except Exception:  # noqa: BLE001
        pass
    return (
        "PRODUCTION BLOCKER: frozen prediction dataset is missing.\n"
        f"  Expected path: {CANONICAL_DATASET_PATH}\n"
        f"  Configured path: {dataset_path}\n"
        f"  Freeze: {freeze_path} (dataset_version={dataset_version})\n"
        f"  Expected sha256: {expected_sha}\n"
        "Restore the exact frozen file matching that sha256. "
        "Do NOT fabricate, regenerate, or substitute "
        f"{FIXTURE_DATASET_PATH} in production.\n"
        "Fixture/test only: set PREDICTION_DATASET_PATH to the fixture and "
        "PREDICTION_VERIFY_FREEZE=false."
    )


def validate_prediction_dataset_settings(settings: APISettings | None = None) -> None:
    """Fail fast for misconfigured dataset modes. No silent fixture fallback."""
    settings = settings or get_api_settings()
    path = Path(settings.prediction_dataset_path)

    if settings.is_production_dataset_mode:
        if _path_looks_like_fixture(path):
            raise RuntimeError(
                "PRODUCTION BLOCKER: PREDICTION_VERIFY_FREEZE=true refuses the test "
                f"fixture dataset ({path}). Restore {CANONICAL_DATASET_PATH} or, for "
                "local fixture smoke only, set PREDICTION_VERIFY_FREEZE=false."
            )
        if not path.exists():
            raise RuntimeError(
                missing_production_dataset_message(path, settings.prediction_freeze_path)
            )
        # Enforce freeze sha256 match at startup (unchanged freeze semantics).
        from src.prediction_foundation.freeze import assert_dataset_matches_freeze, load_freeze

        freeze = load_freeze(settings.prediction_freeze_path)
        assert_dataset_matches_freeze(freeze, path)
        return

    # Fixture / explicit non-verify mode (tests and local smoke).
    if not path.exists():
        raise RuntimeError(
            f"Fixture/test dataset not found: {path}. "
            f"Point PREDICTION_DATASET_PATH at {FIXTURE_DATASET_PATH} "
            "when PREDICTION_VERIFY_FREEZE=false."
        )
