"""HTTP API entrypoint — freeze-backed baseline predictions."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from src.api.config import get_api_settings, validate_prediction_dataset_settings
from src.api.deps import get_engine, parse_positive_int, require_engine
from src.api.five_parreh_routes import router as five_parreh_router
from src.api.race_program_routes import router as race_program_router
from src.api.schemas import (
    HealthResponse,
    HorseAnalysisResponse,
    HorseCompareResponse,
    HorseSearchResponse,
    PredictionResponse,
    RaceListResponse,
    RaceResponse,
)

settings = get_api_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Production mode (PREDICTION_VERIFY_FREEZE=true): refuse startup if the
    # canonical frozen observations file is missing. Never fall back to fixture.
    # Re-read settings at startup so test env overrides apply.
    validate_prediction_dataset_settings(get_api_settings())
    yield


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
    description=(
        "Freeze-backed horse racing prediction API. "
        "Uses prediction_foundation baseline ``rank_race`` (SCORE/RANK only). "
        "``probability`` is always null — score is not a probability. "
        f"Dataset freeze: see /health. ML gate remains DO_NOT_TRAIN_YET."
    ),
)

_origins = settings.cors_origins_list()
# Allow explicit "*" for local demos; disable credentials in that case.
_allow_cred = settings.api_cors_allow_credentials and "*" not in _origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_cred,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(five_parreh_router)
app.include_router(race_program_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error on {}", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal prediction error"},
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    engine = get_engine()
    loaded = engine.store.loaded
    if not loaded:
        try:
            engine.store.load()
            loaded = True
        except Exception:  # noqa: BLE001
            loaded = False
    version = settings.api_version
    try:
        ds_version = engine.dataset_version if loaded else _freeze_version_fallback()
        ml_status = engine.ml_status if loaded else "DO_NOT_TRAIN_YET"
    except Exception:  # noqa: BLE001
        ds_version = _freeze_version_fallback()
        ml_status = "DO_NOT_TRAIN_YET"
    return HealthResponse(
        status="ok",
        version=version,
        dataset_version=ds_version,
        ml_status=ml_status,
        dataset_loaded=loaded,
        baseline_default=settings.prediction_default_baseline,
    )


def _freeze_version_fallback() -> str:
    try:
        from src.prediction_foundation.freeze import load_freeze

        return str(load_freeze(settings.prediction_freeze_path).get("dataset_version") or "unknown")
    except Exception:  # noqa: BLE001
        return "pf-v1.0.0-20260808"


@app.get("/races", response_model=RaceListResponse, tags=["races"])
def list_races(
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RaceListResponse:
    """List freeze-backed races (metadata only). No scoring changes."""
    engine = require_engine()
    try:
        payload = engine.list_races(limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        logger.exception("list_races failed")
        raise HTTPException(status_code=500, detail="Internal prediction error") from exc
    return RaceListResponse.model_validate(payload)


@app.get("/races/{race_id}", response_model=RaceResponse, tags=["races"])
def get_race(race_id: str) -> RaceResponse:
    rid = parse_positive_int(race_id, field="race_id")
    engine = require_engine()
    try:
        race = engine.get_race(rid)
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_race failed")
        raise HTTPException(status_code=500, detail="Internal prediction error") from exc
    if race is None:
        raise HTTPException(status_code=404, detail=f"Race {rid} not found in freeze dataset")
    return RaceResponse.model_validate(race)


@app.get(
    "/races/{race_id}/prediction",
    response_model=PredictionResponse,
    tags=["prediction"],
)
def predict_race(
    race_id: str,
    baseline: str = Query(default="A", pattern="^[A-Da-d]$"),
) -> PredictionResponse:
    rid = parse_positive_int(race_id, field="race_id")
    engine = require_engine()
    try:
        result = engine.rank_race(rid, baseline=baseline.upper())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        logger.exception("predict_race failed")
        raise HTTPException(status_code=500, detail="Internal prediction error") from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"Race {rid} not found in freeze dataset")

    # Hard guarantee: never fabricate probability from score.
    for item in result.get("prediction") or []:
        item["probability"] = None

    return PredictionResponse.model_validate(result)


@app.get(
    "/races/{race_id}/compare",
    response_model=HorseCompareResponse,
    tags=["prediction"],
)
def compare_horses(
    race_id: str,
    horse_a: str = Query(..., description="Internal horse_id for side A"),
    horse_b: str = Query(..., description="Internal horse_id for side B"),
    baseline: str = Query(default="A", pattern="^[A-Da-d]$"),
) -> HorseCompareResponse:
    """Pairwise model-score comparison for two horses in the same race."""
    rid = parse_positive_int(race_id, field="race_id")
    hid_a = parse_positive_int(horse_a, field="horse_a")
    hid_b = parse_positive_int(horse_b, field="horse_b")
    engine = require_engine()
    try:
        result = engine.compare_horses(rid, hid_a, hid_b, baseline=baseline.upper())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        logger.exception("compare_horses failed")
        raise HTTPException(status_code=500, detail="Internal prediction error") from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"Race {rid} not found in freeze dataset")
    result["probability"] = None
    if result.get("horse_a"):
        result["horse_a"]["probability"] = None
    if result.get("horse_b"):
        result["horse_b"]["probability"] = None
    if result.get("selected_horse"):
        result["selected_horse"]["probability"] = None
    return HorseCompareResponse.model_validate(result)


@app.get("/horses/search", response_model=HorseSearchResponse, tags=["horses"])
def search_horses(
    name: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
) -> HorseSearchResponse:
    """Search horses by display name. ``horse_id`` is returned for clients; UI should not require users to type it."""
    engine = require_engine()
    try:
        payload = engine.search_horses(name, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        logger.exception("search_horses failed")
        raise HTTPException(status_code=500, detail="Internal prediction error") from exc
    return HorseSearchResponse.model_validate(payload)


@app.get("/horses/{horse_id}", response_model=HorseAnalysisResponse, tags=["horses"])
def get_horse(horse_id: str) -> HorseAnalysisResponse:
    hid = parse_positive_int(horse_id, field="horse_id")
    engine = require_engine()
    try:
        analysis = engine.get_horse_analysis(hid)
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_horse failed")
        raise HTTPException(status_code=500, detail="Internal prediction error") from exc
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Horse {hid} not found in freeze dataset")
    return HorseAnalysisResponse.model_validate(analysis)
