"""Deterministic ranking service using historical career stats (Baseline A style).

No ML. No betting. Leakage-safe when as_of_date is provided (uses only prior races).
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.prediction_engine.contract import CONTRACT_VERSION

DEFAULT_DB = Path(__file__).resolve().parents[2] / "output" / "historical" / "horse_racing.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn(db: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    return c


def _reliability(n: int) -> str:
    if n < 3:
        return "VERY_LOW"
    if n <= 4:
        return "LOW"
    if n <= 9:
        return "MEDIUM"
    return "HIGH"


def _eb_rate(wins: int, n: int, alpha: float = 1.0, beta: float = 7.0) -> float | None:
    if n <= 0:
        return None
    return (wins + alpha) / (n + alpha + beta)


def _prior_stats(
    conn: sqlite3.Connection,
    wh_horse_id: int,
    *,
    before_date: str | None,
    before_race_id: int | None,
) -> dict[str, Any]:
    q = """
        SELECT ra.race_date, ra.id AS race_id, rr.finish_position, ra.distance, ra.track,
               rr.source_rating
        FROM wh_race_results rr
        JOIN wh_races ra ON ra.id = rr.race_id
        WHERE rr.horse_id = ?
    """
    params: list[Any] = [wh_horse_id]
    if before_date:
        q += " AND (ra.race_date < ? OR (ra.race_date = ? AND ra.id < ?))"
        params.extend([before_date, before_date, before_race_id or 0])
    q += " ORDER BY ra.race_date, ra.id"
    rows = conn.execute(q, params).fetchall()
    n = len(rows)
    wins = sum(1 for r in rows if r["finish_position"] == 1)
    top3 = sum(1 for r in rows if r["finish_position"] is not None and r["finish_position"] <= 3)
    pos = [int(r["finish_position"]) for r in rows if r["finish_position"] is not None]
    recent = rows[-5:]
    recent_pos = [r["finish_position"] for r in recent]
    recent_score = None
    if recent_pos:
        # higher better: invert rank when present (ignore non-positive finishes)
        vals = []
        for p in recent_pos:
            if p is None:
                continue
            try:
                pi = int(p)
            except (TypeError, ValueError):
                continue
            if pi <= 0:
                continue
            vals.append(1.0 / pi)
        recent_score = sum(vals) / len(vals) if vals else None
    return {
        "sample_n": n,
        "wins": wins,
        "top3": top3,
        "raw_win_rate": (wins / n) if n else None,
        "smoothed_win_rate": _eb_rate(wins, n),
        "raw_top3_rate": (top3 / n) if n else None,
        "smoothed_top3_rate": _eb_rate(top3, n, alpha=1.0, beta=4.0),
        "avg_finish": (sum(pos) / len(pos)) if pos else None,
        "recent_positions": recent_pos,
        "recent_form_score": recent_score,
        "reliability": _reliability(n),
        "is_missing": n == 0,
    }


def rank_race(
    race_id: int,
    *,
    db_path: Path | str = DEFAULT_DB,
    methodology: str = "baseline_A_historical_v1",
) -> dict[str, Any]:
    """Rank all horses in a warehouse race_id. Returns API-ready JSON dict."""
    db_path = Path(db_path)
    conn = _conn(db_path)
    try:
        race = conn.execute(
            """
            SELECT id, race_date, track, racecourse_code, name, distance, surface, race_number
            FROM wh_races WHERE id = ?
            """,
            (race_id,),
        ).fetchone()
        if not race:
            return {
                "race_id": race_id,
                "as_of_date": None,
                "race_conditions": {},
                "horses": [],
                "top_pick": None,
                "top_3": [],
                "alternate": None,
                "warnings": [f"race_id {race_id} not found"],
                "methodology_version": f"{CONTRACT_VERSION}:{methodology}",
                "timestamp_utc": _utc_now(),
                "error": "RACE_NOT_FOUND",
            }

        as_of = str(race["race_date"]) if race["race_date"] is not None else None
        entries = conn.execute(
            """
            SELECT rr.id AS result_id, rr.horse_id AS wh_horse_id, rr.number, rr.weight,
                   rr.source_rating, rr.finish_position,
                   wh.name AS horse_name, wh.source_horse_id,
                   l.horse_id AS horse_id
            FROM wh_race_results rr
            JOIN wh_horses wh ON wh.id = rr.horse_id
            LEFT JOIN id_horse_links l ON l.warehouse_horse_id = rr.horse_id
            WHERE rr.race_id = ?
            ORDER BY rr.number
            """,
            (race_id,),
        ).fetchall()

        warnings: list[str] = []
        scored: list[dict[str, Any]] = []
        for e in entries:
            horse_id = e["horse_id"]
            if horse_id is None:
                warnings.append(
                    f"wh_horse_id={e['wh_horse_id']} missing permanent horse_id link"
                )
                horse_id = -int(e["wh_horse_id"])  # stable negative sentinel, not a name
            stats = _prior_stats(
                conn,
                int(e["wh_horse_id"]),
                before_date=as_of,
                before_race_id=int(race_id),
            )
            # Score: primarily smoothed win rate + recent form; never call probability
            sw = stats["smoothed_win_rate"] or 0.0
            st = stats["smoothed_top3_rate"] or 0.0
            rf = stats["recent_form_score"] or 0.0
            score = round(100.0 * (0.55 * sw + 0.25 * st + 0.20 * rf), 4)
            if stats["is_missing"]:
                score = 0.0
                warnings.append(
                    f"horse_id={horse_id} has no prior starts before {as_of} (very low evidence)"
                )

            conf = stats["reliability"]
            dq = "MISSING" if stats["is_missing"] else (
                "LOW" if stats["sample_n"] < 5 else ("MEDIUM" if stats["sample_n"] < 10 else "HIGH")
            )
            scored.append(
                {
                    "horse_id": int(horse_id),
                    "warehouse_horse_id": int(e["wh_horse_id"]),
                    "source_horse_id": e["source_horse_id"],
                    "display_name": e["horse_name"],  # presentation only
                    "cloth_number": e["number"],
                    "rank": None,
                    "score": score,
                    "confidence": conf,
                    "data_quality": dq,
                    "evidence": {
                        "prior_starts": stats["sample_n"],
                        "prior_wins": stats["wins"],
                        "prior_top3": stats["top3"],
                        "recent_positions": stats["recent_positions"],
                        "as_of_date": as_of,
                        "cutoff": {
                            "race_date": as_of,
                            "race_id": race_id,
                            "result_id": e["result_id"],
                        },
                    },
                    "feature_summary": {
                        "win_rate": {
                            "value": stats["smoothed_win_rate"],
                            "raw_rate": stats["raw_win_rate"],
                            "smoothed_rate": stats["smoothed_win_rate"],
                            "sample_n": stats["sample_n"],
                            "is_missing": stats["is_missing"],
                            "reliability": stats["reliability"],
                        },
                        "top3_rate": {
                            "value": stats["smoothed_top3_rate"],
                            "raw_rate": stats["raw_top3_rate"],
                            "smoothed_rate": stats["smoothed_top3_rate"],
                            "sample_n": stats["sample_n"],
                            "is_missing": stats["is_missing"],
                            "reliability": stats["reliability"],
                        },
                        "recent_form_score": {
                            "value": stats["recent_form_score"],
                            "sample_n": min(5, stats["sample_n"]),
                            "is_missing": stats["recent_form_score"] is None,
                            "reliability": _reliability(min(5, stats["sample_n"])),
                        },
                        "weight": {
                            "value": e["weight"],
                            "is_missing": e["weight"] is None,
                        },
                        "source_rating_card": {
                            "value": e["source_rating"],
                            "is_missing": e["source_rating"] is None,
                            "note": "card rating shown for context; historical score ignores same-race outcome",
                        },
                    },
                    "actual_finish_position": e["finish_position"],
                }
            )

        scored.sort(key=lambda r: (-r["score"], r["horse_id"]))
        for i, row in enumerate(scored, 1):
            row["rank"] = i

        top_pick = scored[0] if scored else None
        top_3 = scored[:3]
        alternate = scored[3] if len(scored) > 3 else None

        return {
            "race_id": int(race_id),
            "as_of_date": as_of,
            "race_conditions": {
                "track": race["track"],
                "racecourse_code": race["racecourse_code"],
                "distance": race["distance"],
                "surface": race["surface"],
                "race_name": race["name"],
                "race_number": race["race_number"],
                "field_size": len(scored),
            },
            "horses": [
                {
                    "horse_id": h["horse_id"],
                    "rank": h["rank"],
                    "score": h["score"],
                    "confidence": h["confidence"],
                    "data_quality": h["data_quality"],
                    "evidence": h["evidence"],
                    "feature_summary": h["feature_summary"],
                    # optional presentation helpers (not identifiers)
                    "display_name": h["display_name"],
                    "cloth_number": h["cloth_number"],
                }
                for h in scored
            ],
            "top_pick": (
                {
                    "horse_id": top_pick["horse_id"],
                    "rank": 1,
                    "score": top_pick["score"],
                    "display_name": top_pick["display_name"],
                }
                if top_pick
                else None
            ),
            "top_3": [
                {
                    "horse_id": h["horse_id"],
                    "rank": h["rank"],
                    "score": h["score"],
                    "display_name": h["display_name"],
                }
                for h in top_3
            ],
            "alternate": (
                {
                    "horse_id": alternate["horse_id"],
                    "rank": alternate["rank"],
                    "score": alternate["score"],
                    "display_name": alternate["display_name"],
                }
                if alternate
                else None
            ),
            "warnings": warnings,
            "methodology_version": f"{CONTRACT_VERSION}:{methodology}",
            "score_is_probability": False,
            "provenance": {
                "engine": "prediction_engine.service.rank_race",
                "database": str(db_path),
                "uses_betting_data": False,
                "uses_same_race_results_for_features": False,
            },
            "timestamp_utc": _utc_now(),
        }
    finally:
        conn.close()


def get_horse_analysis(
    horse_id: int,
    *,
    db_path: Path | str = DEFAULT_DB,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """API-ready horse dossier (form / track / distance / pedigree file join)."""
    db_path = Path(db_path)
    conn = _conn(db_path)
    try:
        h = conn.execute(
            "SELECT horse_id, display_name, sex, birth_year, status FROM id_horses WHERE horse_id=?",
            (horse_id,),
        ).fetchone()
        if not h:
            return {
                "horse_id": horse_id,
                "error": "HORSE_NOT_FOUND",
                "timestamp_utc": _utc_now(),
            }
        wids = [
            int(r["warehouse_horse_id"])
            for r in conn.execute(
                "SELECT warehouse_horse_id FROM id_horse_links WHERE horse_id=?",
                (horse_id,),
            )
        ]
        starts = []
        if wids:
            q = f"""
                SELECT ra.id AS race_id, ra.race_date, ra.track, ra.distance, ra.name,
                       rr.finish_position, rr.weight, rr.source_rating, rr.number
                FROM wh_race_results rr
                JOIN wh_races ra ON ra.id = rr.race_id
                WHERE rr.horse_id IN ({','.join('?'*len(wids))})
            """
            params: list[Any] = list(wids)
            if as_of_date:
                q += " AND ra.race_date <= ?"
                params.append(as_of_date)
            q += " ORDER BY ra.race_date DESC, ra.id DESC"
            starts = [dict(r) for r in conn.execute(q, params)]

        # pedigree from night_run or pedigree relationships
        ped = {"sire": None, "dam": None, "source": None, "confidence": None}
        rel_path = Path(__file__).resolve().parents[2] / "data" / "night_run" / "phase1_pedigree" / "pedigree_relationships.jsonl"
        if not rel_path.exists():
            rel_path = Path(__file__).resolve().parents[2] / "data" / "pedigree" / "pedigree_relationships.jsonl"
        if rel_path.exists():
            for line in rel_path.open(encoding="utf-8"):
                if not line.strip():
                    continue
                row = json.loads(line)
                hid = row.get("horse_id")
                if hid != horse_id:
                    continue
                ptype = row.get("parent_type") or (
                    "SIRE" if row.get("field") == "sire" else "DAM" if row.get("field") == "dam" else None
                )
                parent = {
                    "parent_id": row.get("parent_id") or row.get("parent_entity_id"),
                    "name": row.get("parent_name"),
                    "confidence": row.get("confidence"),
                    "source": row.get("source"),
                    "evidence": row.get("evidence"),
                }
                if ptype == "SIRE":
                    ped["sire"] = parent
                elif ptype == "DAM":
                    ped["dam"] = parent
                ped["source"] = row.get("source")
                ped["confidence"] = row.get("confidence")

        finished = [s for s in starts if s.get("finish_position") is not None]
        wins = sum(1 for s in finished if s["finish_position"] == 1)
        top3 = sum(1 for s in finished if s["finish_position"] <= 3)

        by_track: dict[str, dict[str, int]] = {}
        by_dist: dict[str, dict[str, int]] = {}
        for s in starts:
            tr = s.get("track") or "UNKNOWN"
            by_track.setdefault(tr, {"starts": 0, "wins": 0, "top3": 0})
            by_track[tr]["starts"] += 1
            if s.get("finish_position") == 1:
                by_track[tr]["wins"] += 1
            if s.get("finish_position") is not None and s["finish_position"] <= 3:
                by_track[tr]["top3"] += 1
            d = str(s.get("distance") or "UNKNOWN")
            by_dist.setdefault(d, {"starts": 0, "wins": 0, "top3": 0})
            by_dist[d]["starts"] += 1
            if s.get("finish_position") == 1:
                by_dist[d]["wins"] += 1
            if s.get("finish_position") is not None and s["finish_position"] <= 3:
                by_dist[d]["top3"] += 1

        n = len(starts)
        return {
            "horse_id": int(horse_id),
            "display_name": h["display_name"],
            "sex": h["sex"],
            "birth_year": h["birth_year"],
            "as_of_date": as_of_date,
            "form": {
                "starts": n,
                "wins": wins,
                "top3": top3,
                "win_rate": {
                    "value": _eb_rate(wins, n),
                    "raw_rate": (wins / n) if n else None,
                    "smoothed_rate": _eb_rate(wins, n),
                    "sample_n": n,
                    "is_missing": n == 0,
                    "reliability": _reliability(n),
                },
                "recent": starts[:5],
            },
            "track_record": by_track,
            "distance_record": by_dist,
            "pedigree": ped,
            "data_quality": "MISSING" if n == 0 else _reliability(n),
            "provenance": {
                "database": str(db_path),
                "warehouse_horse_ids": wids,
                "uses_betting_data": False,
            },
            "timestamp_utc": _utc_now(),
            "methodology_version": CONTRACT_VERSION,
        }
    finally:
        conn.close()
