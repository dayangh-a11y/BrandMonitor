"""Rank fastest horses per breed from harvested histories."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.breeding.productions import BLOOD_LABELS, blood_label
from src.speed.history import (
    MAX_DISTANCE,
    MAX_MPS,
    MAX_TIME_S,
    MIN_DISTANCE,
    MIN_MPS,
    MIN_TIME_S,
    is_plausible_timed_start,
)

MIN_TIMED_STARTS_FOR_PEAK = 3
CLASSIC_DISTANCES = (1000, 1200, 1400, 1600, 1800, 2000, 2200)
TOP_N = 10


def _placed_timed_starts(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Plausible clocks from top-3 finishes only (reduces also-ran garbage times)."""
    out = []
    for s in row.get("starts") or []:
        if not is_plausible_timed_start(s):
            continue
        pos = s.get("finish_position")
        try:
            pos_i = int(pos) if pos is not None else None
        except (TypeError, ValueError):
            pos_i = None
        if pos_i is not None and 1 <= pos_i <= 3:
            out.append(s)
    return out


def _horse_peak(row: dict[str, Any]) -> dict[str, Any] | None:
    blood = row.get("blood")
    if blood not in BLOOD_LABELS and blood != "THORUGHBREAD":
        return None
    timed = _placed_timed_starts(row)
    if len(timed) < MIN_TIMED_STARTS_FOR_PEAK:
        return None
    best = max(timed, key=lambda s: float(s["speed_mps"]))
    speeds = [float(s["speed_mps"]) for s in timed]
    return {
        "source_id": row.get("source_id"),
        "name": row.get("name"),
        "breed_code": blood,
        "breed": blood_label(blood),
        "sex": row.get("sex"),
        "birthdate": row.get("birthdate"),
        "timed_starts": len(timed),
        "best_speed_mps": best["speed_mps"],
        "avg_speed_mps": round(sum(speeds) / len(speeds), 4),
        "best_time_s": best["time_s"],
        "best_time_fmt": best["time_fmt"],
        "best_distance": best["distance"],
        "best_race_date": best.get("race_date"),
        "best_track": best.get("track"),
        "best_race_name": best.get("race_name"),
        "best_finish": best.get("finish_position"),
    }


def _distance_records(harvest_rows: list[dict[str, Any]]) -> dict[str, dict[int, list[dict[str, Any]]]]:
    """Per breed → distance → sorted best times (lowest time_s)."""
    buckets: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in harvest_rows:
        blood = row.get("blood")
        if blood not in BLOOD_LABELS:
            continue
        for st in row.get("starts") or []:
            if not is_plausible_timed_start(st):
                continue
            # Official distance records: winning clocks only
            try:
                pos_i = int(st["finish_position"]) if st.get("finish_position") is not None else None
            except (TypeError, ValueError):
                pos_i = None
            if pos_i != 1:
                continue
            dist = int(st["distance"])
            if dist not in CLASSIC_DISTANCES:
                continue
            buckets[blood][dist].append(
                {
                    "source_id": row.get("source_id"),
                    "name": row.get("name"),
                    "breed_code": blood,
                    "breed": blood_label(blood),
                    "distance": dist,
                    "time_s": st["time_s"],
                    "time_fmt": st["time_fmt"],
                    "speed_mps": st["speed_mps"],
                    "race_date": st.get("race_date"),
                    "track": st.get("track"),
                    "race_name": st.get("race_name"),
                    "finish_position": st.get("finish_position"),
                }
            )
    out: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for blood, by_dist in buckets.items():
        out[blood] = {}
        for dist, rows in by_dist.items():
            rows.sort(key=lambda r: (float(r["time_s"]), -float(r["speed_mps"])))
            # best unique horse per distance (keep horse's best only)
            seen: set[str] = set()
            uniq: list[dict[str, Any]] = []
            for r in rows:
                sid = str(r.get("source_id"))
                if sid in seen:
                    continue
                seen.add(sid)
                r = dict(r)
                r["rank"] = len(uniq) + 1
                uniq.append(r)
                if len(uniq) >= TOP_N:
                    break
            out[blood][dist] = uniq
    return out


def build_fastest_report(harvest_rows: list[dict[str, Any]], *, top_n: int = TOP_N) -> dict[str, Any]:
    peaks = []
    for row in harvest_rows:
        if row.get("harvest_status") not in {"OK", "EMPTY"}:
            continue
        peak = _horse_peak(row)
        if peak:
            peaks.append(peak)

    order = ["TURKMEN", "DOKHOON", "THORUGHBREAD", "ARAB"]
    by_breed_peaks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in peaks:
        by_breed_peaks[p["breed_code"]].append(p)
    for blood in by_breed_peaks:
        by_breed_peaks[blood].sort(
            key=lambda r: (-float(r["best_speed_mps"]), -int(r["timed_starts"]))
        )
        for i, r in enumerate(by_breed_peaks[blood], 1):
            r["rank"] = i

    dist_records = _distance_records(harvest_rows)

    headlines = []
    by_breed: dict[str, Any] = {}
    bloods = [b for b in order if b in by_breed_peaks] + [
        b for b in by_breed_peaks if b not in order
    ]
    for blood in bloods:
        top = by_breed_peaks[blood][:top_n]
        dist_block = {
            str(d): (dist_records.get(blood) or {}).get(d) or []
            for d in CLASSIC_DISTANCES
            if (dist_records.get(blood) or {}).get(d)
        }
        best = top[0] if top else None
        # best 1000m record if any
        best_1000 = ((dist_records.get(blood) or {}).get(1000) or [None])[0]
        headlines.append(
            {
                "breed": blood_label(blood),
                "breed_code": blood,
                "fastest_horse": (best or {}).get("name"),
                "best_speed_mps": (best or {}).get("best_speed_mps"),
                "best_time_fmt": (best or {}).get("best_time_fmt"),
                "best_distance": (best or {}).get("best_distance"),
                "best_track": (best or {}).get("best_track"),
                "timed_starts": (best or {}).get("timed_starts"),
                "record_1000m_horse": (best_1000 or {}).get("name") if best_1000 else None,
                "record_1000m_time": (best_1000 or {}).get("time_fmt") if best_1000 else None,
            }
        )
        by_breed[blood] = {
            "breed": blood_label(blood),
            "breed_code": blood,
            "top_by_peak_speed": top,
            "records_by_distance": dist_block,
        }

    timed_total = sum(int(r.get("timed_starts_count") or 0) for r in harvest_rows)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stats_scope": "STATIC_DESCRIPTIVE_CLOCK_TIMES",
        "ml_status": "DO_NOT_TRAIN_YET",
        "metric_definition": {
            "primary": "best_speed_mps = distance_m / time_s (peak career clock, top-3 finishes)",
            "secondary": "best winning time at classic distances (1000–2200m, finish_position=1)",
            "source": "asbdavani horse performance history time (ms) + plan.distance",
            "breed_source": "productions offspring blood label (history plan.blood usually empty)",
            "eligibility_peak": {
                "min_placed_timed_starts": MIN_TIMED_STARTS_FOR_PEAK,
                "finish_positions": [1, 2, 3],
            },
            "plausibility": {
                "min_mps": MIN_MPS,
                "max_mps": MAX_MPS,
                "min_time_s": MIN_TIME_S,
                "max_time_s": MAX_TIME_S,
                "min_distance": MIN_DISTANCE,
                "max_distance": MAX_DISTANCE,
            },
            "note": (
                "Peak m/s can favor short sprints; use distance records for fair "
                "same-distance comparisons."
            ),
        },
        "harvest_summary": {
            "horses": len(harvest_rows),
            "horses_ok": sum(1 for r in harvest_rows if r.get("harvest_status") == "OK"),
            "horses_with_peak_board": len(peaks),
            "timed_starts": timed_total,
        },
        "headlines": headlines,
        "by_breed": by_breed,
    }


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# سریع‌ترین اسب‌های تاریخ به تفکیک نژاد",
        "",
        f"- Generated (UTC): `{report['generated_at_utc']}`",
        f"- Scope: `{report['stats_scope']}`",
        f"- ML: `{report['ml_status']}`",
        "",
        "## معیار",
        "",
        "- سرعت قله: `distance(m) / time(s)` بر حسب متر بر ثانیه (فقط مقام‌های ۱–۳)",
        "- رکورد مسافت: بهترین زمان **برنده** در مسافت‌های کلاسیک",
        "- نژاد از برچسب blood صفحهٔ productions (چون blood روی تاریخچه معمولاً خالی است)",
        f"- حداقل برای جدول قله: {MIN_TIMED_STARTS_FOR_PEAK} استارت زمان‌دار در جمع ۳",
        f"- فیلتر فیزیکی: {MIN_MPS}–{MAX_MPS} m/s و زمان {MIN_TIME_S}–{MAX_TIME_S}s",
        "",
        "## پوشش",
        "",
        f"- اسب‌ها: {report['harvest_summary']['horses']} "
        f"(OK={report['harvest_summary']['horses_ok']})",
        f"- استارت زمان‌دار: {report['harvest_summary']['timed_starts']}",
        f"- واجد شرایط جدول قله: {report['harvest_summary']['horses_with_peak_board']}",
        "",
        "## نتیجهٔ اصلی (سریع‌ترین هر نژاد — قلهٔ m/s)",
        "",
        "| نژاد | اسب | سرعت (m/s) | زمان | مسافت | پیست | استارت زمان‌دار | رکورد ۱۰۰۰م |",
        "|---|---|---:|---:|---:|---|---:|---|",
    ]
    for h in report.get("headlines") or []:
        rec = ""
        if h.get("record_1000m_horse"):
            rec = f"{h['record_1000m_horse']} ({h.get('record_1000m_time')})"
        lines.append(
            f"| {h.get('breed')} | {h.get('fastest_horse') or '—'} | "
            f"{h.get('best_speed_mps') if h.get('best_speed_mps') is not None else '—'} | "
            f"{h.get('best_time_fmt') or '—'} | {h.get('best_distance') or '—'} | "
            f"{h.get('best_track') or '—'} | {h.get('timed_starts') or '—'} | {rec or '—'} |"
        )

    for blood, block in (report.get("by_breed") or {}).items():
        lines += ["", f"## {block.get('breed')} (`{blood}`)", "", "### Top سرعت قله", ""]
        lines.append(
            "| رتبه | نام | m/s | میانگین m/s | زمان قله | مسافت | تاریخ | پیست | استارت |"
        )
        lines.append("|---:|---|---:|---:|---:|---:|---|---|---:|")
        for r in block.get("top_by_peak_speed") or []:
            date = (r.get("best_race_date") or "")[:10]
            lines.append(
                f"| {r.get('rank')} | {r.get('name')} | {r.get('best_speed_mps')} | "
                f"{r.get('avg_speed_mps')} | {r.get('best_time_fmt')} | {r.get('best_distance')} | "
                f"{date} | {r.get('best_track') or '—'} | {r.get('timed_starts')} |"
            )
        lines += ["", "### رکورد مسافت (بهترین زمان)", ""]
        for dist_s, rows in (block.get("records_by_distance") or {}).items():
            if not rows:
                continue
            lines.append(f"#### {dist_s} متر")
            lines.append("")
            lines.append("| رتبه | نام | زمان | m/s | تاریخ | پیست | مقام |")
            lines.append("|---:|---|---:|---:|---|---|---:|")
            for r in rows[:5]:
                date = (r.get("race_date") or "")[:10]
                lines.append(
                    f"| {r.get('rank')} | {r.get('name')} | {r.get('time_fmt')} | "
                    f"{r.get('speed_mps')} | {date} | {r.get('track') or '—'} | "
                    f"{r.get('finish_position') if r.get('finish_position') is not None else '—'} |"
                )
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
