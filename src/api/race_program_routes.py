"""HTTP routes for the future race program (meetings / upcoming races)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from src.api.config import get_api_settings
from src.race_program.eligibility import DEFAULT_UPCOMING_DAYS
from src.race_program.service import RaceProgramService, load_race_program

router = APIRouter(prefix="/race-program", tags=["race-program"])


@lru_cache(maxsize=1)
def _cached_program(path_str: str, mtime_ns: int) -> RaceProgramService:
    return load_race_program(Path(path_str))


def clear_race_program_cache() -> None:
    _cached_program.cache_clear()


def get_race_program() -> RaceProgramService:
    settings = get_api_settings()
    path = Path(settings.race_program_path)
    mtime = path.stat().st_mtime_ns if path.exists() else 0
    return _cached_program(str(path.resolve()), mtime)


@router.get("/upcoming")
def upcoming_meetings(
    days: int = Query(default=DEFAULT_UPCOMING_DAYS, ge=1, le=60),
) -> dict[str, Any]:
    """Upcoming meetings with races eligible for prediction (future only)."""
    try:
        program = get_race_program()
        return program.upcoming_payload(days=days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("race-program upcoming failed")
        raise HTTPException(status_code=500, detail="Internal race-program error") from exc


@router.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: str) -> dict[str, Any]:
    """Future-eligible races for one meeting (human-readable fields + internal ids)."""
    meeting_id = (meeting_id or "").strip()
    if not meeting_id or len(meeting_id) > 80:
        raise HTTPException(status_code=422, detail="Invalid meeting_id")
    try:
        program = get_race_program()
        detail = program.meeting_detail(meeting_id, prediction_only=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("race-program meeting detail failed")
        raise HTTPException(status_code=500, detail="Internal race-program error") from exc
    if detail is None or not detail.get("races"):
        raise HTTPException(status_code=404, detail="Meeting not found or has no upcoming races")
    return detail


@router.get("/five-parreh")
def list_five_parreh() -> dict[str, Any]:
    """Future Five-Parreh events from the same race-program source."""
    try:
        program = get_race_program()
        events = program.list_future_five_parreh_events()
    except Exception as exc:  # noqa: BLE001
        logger.exception("race-program five-parreh list failed")
        raise HTTPException(status_code=500, detail="Internal race-program error") from exc
    return {
        "count": len(events),
        "events": events,
        "message": (
            None
            if events
            else (
                "در حال حاضر رویداد پنج‌پرهٔ آینده‌ای ثبت نشده است."
            )
        ),
    }


@router.get("/five-parreh/{event_id}")
def get_five_parreh_event(event_id: str) -> dict[str, Any]:
    event_id = (event_id or "").strip()
    if not event_id or len(event_id) > 80:
        raise HTTPException(status_code=422, detail="Invalid event_id")
    try:
        program = get_race_program()
        event = program.get_future_five_parreh_event(event_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("race-program five-parreh detail failed")
        raise HTTPException(status_code=500, detail="Internal race-program error") from exc
    if event is None:
        raise HTTPException(status_code=404, detail="Five-Parreh event not found or not future")
    return event
