#!/usr/bin/env python3
"""PRE-RACE HISTORICAL + CONTEXTUAL RANKING (not a Prediction).

- Never deletes historical races to inflate scores.
- Uses recency weighting: recent races count more, older remain.
- Distance audit uses warehouse + raw/source distance fields.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sqlite3

DB_PATH = ROOT / "output/historical/horse_racing.db"
ARTIFACT_DIR = Path("/opt/cursor/artifacts")

# Upcoming Mashhad card
FIELD = [
    {"card_name": "ماهنور", "horse_id": 6705},
    {"card_name": "چکن چکینی", "horse_id": 3895, "db_name": "چگن چگینی"},
    {"card_name": "گل سو جاهد", "horse_id": 6788},
    {"card_name": "علی بابا", "horse_id": 3981},
    {"card_name": "یاران داوری", "horse_id": 4209},
    {"card_name": "نازگل تاتار علیا", "horse_id": 3988},
    {"card_name": "گدر سن سجادی", "horse_id": 1771},
]

TARGET_TRACK = "مشهد"
TARGET_DISTANCE = 1300
TARGET_BREED = "ترکمن"
# Class 6 / rating band ~60-64 on card — comparable if race_name mentions کلاس6 / کلاس 6 / 60- etc.
CLASS_PATTERNS = [
    re.compile(r"کلاس\s*6"),
    re.compile(r"کلاس6"),
    re.compile(r"\(65-51\)"),
    re.compile(r"\(60-"),
    re.compile(r"60-64"),
    re.compile(r"51-65"),
]

# Recency half-life in days for career historical weighting
HALF_LIFE_DAYS = 365.0
# Recent-form window
RECENT_N = 5
AS_OF = date(2026, 8, 8)  # ranking as-of (today in task context)


def finish_points(finish: int | None) -> float | None:
    if finish is None or finish < 1:
        return None
    return max(0.0, 100.0 - (finish - 1) * 12.0)


def recency_weight(race_date: date, as_of: date = AS_OF, half_life: float = HALF_LIFE_DAYS) -> float:
    days = max(0, (as_of - race_date).days)
    return 0.5 ** (days / half_life)


def weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    """pairs of (value, weight)."""
    if not pairs:
        return None
    num = sum(v * w for v, w in pairs)
    den = sum(w for _, w in pairs)
    if den <= 0:
        return None
    return num / den


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(str(s)[:10])


def is_comparable_class(race_name: str | None) -> bool:
    if not race_name:
        return False
    return any(p.search(race_name) for p in CLASS_PATTERNS)


@dataclass
class Start:
    result_id: int
    race_id: int
    race_date: date
    track: str | None
    distance_wh: int | None
    distance_raw: int | None
    distance_effective: int | None
    surface: str | None
    race_name: str | None
    finish: int | None
    source_race_id: str | None


def connect() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def load_starts(c: sqlite3.Connection, horse_id: int) -> list[Start]:
    rows = c.execute(
        """
        SELECT
            r.id AS result_id,
            rac.id AS race_id,
            rac.race_date,
            rac.track,
            rac.distance AS distance_wh,
            rac.surface,
            rac.name AS race_name,
            rac.source_race_id,
            rac.raw_race_id,
            r.finish_position,
            rr.distance AS distance_raw
        FROM wh_race_results r
        JOIN wh_races rac ON rac.id = r.race_id
        JOIN id_horse_links l ON l.warehouse_horse_id = r.horse_id
        LEFT JOIN raw_races rr ON rr.id = rac.raw_race_id
        WHERE l.horse_id = ?
        ORDER BY rac.race_date ASC, r.id ASC
        """,
        (horse_id,),
    ).fetchall()
    out: list[Start] = []
    for row in rows:
        d = dict(row)
        dist_wh = d["distance_wh"]
        dist_raw = d["distance_raw"]
        eff = dist_wh if dist_wh is not None else dist_raw
        rd = parse_date(d["race_date"])
        if rd is None:
            continue
        out.append(
            Start(
                result_id=int(d["result_id"]),
                race_id=int(d["race_id"]),
                race_date=rd,
                track=d["track"],
                distance_wh=int(dist_wh) if dist_wh is not None else None,
                distance_raw=int(dist_raw) if dist_raw is not None else None,
                distance_effective=int(eff) if eff is not None else None,
                surface=d["surface"],
                race_name=d["race_name"],
                finish=int(d["finish_position"]) if d["finish_position"] is not None else None,
                source_race_id=d["source_race_id"],
            )
        )
    return out


def record_bucket(starts: list[Start], *, distance: int | None = None, track: str | None = None,
                  class_only: bool = False) -> dict[str, Any]:
    sel = starts
    if distance is not None:
        sel = [s for s in sel if s.distance_effective == distance]
    if track is not None:
        sel = [s for s in sel if s.track == track]
    if class_only:
        sel = [s for s in sel if is_comparable_class(s.race_name)]
    finishes = [s.finish for s in sel if s.finish is not None and s.finish >= 1]
    return {
        "starts": len(sel),
        "wins": sum(1 for f in finishes if f == 1),
        "seconds": sum(1 for f in finishes if f == 2),
        "thirds": sum(1 for f in finishes if f == 3),
        "avg_finish": round(sum(finishes) / len(finishes), 3) if finishes else None,
        "best_finish": min(finishes) if finishes else None,
        "dates": [s.race_date.isoformat() for s in sel],
        "distances_seen": sorted({s.distance_effective for s in sel if s.distance_effective}),
    }


def last5_string(starts: list[Start]) -> str:
    recent = starts[-RECENT_N:]
    parts = []
    for s in recent:
        if s.finish is None or s.finish < 1:
            parts.append("DNF/NULL")
        else:
            parts.append(str(s.finish))
    return "-".join(parts)


def historical_score_recency(starts: list[Start]) -> float | None:
    pairs: list[tuple[float, float]] = []
    for s in starts:
        pts = finish_points(s.finish)
        if pts is None:
            # Keep the start in career, but give weak penalty weight instead of deleting
            pts = 20.0
            w = recency_weight(s.race_date) * 0.5
        else:
            w = recency_weight(s.race_date)
        pairs.append((pts, w))
    val = weighted_mean(pairs)
    return round(val, 2) if val is not None else None


def recent_form_score(starts: list[Start]) -> float | None:
    recent = starts[-RECENT_N:]
    if not recent:
        return None
    pairs: list[tuple[float, float]] = []
    # Within last-5, more recent gets higher linear weight
    for i, s in enumerate(recent):
        linear = (i + 1) / len(recent)  # oldest in window = small
        pts = finish_points(s.finish)
        if pts is None:
            pts = 20.0
            w = linear * 0.5
        else:
            w = linear
        # Also apply calendar recency
        w *= recency_weight(s.race_date, half_life=180.0)
        pairs.append((pts, w))
    val = weighted_mean(pairs)
    return round(val, 2) if val is not None else None


def subset_score(starts: list[Start]) -> float | None:
    """Recency-weighted finish score on a subset; None if empty."""
    if not starts:
        return None
    return historical_score_recency(starts)


def confidence_label(
    *,
    starts_n: int,
    birth_year_ok: bool,
    has_track: bool,
    has_distance: bool,
    has_class: bool,
) -> str:
    score = 0
    if starts_n >= 5:
        score += 2
    elif starts_n >= 2:
        score += 1
    if birth_year_ok:
        score += 1
    if has_track:
        score += 1
    if has_distance:
        score += 1
    if has_class:
        score += 1
    if score >= 5:
        return "HIGH"
    if score >= 3:
        return "MEDIUM"
    return "LOW"


def composite(scores: dict[str, float | None]) -> float | None:
    """
    Weights (missing redistributed):
      Historical 0.30, Recent Form 0.30, Track 0.15, Distance 0.15, Class 0.10
    """
    weights = {
        "historical": 0.30,
        "recent_form": 0.30,
        "track": 0.15,
        "distance": 0.15,
        "class": 0.10,
    }
    present = {k: v for k, v in scores.items() if v is not None and k in weights}
    if not present:
        return None
    wsum = sum(weights[k] for k in present)
    return round(sum(present[k] * weights[k] for k in present) / wsum, 2)


def distance_audit_for_horse(c: sqlite3.Connection, horse_id: int, starts: list[Start]) -> dict[str, Any]:
    # Structured vs raw coverage
    wh_null = sum(1 for s in starts if s.distance_wh is None)
    raw_null = sum(1 for s in starts if s.distance_raw is None)
    eff_null = sum(1 for s in starts if s.distance_effective is None)
    dist_hist = Counter(s.distance_effective for s in starts if s.distance_effective is not None)
    detail = []
    for s in starts:
        detail.append(
            {
                "date": s.race_date.isoformat(),
                "race_id": s.race_id,
                "track": s.track,
                "distance_structured_wh": s.distance_wh,
                "distance_raw_source": s.distance_raw,
                "distance_effective": s.distance_effective,
                "race_name": s.race_name,
                "finish": s.finish,
                "target_band": s.distance_effective in (1200, 1300, 1400, 1500),
            }
        )
    return {
        "starts": len(starts),
        "wh_distance_null": wh_null,
        "raw_distance_null": raw_null,
        "effective_distance_null": eff_null,
        "distance_histogram": {str(k): v for k, v in sorted(dist_hist.items())},
        "has_1200": dist_hist.get(1200, 0),
        "has_1300": dist_hist.get(1300, 0),
        "has_1400": dist_hist.get(1400, 0),
        "has_1500": dist_hist.get(1500, 0),
        "note": (
            "Distance exists in wh_races.distance and/or raw_races.distance; "
            "do not label MISSING when effective distance is present."
        ),
        "starts_detail": detail,
    }


def horse_block(c: sqlite3.Connection, card: dict[str, Any]) -> dict[str, Any]:
    horse_id = int(card["horse_id"])
    h = c.execute(
        "SELECT horse_id, display_name, birth_year, meta_json FROM id_horses WHERE horse_id=?",
        (horse_id,),
    ).fetchone()
    meta = json.loads(h["meta_json"] or "{}") if h else {}
    starts = load_starts(c, horse_id)
    finishes = [s.finish for s in starts if s.finish is not None and s.finish >= 1]

    hist = historical_score_recency(starts)
    form = recent_form_score(starts)
    track_starts = [s for s in starts if s.track == TARGET_TRACK]
    dist_starts = [s for s in starts if s.distance_effective == TARGET_DISTANCE]
    # Comparable distance band ±100m around 1300 for contextual distance score if exact missing
    band_starts = [s for s in starts if s.distance_effective in (1200, 1300, 1400, 1500)]
    class_starts = [s for s in starts if is_comparable_class(s.race_name)]

    track_sc = subset_score(track_starts)
    # Prefer exact 1300; else use band with slight discount already via mixture
    if dist_starts:
        dist_sc = subset_score(dist_starts)
        dist_note = "exact_1300"
    elif band_starts:
        dist_sc = subset_score(band_starts)
        # Soft-discount for proxy band
        if dist_sc is not None:
            dist_sc = round(dist_sc * 0.9, 2)
        dist_note = "proxy_1200_1400_1500_band"
    else:
        dist_sc = None
        dist_note = "no_distance_evidence_in_band"

    class_sc = subset_score(class_starts)
    scores = {
        "historical": hist,
        "recent_form": form,
        "track": track_sc,
        "distance": dist_sc,
        "class": class_sc,
    }
    final = composite(scores)

    by = h["birth_year"] if h else None
    # age sanity vs corrected/current birth_year
    birth_ok = True
    if by is not None and starts:
        for s in starts:
            age_at = s.race_date.year - int(by)
            if age_at < 2:
                birth_ok = False
                break

    conf = confidence_label(
        starts_n=len(starts),
        birth_year_ok=birth_ok,
        has_track=bool(track_starts),
        has_distance=bool(dist_starts or band_starts),
        has_class=bool(class_starts),
    )

    return {
        "Horse": h["display_name"] if h else card["card_name"],
        "card_name": card["card_name"],
        "horse_id": horse_id,
        "birth_year": by,
        "birth_year_correction": meta.get("birth_year_correction"),
        "total_starts": len(starts),
        "wins": sum(1 for f in finishes if f == 1),
        "seconds": sum(1 for f in finishes if f == 2),
        "thirds": sum(1 for f in finishes if f == 3),
        "average_finish": round(sum(finishes) / len(finishes), 3) if finishes else None,
        "last_5": last5_string(starts),
        "record_1200m": record_bucket(starts, distance=1200),
        "record_1300m": record_bucket(starts, distance=1300),
        "record_1400m": record_bucket(starts, distance=1400),
        "record_1500m": record_bucket(starts, distance=1500),
        "mashhad_record": record_bucket(starts, track=TARGET_TRACK),
        "comparable_class_record": record_bucket(starts, class_only=True),
        "recent_form_score": form,
        "Historical_Score": hist,
        "Recent_Form_Score": form,
        "Track_Score": track_sc,
        "Distance_Score": dist_sc,
        "Distance_Score_note": dist_note,
        "Class_Score": class_sc,
        "Final_Score": final,
        "Confidence": conf,
        "distance_audit": distance_audit_for_horse(c, horse_id, starts),
        "valid_historical_races_retained": len(starts),
        "suspicious_races_removed": 0,
    }


def legacy_equal_weight_score(block: dict[str, Any]) -> float | None:
    """BEFORE-style composite without recency (simple mean of available components)."""
    # Approximate prior methodology: hist from avg finish, form from last5 exclude null
    # We recompute from stored stats for comparison only.
    return None  # filled in main with before snapshot


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    c = connect()

    # Snapshot BEFORE correction values for horse 1771 from meta/raw observed
    h1771 = c.execute(
        "SELECT horse_id, display_name, birth_year, meta_json FROM id_horses WHERE horse_id=1771"
    ).fetchone()
    meta1771 = json.loads(h1771["meta_json"] or "{}") if h1771 else {}
    old_by = meta1771.get("birth_year_correction", {}).get("old_value")
    if old_by is None:
        old_by = meta1771.get("birth_year_raw_observed", 2023)

    horses = [horse_block(c, card) for card in FIELD]
    ranked = sorted(horses, key=lambda x: (-(x["Final_Score"] or -1), x["horse_id"]))
    for i, h in enumerate(ranked, 1):
        h["rank"] = i

    # BEFORE metadata correction ranking: same recency model but flag age inconsistency
    # for reporting — scores use ALL races either way (no deletion). Difference is confidence
    # and birth_year display / age-gate in confidence.
    before_rows = []
    for h in horses:
        b = dict(h)
        if h["horse_id"] == 1771:
            b["birth_year"] = int(old_by) if old_by is not None else 2023
            # Force LOW confidence under wrong BY
            b["Confidence"] = "LOW"
            b["note"] = "BEFORE: birth_year=2023 made age_at_race negative for 6 starts; races still retained"
        before_rows.append(b)
    before_ranked = sorted(before_rows, key=lambda x: (-(x["Final_Score"] or -1), x["horse_id"]))
    for i, h in enumerate(before_ranked, 1):
        h["rank"] = i

    still_number_one = ranked[0]["horse_id"] == 1771
    h1771_after = next(x for x in ranked if x["horse_id"] == 1771)

    report = {
        "title": "PRE-RACE HISTORICAL + CONTEXTUAL RANKING",
        "not_a_prediction": True,
        "prediction_note": "Do not call this a Prediction yet.",
        "db_race_results_deleted": False,
        "horse_1771_split": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "race": {
            "track": TARGET_TRACK,
            "distance": TARGET_DISTANCE,
            "breed": "Turkmen",
            "class": "6",
            "age": "+3",
        },
        "scoring_rules": {
            "never_delete_valid_races_to_improve_score": True,
            "recency_half_life_days": HALF_LIFE_DAYS,
            "recent_form_window": RECENT_N,
            "weights": {
                "historical": 0.30,
                "recent_form": 0.30,
                "track": 0.15,
                "distance": 0.15,
                "class": 0.10,
            },
            "distance_policy": "Use wh_races.distance; fall back to raw_races.distance; never report MISSING if either present.",
            "null_finish_policy": "Retain start; score as weak 20pts at half weight (not deleted).",
        },
        "horse_1771_birth_year": {
            "old_birth_year": old_by,
            "corrected_birth_year": h1771_after["birth_year"],
            "number_of_valid_historical_races_retained": h1771_after["valid_historical_races_retained"],
            "number_of_suspicious_races_removed": 0,
            "correction_provenance": h1771_after.get("birth_year_correction"),
        },
        "comparison_before_after_metadata": {
            "note": "Scores keep all races in both cases. BEFORE differs by confidence / BY metadata only — no fake clean score via deletion.",
            "BEFORE": [
                {
                    "rank": h["rank"],
                    "Horse": h["Horse"],
                    "horse_id": h["horse_id"],
                    "Final_Score": h["Final_Score"],
                    "Confidence": h["Confidence"],
                    "birth_year": h["birth_year"],
                }
                for h in before_ranked
            ],
            "AFTER": [
                {
                    "rank": h["rank"],
                    "Horse": h["Horse"],
                    "horse_id": h["horse_id"],
                    "Final_Score": h["Final_Score"],
                    "Confidence": h["Confidence"],
                    "birth_year": h["birth_year"],
                }
                for h in ranked
            ],
        },
        "ranking_table": [
            {
                "rank": h["rank"],
                "Horse": h["Horse"],
                "horse_id": h["horse_id"],
                "Historical_Score": h["Historical_Score"],
                "Recent_Form_Score": h["Recent_Form_Score"],
                "Track_Score": h["Track_Score"],
                "Distance_Score": h["Distance_Score"],
                "Class_Score": h["Class_Score"],
                "Final_Score": h["Final_Score"],
                "Confidence": h["Confidence"],
            }
            for h in ranked
        ],
        "horse_stats": horses,
        "final_question": {
            "question": "After correcting metadata and extracting distance evidence, is horse_id 1771 still #1?",
            "answer": "YES" if still_number_one else "NO",
            "still_number_one": still_number_one,
        },
    }

    out_json = ARTIFACT_DIR / "prerace_historical_contextual_ranking.json"
    out_md = ARTIFACT_DIR / "prerace_historical_contextual_ranking.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = []
    lines.append("# PRE-RACE HISTORICAL + CONTEXTUAL RANKING")
    lines.append("")
    lines.append("**Not a Prediction.**")
    lines.append("")
    lines.append("## Ranking")
    lines.append("")
    lines.append("| Rank | Horse | horse_id | Historical | Recent Form | Track | Distance | Class | Final | Confidence |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for h in ranked:
        lines.append(
            f"| {h['rank']} | {h['Horse']} | {h['horse_id']} | {h['Historical_Score']} | {h['Recent_Form_Score']} | {h['Track_Score']} | {h['Distance_Score']} | {h['Class_Score']} | {h['Final_Score']} | {h['Confidence']} |"
        )
    lines.append("")
    lines.append("## horse_id 1771 birth_year")
    lines.append("")
    lines.append(f"- Old birth_year: {old_by}")
    lines.append(f"- Corrected birth_year: {h1771_after['birth_year']}")
    lines.append(f"- Valid historical races retained: {h1771_after['valid_historical_races_retained']}")
    lines.append("- Suspicious races removed: **0**")
    lines.append("")
    lines.append("## Final question")
    lines.append("")
    lines.append(f"**Is 1771 still #1?** {report['final_question']['answer']}")
    lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")

    # Also copy under workspace output
    out_dir = ROOT / "output/prerace"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prerace_historical_contextual_ranking.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "prerace_historical_contextual_ranking.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "ranking": report["ranking_table"],
        "horse_1771": report["horse_1771_birth_year"],
        "still_number_one": still_number_one,
        "artifacts": [str(out_json), str(out_md)],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
