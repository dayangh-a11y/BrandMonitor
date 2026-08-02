"""Public API token gate for private beta (does not change response shapes)."""

from __future__ import annotations

from fastapi import Request

from api.errors import APIError
from core.config import load_settings


def token_from_request(request: Request) -> str | None:
    header = request.headers.get("X-API-Token")
    if header:
        return header.strip()
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    query = request.query_params.get("api_token")
    return query.strip() if query else None


async def require_api_token(request: Request) -> None:
    settings = load_settings()
    expected = settings.api_token or "dev-api-token"
    provided = token_from_request(request) or ""
    if provided != expected:
        raise APIError(
            401,
            "unauthorized",
            "API token required (header X-API-Token, Authorization: Bearer, or ?api_token=)",
        )
