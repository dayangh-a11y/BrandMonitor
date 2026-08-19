"""Module 11 — Benchmark Engine.

Compare every horse against:
  Breed Average, Season Average, Career Average, Distance Average, Track Average.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.analytics.models import AnlHorseMetrics
from src.standardization.models import StdBenchmark


def _safe_mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return float(mean(vals))


def build_benchmarks(
    session: Session,
    *,
    scope: str = "season",
    season_key: str | None = None,
    metric_names: tuple[str, ...] = (
        "performance_rating",
        "win_rate",
        "avg_finish",
        "consistency_score",
        "earnings_total",
    ),
) -> dict[str, Any]:
    q = select(AnlHorseMetrics).where(
        AnlHorseMetrics.scope == scope,
        AnlHorseMetrics.breed == "*",
    )
    if season_key and season_key != "*":
        q = q.where(AnlHorseMetrics.season_key == season_key)
    rows = list(session.scalars(q).all())
    # Fallback: if no overall (*) rows, use all breeds but collapse per horse
    if not rows:
        q2 = select(AnlHorseMetrics).where(AnlHorseMetrics.scope == scope)
        if season_key and season_key != "*":
            q2 = q2.where(AnlHorseMetrics.season_key == season_key)
        by_horse: dict[int, AnlHorseMetrics] = {}
        for r in session.scalars(q2).all():
            prev = by_horse.get(r.horse_id)
            if prev is None or (r.starts or 0) > (prev.starts or 0):
                by_horse[r.horse_id] = r
        rows = list(by_horse.values())
    if not rows:
        return {"written": 0, "horses": 0}

    # When no explicit season_key, build each season separately to avoid collisions
    if not season_key or season_key == "*":
        if scope == "career":
            return _build_benchmarks_for_season(
                session,
                rows=rows,
                scope=scope,
                season_id="*",
                metric_names=metric_names,
            )
        by_season: dict[str, list[AnlHorseMetrics]] = defaultdict(list)
        for r in rows:
            by_season[r.season_key or "*"].append(r)
        total_written = 0
        total_horses = 0
        for sk, season_rows in by_season.items():
            part = _build_benchmarks_for_season(
                session,
                rows=season_rows,
                scope=scope,
                season_id=sk,
                metric_names=metric_names,
            )
            total_written += int(part.get("written") or 0)
            total_horses += int(part.get("horses") or 0)
        return {
            "written": total_written,
            "horses": total_horses,
            "seasons": len(by_season),
        }

    return _build_benchmarks_for_season(
        session,
        rows=rows,
        scope=scope,
        season_id=season_key,
        metric_names=metric_names,
    )


def _build_benchmarks_for_season(
    session: Session,
    *,
    rows: list[AnlHorseMetrics],
    scope: str,
    season_id: str,
    metric_names: tuple[str, ...],
) -> dict[str, Any]:
    if not rows:
        return {"written": 0, "horses": 0}

    # Career lookup (overall breed only)
    career_rows = list(
        session.scalars(
            select(AnlHorseMetrics).where(
                AnlHorseMetrics.scope == "career",
                AnlHorseMetrics.breed == "*",
            )
        ).all()
    )
    career_by_horse = {r.horse_id: r for r in career_rows}

    session.execute(
        delete(StdBenchmark).where(
            StdBenchmark.scope == scope,
            StdBenchmark.season_id == (season_id or "*"),
        )
    )
    session.flush()

    season_vals: dict[str, list[float]] = defaultdict(list)
    breed_vals: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        for m in metric_names:
            v = getattr(r, m, None)
            if v is None:
                continue
            season_vals[m].append(float(v))
            breed_vals[(r.breed or "*", m)].append(float(v))

    dist_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    track_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        for m in metric_names:
            v = getattr(r, m, None)
            if v is None:
                continue
            if r.distance_preference:
                dist_groups[(r.distance_preference, m)].append(float(v))
            if r.track_preference:
                track_groups[(r.track_preference, m)].append(float(v))

    written = 0
    seen: set[tuple[int, str]] = set()
    for r in rows:
        career = career_by_horse.get(r.horse_id)
        for m in metric_names:
            key = (r.horse_id, m)
            if key in seen:
                continue
            seen.add(key)
            hv = getattr(r, m, None)
            hv_f = float(hv) if hv is not None else None
            season_avg = _safe_mean(season_vals.get(m, []))
            breed_avg = _safe_mean(breed_vals.get((r.breed or "*", m), []))
            career_avg = None
            if career is not None:
                cv = getattr(career, m, None)
                career_avg = float(cv) if cv is not None else None
            distance_avg = None
            if r.distance_preference:
                distance_avg = _safe_mean(
                    dist_groups.get((r.distance_preference, m), [])
                )
            track_avg = None
            if r.track_preference:
                track_avg = _safe_mean(track_groups.get((r.track_preference, m), []))

            delta = None
            if hv_f is not None and season_avg is not None:
                delta = hv_f - season_avg

            session.add(
                StdBenchmark(
                    horse_id=r.horse_id,
                    scope=scope,
                    season_id=season_id or "*",
                    metric_name=m,
                    horse_value=hv_f,
                    breed_avg=breed_avg,
                    season_avg=season_avg,
                    career_avg=career_avg,
                    distance_avg=distance_avg,
                    track_avg=track_avg,
                    delta_vs_season=delta,
                    meta_json={
                        "breed": r.breed,
                        "distance_preference": r.distance_preference,
                        "track_preference": r.track_preference,
                    },
                )
            )
            written += 1

    session.flush()
    logger.info(
        "Benchmarks written={} horses={} season_id={}",
        written,
        len(rows),
        season_id,
    )
    return {"written": written, "horses": len(rows), "season_id": season_id}
