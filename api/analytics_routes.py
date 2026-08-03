"""Analytics JSON API + export endpoints (Phase 7)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from analytics.export import (
    export_chart_png_svg,
    export_csv,
    export_excel,
    export_json,
    export_pdf,
)
from analytics.filters import AnalyticsFilter
from analytics.service import AnalyticsService
from api.auth import require_api_token
from api.deps import get_db
from api.errors import APIError
from core.db import Database

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_api_token)])


def _filters_from_request(request: Request) -> AnalyticsFilter:
    return AnalyticsFilter.from_params(dict(request.query_params))


def _service(db: Database) -> AnalyticsService:
    return AnalyticsService(db)


@router.get("/companies/{company_id}")
async def company_analytics(
    company_id: int,
    request: Request,
    refresh: bool = Query(False),
    db: Database = Depends(get_db),
) -> dict:
    try:
        return await _service(db).company_dashboard(
            company_id, _filters_from_request(request), force_refresh=refresh
        )
    except KeyError as exc:
        raise APIError(404, "company_not_found", str(exc)) from exc


@router.get("/branches/{branch_id}")
async def branch_analytics(
    branch_id: int,
    request: Request,
    refresh: bool = Query(False),
    db: Database = Depends(get_db),
) -> dict:
    try:
        return await _service(db).branch_dashboard(
            branch_id, _filters_from_request(request), force_refresh=refresh
        )
    except KeyError as exc:
        raise APIError(404, "branch_not_found", str(exc)) from exc


@router.get("/compare")
async def compare_analytics(
    request: Request,
    mode: Literal["company", "branch", "province", "city", "period"] = Query(...),
    ids: str = Query("", description="Comma-separated entity ids"),
    names: str = Query("", description="Comma-separated names/periods"),
    db: Database = Depends(get_db),
) -> dict:
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    name_list = [x.strip() for x in names.split(",") if x.strip()]
    try:
        return await _service(db).compare(
            mode=mode,
            ids=id_list or None,
            names=name_list or None,
            filt=_filters_from_request(request),
        )
    except (KeyError, ValueError) as exc:
        raise APIError(400, "compare_error", str(exc)) from exc


@router.post("/refresh")
async def refresh_analytics(db: Database = Depends(get_db)) -> dict:
    return await _service(db).refresh_all()


@router.get("/companies/{company_id}/geo")
async def company_geo_analytics(
    company_id: int,
    request: Request,
    refresh: bool = Query(False),
    db: Database = Depends(get_db),
) -> dict:
    """Phase 11 geographic analytics payload (map pins, heatmaps, leaderboard)."""
    try:
        return await _service(db).geo_dashboard(
            company_id, _filters_from_request(request), force_refresh=refresh
        )
    except KeyError as exc:
        raise APIError(404, "company_not_found", str(exc)) from exc


@router.get("/companies/{company_id}/geo/export")
async def export_company_geo(
    company_id: int,
    request: Request,
    format: Literal["json", "csv", "excel", "pdf", "png"] = Query("json"),
    chart: str = Query("top10_best_bar"),
    db: Database = Depends(get_db),
) -> Response:
    try:
        payload = await _service(db).geo_dashboard(
            company_id, _filters_from_request(request)
        )
    except KeyError as exc:
        raise APIError(404, "company_not_found", str(exc)) from exc
    return _export_response(
        payload, format=format, chart=chart, stem=f"company_{company_id}_geo"
    )


@router.get("/companies/{company_id}/export")
async def export_company(
    company_id: int,
    request: Request,
    format: Literal["json", "csv", "excel", "pdf", "png"] = Query("json"),
    chart: str = Query("sentiment_pie"),
    db: Database = Depends(get_db),
) -> Response:
    try:
        payload = await _service(db).company_dashboard(
            company_id, _filters_from_request(request)
        )
    except KeyError as exc:
        raise APIError(404, "company_not_found", str(exc)) from exc
    return _export_response(payload, format=format, chart=chart, stem=f"company_{company_id}")


@router.get("/branches/{branch_id}/export")
async def export_branch(
    branch_id: int,
    request: Request,
    format: Literal["json", "csv", "excel", "pdf", "png"] = Query("json"),
    chart: str = Query("rating_trend_line"),
    db: Database = Depends(get_db),
) -> Response:
    try:
        payload = await _service(db).branch_dashboard(
            branch_id, _filters_from_request(request)
        )
    except KeyError as exc:
        raise APIError(404, "branch_not_found", str(exc)) from exc
    return _export_response(payload, format=format, chart=chart, stem=f"branch_{branch_id}")


def _export_response(payload: dict, *, format: str, chart: str, stem: str) -> Response:
    if format == "json":
        return Response(
            export_json(payload),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{stem}.json"'},
        )
    if format == "csv":
        return Response(
            export_csv(payload),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
        )
    if format == "excel":
        return Response(
            export_excel(payload),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
        )
    if format == "pdf":
        return Response(
            export_pdf(payload),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'},
        )
    # png → SVG chart export (lightweight, no pillow dependency)
    charts = payload.get("charts") or {}
    selected = charts.get(chart) or next(iter(charts.values()), {"type": "bar", "labels": [], "values": []})
    return Response(
        export_chart_png_svg(selected),
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="{stem}_{chart}.svg"'},
    )
