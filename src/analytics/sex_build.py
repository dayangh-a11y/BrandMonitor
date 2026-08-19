"""Persist sex-normalization metrics and race compositions into anl_*."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import delete
from sqlalchemy.orm import Session

from src.analytics.metrics import StartRec
from src.analytics.models import AnlRaceSex, AnlSexMetrics
from src.analytics.sex_normalize import (
    HorseSexMetrics,
    SexStrengthFactor,
    compute_all_sex_metrics,
    estimate_sex_strength_factor,
    build_race_compositions,
    resolve_sex_for_start,
)


def persist_race_sex(
    session: Session,
    compositions: dict[int, Any],
    *,
    ssf: SexStrengthFactor | None = None,
) -> int:
    session.execute(delete(AnlRaceSex))
    n = 0
    meta = ssf.to_dict() if ssf else None
    for comp in compositions.values():
        session.add(
            AnlRaceSex(
                race_id=comp.race_id,
                males=comp.males,
                females=comp.females,
                unknown=comp.unknown,
                field_size=comp.field_size,
                mixed_race=comp.mixed,
                meta_json=meta,
            )
        )
        n += 1
    session.flush()
    return n


def persist_sex_metrics(
    session: Session,
    metrics: list[HorseSexMetrics],
    *,
    build_run_id: int | None,
    clear_scope: tuple[str, str] | None = None,
) -> int:
    """
    Persist horse sex metrics.

    If clear_scope=(scope, season_key) is set, delete matching rows first.
    If None, caller should have cleared the table.
    """
    if clear_scope is not None:
        scope, season_key = clear_scope
        session.execute(
            delete(AnlSexMetrics).where(
                AnlSexMetrics.scope == scope,
                AnlSexMetrics.season_key == season_key,
            )
        )
    now = datetime.now(timezone.utc)
    n = 0
    for m in metrics:
        session.add(
            AnlSexMetrics(
                horse_id=m.horse_id,
                horse_name=m.horse_name,
                scope=m.scope,
                season_key=m.season_key,
                sex_normalized=m.sex,
                sex_group=m.sex_group,
                starts=m.starts,
                starts_male_only=m.starts_male_only,
                starts_female_only=m.starts_female_only,
                starts_mixed=m.starts_mixed,
                male_only_performance=m.male_only_performance,
                female_only_performance=m.female_only_performance,
                mixed_race_performance=m.mixed_race_performance,
                performance_vs_males=m.performance_vs_males,
                performance_vs_females=m.performance_vs_females,
                avg_finish_vs_males=m.avg_finish_vs_males,
                avg_finish_vs_females=m.avg_finish_vs_females,
                win_rate_vs_males=m.win_rate_vs_males,
                win_rate_vs_females=m.win_rate_vs_females,
                podium_rate_vs_males=m.podium_rate_vs_males,
                podium_rate_vs_females=m.podium_rate_vs_females,
                sex_adjusted_performance_rating=m.sex_adjusted_performance_rating,
                raw_performance_rating=m.raw_performance_rating,
                sex_strength_factor=m.sex_strength_factor,
                explain_json=m.explain,
                build_run_id=build_run_id,
                computed_at=now,
            )
        )
        n += 1
    session.flush()
    return n


def build_sex_layer(
    session: Session,
    *,
    all_starts: list[StartRec],
    raw_sex_by_horse: dict[int, str | None],
    scoped_starts: list[StartRec],
    scope: str,
    season_key: str,
    build_run_id: int | None,
    global_ssf: SexStrengthFactor,
) -> dict[int, HorseSexMetrics]:
    """
    Compute + persist sex metrics for one scope using a global historical SSF.
    Returns map horse_id → HorseSexMetrics (breed-agnostic).
    """
    _ssf, _comps, metrics = compute_all_sex_metrics(
        scoped_starts,
        raw_sex_by_horse,
        scope=scope,
        season_key=season_key,
        ssf=global_ssf,
    )
    persist_sex_metrics(
        session,
        metrics,
        build_run_id=build_run_id,
        clear_scope=(scope, season_key),
    )
    logger.info(
        "Sex metrics scope={} season={} horses={} ssf={:.4f}",
        scope,
        season_key,
        len(metrics),
        global_ssf.factor,
    )
    return {m.horse_id: m for m in metrics}


def estimate_global_ssf(
    all_starts: list[StartRec],
    raw_sex_by_horse: dict[int, str | None],
) -> tuple[SexStrengthFactor, dict[int, Any]]:
    sex_by: dict[tuple[int, int], Any] = {}
    for s in all_starts:
        sex_by[(s.horse_id, s.race_id)] = resolve_sex_for_start(
            s, raw_sex_by_horse.get(s.horse_id)
        )
    compositions = build_race_compositions(all_starts, sex_by)
    ssf = estimate_sex_strength_factor(all_starts, sex_by, compositions)
    return ssf, compositions
