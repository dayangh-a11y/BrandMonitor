"""Collect historical prediction-market snapshots into Raw."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.prediction_market.client import MosharekatClient
from src.prediction_market.models import RawPredictionSnapshot
from src.prediction_market.warehouse import build_prediction_warehouse


def _hash_payload(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _append_snapshot(
    session: Session,
    *,
    kind: str,
    source_key: str,
    endpoint: str,
    payload: dict[str, Any],
    race_status: str | None = None,
    is_pre_race: bool = False,
    captured_at: datetime | None = None,
) -> bool:
    """Append snapshot if hash differs from latest for this key/kind."""
    captured = captured_at or datetime.now(timezone.utc)
    digest = _hash_payload(payload)
    latest = session.scalar(
        select(RawPredictionSnapshot)
        .where(
            RawPredictionSnapshot.source == "mosharekat",
            RawPredictionSnapshot.snapshot_kind == kind,
            RawPredictionSnapshot.source_key == str(source_key),
        )
        .order_by(RawPredictionSnapshot.captured_at.desc())
        .limit(1)
    )
    if latest is not None and latest.payload_hash == digest:
        return False
    session.add(
        RawPredictionSnapshot(
            source="mosharekat",
            snapshot_kind=kind,
            source_key=str(source_key),
            endpoint=endpoint,
            race_status=race_status,
            is_pre_race=is_pre_race,
            payload_json=payload,
            payload_hash=digest,
            captured_at=captured,
        )
    )
    return True


def collect_prediction_history(
    session: Session,
    *,
    client: MosharekatClient | None = None,
    limit_days: int | None = None,
    day_ids: list[int] | None = None,
    include_odds: bool = True,
    include_survey: bool = True,
    build_warehouse: bool = True,
) -> dict[str, Any]:
    """
    Pull all public historical race days + racecards (+ odds/survey) into Raw,
    then optionally normalize into warehouse prediction tables.
    """
    client = client or MosharekatClient()
    now = datetime.now(timezone.utc)
    stats = {
        "days_listed": 0,
        "days_fetched": 0,
        "snapshots_written": 0,
        "odds_fetched": 0,
        "survey_fetched": 0,
        "errors": 0,
    }

    days = client.list_race_days(limit=500)
    stats["days_listed"] = len(days)
    _append_snapshot(
        session,
        kind="race_days",
        source_key="all",
        endpoint="/api/v1/races/days",
        payload={"data": {"race_days": days}, "success": True},
        captured_at=now,
    )
    stats["snapshots_written"] += 1

    if day_ids:
        id_set = {int(x) for x in day_ids}
        days = [d for d in days if int(d.get("id", -1)) in id_set]
        # Also allow explicit ids not in list
        known = {int(d.get("id", -1)) for d in days}
        for did in id_set - known:
            days.append({"id": did})

    if limit_days is not None:
        days = days[:limit_days]

    for day in days:
        day_id = day.get("id")
        if day_id is None:
            continue
        try:
            card = client.fetch_racecard(day_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("racecard {} failed: {}", day_id, exc)
            stats["errors"] += 1
            continue
        stats["days_fetched"] += 1
        data = card.get("data") if isinstance(card, dict) else {}
        races = data.get("races") if isinstance(data, dict) else []
        if not isinstance(races, list):
            races = []

        # Day-level pre-race if any race still OPEN
        statuses = [
            str(r.get("status") or "").upper()
            for r in races
            if isinstance(r, dict)
        ]
        day_pre = any(s in {"OPEN", "ACTIVE", "PENDING"} for s in statuses)
        if _append_snapshot(
            session,
            kind="racecard",
            source_key=str(day_id),
            endpoint=f"/api/v1/races/racecard?day_id={day_id}",
            payload=card,
            race_status=",".join(sorted(set(statuses))) or None,
            is_pre_race=day_pre,
            captured_at=now,
        ):
            stats["snapshots_written"] += 1

        for race in races:
            if not isinstance(race, dict):
                continue
            rid = race.get("id")
            if rid is None:
                continue
            status = str(race.get("status") or "").upper()
            pre = status in {"OPEN", "ACTIVE", "PENDING"}
            if include_odds:
                try:
                    odds = client.fetch_odds(rid)
                    if _append_snapshot(
                        session,
                        kind="odds",
                        source_key=str(rid),
                        endpoint=f"/api/v1/pools/race/{rid}/odds",
                        payload=odds,
                        race_status=status or None,
                        is_pre_race=pre,
                        captured_at=now,
                    ):
                        stats["snapshots_written"] += 1
                    stats["odds_fetched"] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("odds {} failed: {}", rid, exc)
                    stats["errors"] += 1
            if include_survey:
                try:
                    survey = client.fetch_survey_statistics(rid)
                    if _append_snapshot(
                        session,
                        kind="survey",
                        source_key=str(rid),
                        endpoint=f"/api/v1/races/{rid}/survey-statistics",
                        payload=survey,
                        race_status=status or None,
                        is_pre_race=pre,
                        captured_at=now,
                    ):
                        stats["snapshots_written"] += 1
                    stats["survey_fetched"] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("survey {} failed: {}", rid, exc)
                    stats["errors"] += 1
        session.flush()

    session.flush()
    if build_warehouse:
        wh_stats = build_prediction_warehouse(session)
        stats["warehouse"] = wh_stats
    logger.info("prediction collect {}", stats)
    return stats
