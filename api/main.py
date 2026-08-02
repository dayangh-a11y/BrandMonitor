from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
from fastapi import HTTPException


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    try:
        yield
    finally:
        await close_db()


app = FastAPI(
    title="BrandMonitor API",
    version="0.3.0",
    description="REST API foundation for BrandMonitor company/branch/review data.",
    lifespan=lifespan,
)

app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "Request validation failed",
            details=exc.errors(),
        ),
    )


app.include_router(router)


@app.get("/health", response_model=HealthOut, tags=["system"])
async def health() -> HealthOut:
    from api.deps import _DB

    if _DB is None:
        raise APIError(503, "db_unavailable", "Database is not initialized")
    stats = await _DB.stats()
    return HealthOut(status="ok", stats=stats)
