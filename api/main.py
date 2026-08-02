from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.admin import router as admin_router
from api.analytics_routes import router as analytics_router
from api.analytics_ui import router as analytics_ui_router
from api.demo import router as demo_router
from api.deps import close_db, init_db
from api.errors import (
    APIError,
    api_error_handler,
    error_body,
    http_exception_handler,
    unhandled_error_handler,
)
from api.routes import router
from api.schemas import HealthOut
from core.config import load_settings
from core.logging_setup import get_logger, setup_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = load_settings()
    setup_logging(settings)
    log = get_logger("api")
    log.info("api_starting env=%s db=%s", settings.environment, settings.db_path)
    await init_db(settings.db_path)
    try:
        yield
    finally:
        log.info("api_stopping")
        await close_db()


settings = load_settings()
app = FastAPI(
    title="BrandMonitor API",
    version="0.7.0",
    description="BrandMonitor REST API with executive analytics dashboards.",
    lifespan=lifespan,
    debug=settings.api_debug,
)

app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc: RequestValidationError):
    get_logger("api").info("validation_error details=%s", exc.errors())
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "Request validation failed",
            details=exc.errors(),
        ),
    )


app.include_router(router)
app.include_router(demo_router)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(analytics_ui_router)


@app.get("/health", response_model=HealthOut, tags=["system"])
async def health() -> HealthOut:
    from api.deps import _DB

    if _DB is None:
        raise APIError(503, "db_unavailable", "Database is not initialized")
    stats = await _DB.stats()
    return HealthOut(status="ok", stats=stats)
