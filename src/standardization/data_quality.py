"""Module 1 — Data Quality checks + Data Quality Report."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analytics.metrics import parse_prize_map, parse_time_seconds
from src.standardization.models import StdDqReport
from src.warehouse.fuzzy import normalize_name
from src.warehouse.models import (
    WhEntityMatch,
    WhHorse,
    WhJockey,
    WhOwner,
    WhRace,
    WhRaceResult,
    WhTrainer,
)

_TIME_RE = re.compile(
    r"^(\d+:)?\d{1,2}\.\d{1,3}$|^(\d+:\d{2}(\.\d+)?)$|^\d+(\.\d+)?$"
)


def _add_issue(
    issues: list[dict[str, Any]],
    *,
    check: str,
    message: str,
    severity: str = "warning",
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    issues.append(
        {
            "check": check,
            "message": message,
            "severity": severity,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "details": details or {},
        }
    )


def run_warehouse_quality_checks(session: Session) -> dict[str, Any]:
    """
    Detect duplicates, missing fields, impossible orders/times,
    and inconsistent entity names.
    """
    started = time.perf_counter()
    issues: list[dict[str, Any]] = []
    counts = defaultdict(int)

    races = list(session.scalars(select(WhRace)).all())
    results = list(session.scalars(select(WhRaceResult)).all())
    horses = list(session.scalars(select(WhHorse)).all())
    jockeys = list(session.scalars(select(WhJockey)).all())
    trainers = list(session.scalars(select(WhTrainer)).all())
    owners = list(session.scalars(select(WhOwner)).all())

    # --- Duplicate races (same source_race_id or same course+date+number+name) ---
    by_source: dict[tuple[str, str], list[WhRace]] = defaultdict(list)
    by_natural: dict[tuple, list[WhRace]] = defaultdict(list)
    for r in races:
        if r.source_race_id:
            by_source[(r.source, r.source_race_id)].append(r)
        by_natural[
            (r.racecourse_code, str(r.race_date), r.race_number, normalize_name(r.name))
        ].append(r)
    for key, group in by_source.items():
        if len(group) > 1:
            counts["duplicate_races"] += len(group) - 1
            _add_issue(
                issues,
                check="duplicate_races",
                message=f"Duplicate source_race_id {key}",
                severity="error",
                entity_type="wh_race",
                entity_id=",".join(str(g.id) for g in group),
            )
    for key, group in by_natural.items():
        if key[0] is None:
            continue
        if len(group) > 1 and len({g.id for g in group}) > 1:
            # Only flag if distinct ids not already covered by source id
            ids = sorted({g.id for g in group})
            if len(ids) > 1:
                counts["duplicate_races"] += len(ids) - 1
                _add_issue(
                    issues,
                    check="duplicate_races",
                    message=f"Duplicate race natural key {key}",
                    severity="warning",
                    entity_type="wh_race",
                    entity_id=",".join(str(i) for i in ids),
                )

    # --- Duplicate horses (same normalized name, different ids) ---
    horse_by_name: dict[str, list[WhHorse]] = defaultdict(list)
    for h in horses:
        horse_by_name[normalize_name(h.name)].append(h)
    for norm, group in horse_by_name.items():
        if not norm or len(group) < 2:
            continue
        ids = {h.id for h in group}
        if len(ids) > 1:
            counts["duplicate_horses"] += len(ids) - 1
            _add_issue(
                issues,
                check="duplicate_horses",
                message=f"Duplicate horse name '{group[0].name}'",
                severity="warning",
                entity_type="horse",
                entity_id=",".join(str(i) for i in sorted(ids)),
                details={"normalized": norm},
            )

    # --- Duplicate results (same race + horse) ---
    res_key: dict[tuple[int, int], list[WhRaceResult]] = defaultdict(list)
    for res in results:
        if res.horse_id is None:
            continue
        res_key[(res.race_id, res.horse_id)].append(res)
    for key, group in res_key.items():
        if len(group) > 1:
            counts["duplicate_results"] += len(group) - 1
            _add_issue(
                issues,
                check="duplicate_results",
                message=f"Duplicate result race={key[0]} horse={key[1]}",
                severity="error",
                entity_type="wh_race_result",
                entity_id=",".join(str(g.id) for g in group),
            )

    race_by_id = {r.id: r for r in races}
    results_by_race: dict[int, list[WhRaceResult]] = defaultdict(list)
    for res in results:
        results_by_race[res.race_id].append(res)

    for race_id, group in results_by_race.items():
        race = race_by_id.get(race_id)
        prize_map = parse_prize_map(race.prize_json) if race else {}

        positions = []
        for res in group:
            if res.finish_position is None:
                counts["missing_finish_position"] += 1
                _add_issue(
                    issues,
                    check="missing_finish_position",
                    message="Missing finish position",
                    severity="warning",
                    entity_type="wh_race_result",
                    entity_id=res.id,
                    details={"race_id": race_id},
                )
            else:
                positions.append(res.finish_position)

            # Missing prize for placed horses when prize table exists
            if (
                race
                and prize_map
                and res.finish_position is not None
                and res.finish_position in prize_map
                and prize_map[res.finish_position] is None
            ):
                counts["missing_prize"] += 1
                _add_issue(
                    issues,
                    check="missing_prize",
                    message=f"Missing prize for position {res.finish_position}",
                    entity_type="wh_race_result",
                    entity_id=res.id,
                )

            # Impossible race time
            if res.time_raw:
                raw = str(res.time_raw).strip()
                secs = parse_time_seconds(raw)
                bad = False
                if not _TIME_RE.match(raw):
                    bad = True
                elif secs is not None and (secs <= 0 or secs > 600):
                    bad = True
                if bad:
                    counts["impossible_race_time"] += 1
                    _add_issue(
                        issues,
                        check="impossible_race_time",
                        message=f"Impossible race time '{res.time_raw}'",
                        severity="error",
                        entity_type="wh_race_result",
                        entity_id=res.id,
                    )

        # Impossible finish order: duplicates or gaps when dense ranking expected
        if positions:
            pos_counts: dict[int, int] = defaultdict(int)
            for p in positions:
                pos_counts[p] += 1
            for p, c in pos_counts.items():
                if c > 1 and p > 0:
                    # Dead heats allowed once; flag triples+ as suspicious
                    if c >= 3:
                        counts["impossible_finish_order"] += 1
                        _add_issue(
                            issues,
                            check="impossible_finish_order",
                            message=f"Position {p} appears {c} times in race {race_id}",
                            severity="warning",
                            entity_type="wh_race",
                            entity_id=race_id,
                        )
            if min(positions) < 1:
                counts["impossible_finish_order"] += 1
                _add_issue(
                    issues,
                    check="impossible_finish_order",
                    message=f"Finish position < 1 in race {race_id}",
                    severity="error",
                    entity_type="wh_race",
                    entity_id=race_id,
                )
            field = len(group)
            if max(positions) > field + 2:
                counts["impossible_finish_order"] += 1
                _add_issue(
                    issues,
                    check="impossible_finish_order",
                    message=(
                        f"Max finish {max(positions)} > field size {field} "
                        f"in race {race_id}"
                    ),
                    severity="warning",
                    entity_type="wh_race",
                    entity_id=race_id,
                )

        # Missing prize table entirely
        if race and not prize_map:
            counts["missing_prize"] += 1
            _add_issue(
                issues,
                check="missing_prize",
                message="Race has no prize table",
                severity="info",
                entity_type="wh_race",
                entity_id=race_id,
            )

    # --- Inconsistent names (entity match candidates + empty/whitespace) ---
    for entity_type, rows in (
        ("horse", horses),
        ("jockey", jockeys),
        ("trainer", trainers),
        ("owner", owners),
    ):
        for row in rows:
            name = getattr(row, "name", None)
            if not name or not str(name).strip():
                counts[f"inconsistent_{entity_type}_names"] += 1
                _add_issue(
                    issues,
                    check=f"inconsistent_{entity_type}_names",
                    message="Empty name",
                    severity="error",
                    entity_type=entity_type,
                    entity_id=row.id,
                )
            elif name != name.strip() or "  " in name:
                counts[f"inconsistent_{entity_type}_names"] += 1
                _add_issue(
                    issues,
                    check=f"inconsistent_{entity_type}_names",
                    message="Name has irregular whitespace",
                    severity="info",
                    entity_type=entity_type,
                    entity_id=row.id,
                    details={"name": name},
                )

    match_count = session.scalar(
        select(func.count()).select_from(WhEntityMatch).where(
            WhEntityMatch.status == "candidate"
        )
    ) or 0
    counts["entity_match_candidates"] = int(match_count)

    duration = time.perf_counter() - started
    summary = {
        "module": "data_quality",
        "version": "1.0.0",
        "races": len(races),
        "horses": len(horses),
        "results": len(results),
        "jockeys": len(jockeys),
        "trainers": len(trainers),
        "owners": len(owners),
        "issue_counts": dict(counts),
        "issues_total": len(issues),
        "issues_sample": issues[:200],
        "duration_seconds": round(duration, 4),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    status = "ok"
    if counts.get("duplicate_results") or counts.get("impossible_race_time"):
        status = "error"
    elif issues:
        status = "warning"

    report_text = format_dq_report(summary)
    session.add(
        StdDqReport(
            status=status,
            summary_json=summary,
            issues_count=len(issues),
            report_text=report_text,
            version="1.0.0",
        )
    )
    session.flush()
    logger.info("Warehouse DQ: status={} issues={}", status, len(issues))
    summary["status"] = status
    summary["report_text"] = report_text
    return summary


def format_dq_report(summary: dict[str, Any]) -> str:
    counts = summary.get("issue_counts") or {}
    lines = [
        "=== Data Quality Report (Module 1) ===",
        f"Status:                 {summary.get('status', 'n/a')}",
        f"Races:                  {summary.get('races', 0)}",
        f"Horses:                 {summary.get('horses', 0)}",
        f"Results:                {summary.get('results', 0)}",
        f"Jockeys:                {summary.get('jockeys', 0)}",
        f"Trainers:               {summary.get('trainers', 0)}",
        f"Owners:                 {summary.get('owners', 0)}",
        f"Duplicate races:        {counts.get('duplicate_races', 0)}",
        f"Duplicate horses:       {counts.get('duplicate_horses', 0)}",
        f"Duplicate results:      {counts.get('duplicate_results', 0)}",
        f"Missing finish pos:     {counts.get('missing_finish_position', 0)}",
        f"Missing prize:          {counts.get('missing_prize', 0)}",
        f"Impossible finish order:{counts.get('impossible_finish_order', 0)}",
        f"Impossible race time:   {counts.get('impossible_race_time', 0)}",
        f"Inconsistent horses:    {counts.get('inconsistent_horse_names', 0)}",
        f"Inconsistent trainers:  {counts.get('inconsistent_trainer_names', 0)}",
        f"Inconsistent jockeys:   {counts.get('inconsistent_jockey_names', 0)}",
        f"Entity match candidates:{counts.get('entity_match_candidates', 0)}",
        f"Issues total:           {summary.get('issues_total', 0)}",
        f"Duration:               {summary.get('duration_seconds', 0)}s",
    ]
    return "\n".join(lines)
