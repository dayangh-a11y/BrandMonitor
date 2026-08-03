"""Postal Intelligence API routes."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from api.auth import require_api_token
from postal.db import PostalIntelligenceDB

router = APIRouter(
    prefix="/postal",
    tags=["postal-intelligence"],
    dependencies=[Depends(require_api_token)],
)


def _db_path() -> str:
    return os.getenv("POSTAL_DB_PATH", "data/postal_intelligence.db")


def _open() -> PostalIntelligenceDB:
    pi = PostalIntelligenceDB(_db_path())
    pi.connect()
    return pi


@router.get("/companies")
def list_companies() -> dict[str, Any]:
    pi = _open()
    try:
        return {"companies": pi.list_companies(), "scores": pi.latest_company_scores()}
    finally:
        pi.close()


@router.get("/companies/{slug}/score")
def company_score(slug: str) -> dict[str, Any]:
    pi = _open()
    try:
        for row in pi.latest_company_scores():
            if row["slug"] == slug:
                return row
        return {"error": "not_found", "slug": slug}
    finally:
        pi.close()


@router.get("/official/{slug}")
def official_profile(slug: str) -> dict[str, Any]:
    import json

    pi = _open()
    try:
        for c in pi.list_companies():
            if c["slug"] == slug:
                off = pi.get_official(int(c["id"]))
                if not off:
                    return {"error": "no_official_profile"}
                return {
                    "company": c,
                    "profile": json.loads(off.get("profile_json") or "{}"),
                }
        return {"error": "not_found"}
    finally:
        pi.close()


@router.get("/branches")
def branch_intelligence(limit: int = Query(100, ge=1, le=5000)) -> dict[str, Any]:
    pi = _open()
    try:
        return {"branches": pi.list_branch_intelligence(limit=limit)}
    finally:
        pi.close()


@router.get("/compare")
def compare() -> dict[str, Any]:
    pi = _open()
    try:
        return pi.latest_comparison("all_companies") or {}
    finally:
        pi.close()


@router.get("/rankings/province")
def province_rankings() -> dict[str, Any]:
    pi = _open()
    try:
        return {"rankings": pi.list_geo_rankings("province")}
    finally:
        pi.close()


@router.get("/rankings/city")
def city_rankings() -> dict[str, Any]:
    pi = _open()
    try:
        return {"rankings": pi.list_geo_rankings("city")}
    finally:
        pi.close()


@router.get("/ui/{page}")
def dashboard_page(page: str = "index.html"):
    from fastapi import HTTPException

    safe = page if page.endswith(".html") else f"{page}.html"
    # prevent path traversal
    safe = os.path.basename(safe)
    path = os.path.join("output/postal_intelligence/dashboards", safe)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Dashboard page not found: {safe}")
    return FileResponse(path, media_type="text/html")
