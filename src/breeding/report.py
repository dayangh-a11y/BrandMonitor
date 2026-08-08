"""Aggregate productions harvest into per-breed best sire / dam boards."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.breeding.productions import BLOOD_LABELS, blood_label, normalize_blood

# Ranking gates (static descriptive — not as-of / not for ML training)
MIN_RACED_OFFSPRING = 3
MIN_STARTS = 10
WIN_RATE_MIN_STARTS = 20

# Place-weighted progeny racing value (no purse data on /productions)
WIN_W, SECOND_W, THIRD_W = 5, 2, 1


def _empty_bucket() -> dict[str, Any]:
    return {
        "offspring": 0,
        "raced_offspring": 0,
        "winning_offspring": 0,
        "starts": 0,
        "wins": 0,
        "seconds": 0,
        "thirds": 0,
        "top3": 0,
        "prv": 0.0,
    }


def aggregate_parent(row: dict[str, Any]) -> dict[str, Any]:
    """Aggregate one harvested parent into overall + per-blood buckets."""
    by_blood: dict[str, dict[str, Any]] = defaultdict(_empty_bucket)
    overall = _empty_bucket()

    for kid in row.get("offspring") or []:
        blood = normalize_blood(kid.get("blood")) or "UNKNOWN"
        starts = int(kid.get("starts") or 0)
        wins = int(kid.get("wins") or 0)
        seconds = int(kid.get("seconds") or 0)
        thirds = int(kid.get("thirds") or 0)
        top3 = wins + seconds + thirds
        prv = wins * WIN_W + seconds * SECOND_W + thirds * THIRD_W

        for bucket in (overall, by_blood[blood]):
            bucket["offspring"] += 1
            if starts > 0:
                bucket["raced_offspring"] += 1
            if wins > 0:
                bucket["winning_offspring"] += 1
            bucket["starts"] += starts
            bucket["wins"] += wins
            bucket["seconds"] += seconds
            bucket["thirds"] += thirds
            bucket["top3"] += top3
            bucket["prv"] += prv

    def finalize(b: dict[str, Any]) -> dict[str, Any]:
        out = dict(b)
        out["win_rate"] = round(out["wins"] / out["starts"], 4) if out["starts"] else None
        out["top3_rate"] = round(out["top3"] / out["starts"], 4) if out["starts"] else None
        out["prv"] = round(float(out["prv"]), 2)
        return out

    return {
        "parent_source_id": row.get("parent_source_id"),
        "parent_entity_id": row.get("parent_entity_id"),
        "parent_name": row.get("parent_name"),
        "role": row.get("role"),
        "harvest_status": row.get("harvest_status"),
        "offspring_count": row.get("offspring_count"),
        "overall": finalize(overall),
        "by_blood": {k: finalize(v) for k, v in by_blood.items()},
    }


def _rank_key_prv(stats: dict[str, Any]) -> tuple:
    return (
        -float(stats.get("prv") or 0),
        -int(stats.get("wins") or 0),
        -int(stats.get("top3") or 0),
        -(stats.get("win_rate") or 0),
        -int(stats.get("winning_offspring") or 0),
    )


def _rank_key_win_rate(stats: dict[str, Any]) -> tuple:
    return (
        -(stats.get("win_rate") or 0),
        -int(stats.get("wins") or 0),
        -float(stats.get("prv") or 0),
        -int(stats.get("raced_offspring") or 0),
    )


def _eligible_prv(stats: dict[str, Any]) -> bool:
    return (
        int(stats.get("raced_offspring") or 0) >= MIN_RACED_OFFSPRING
        and int(stats.get("starts") or 0) >= MIN_STARTS
    )


def _eligible_win_rate(stats: dict[str, Any]) -> bool:
    return int(stats.get("starts") or 0) >= WIN_RATE_MIN_STARTS


def build_breeding_value_report(
    harvest_rows: list[dict[str, Any]],
    *,
    top_n: int = 10,
) -> dict[str, Any]:
    parents = [aggregate_parent(r) for r in harvest_rows if r.get("harvest_status") in {"OK", "EMPTY"}]
    sires = [p for p in parents if p.get("role") == "SIRE"]
    dams = [p for p in parents if p.get("role") == "DAM"]

    bloods = sorted(
        {
            blood
            for p in parents
            for blood in (p.get("by_blood") or {})
            if blood in BLOOD_LABELS or blood == "THORUGHBREAD"
        }
    )
    # stable known order
    order = ["TURKMEN", "DOKHOON", "THORUGHBREAD", "ARAB"]
    bloods = [b for b in order if b in bloods] + [b for b in bloods if b not in order]

    def board_for(role_parents: list[dict[str, Any]], blood: str, mode: str) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for p in role_parents:
            stats = (p.get("by_blood") or {}).get(blood)
            if not stats:
                continue
            if mode == "prv" and not _eligible_prv(stats):
                continue
            if mode == "win_rate" and not _eligible_win_rate(stats):
                continue
            scored.append(
                {
                    "parent_name": p.get("parent_name"),
                    "parent_source_id": p.get("parent_source_id"),
                    "parent_entity_id": p.get("parent_entity_id"),
                    "role": p.get("role"),
                    "breed_code": blood,
                    "breed": blood_label(blood),
                    **stats,
                }
            )
        key = _rank_key_prv if mode == "prv" else _rank_key_win_rate
        scored.sort(key=key)
        for i, row in enumerate(scored, 1):
            row["rank"] = i
        return scored[:top_n]

    by_breed: dict[str, Any] = {}
    headlines: list[dict[str, Any]] = []
    for blood in bloods:
        sire_prv = board_for(sires, blood, "prv")
        dam_prv = board_for(dams, blood, "prv")
        sire_wr = board_for(sires, blood, "win_rate")
        dam_wr = board_for(dams, blood, "win_rate")
        by_breed[blood] = {
            "breed": blood_label(blood),
            "breed_code": blood,
            "best_stallion_by_prv": sire_prv[0] if sire_prv else None,
            "best_mare_by_prv": dam_prv[0] if dam_prv else None,
            "best_stallion_by_win_rate": sire_wr[0] if sire_wr else None,
            "best_mare_by_win_rate": dam_wr[0] if dam_wr else None,
            "top_stallions_by_prv": sire_prv,
            "top_mares_by_prv": dam_prv,
            "top_stallions_by_win_rate": sire_wr,
            "top_mares_by_win_rate": dam_wr,
        }
        headlines.append(
            {
                "breed": blood_label(blood),
                "breed_code": blood,
                "stallion": (sire_prv[0] or {}).get("parent_name") if sire_prv else None,
                "stallion_prv": (sire_prv[0] or {}).get("prv") if sire_prv else None,
                "stallion_wins": (sire_prv[0] or {}).get("wins") if sire_prv else None,
                "stallion_win_rate": (sire_prv[0] or {}).get("win_rate") if sire_prv else None,
                "stallion_raced_offspring": (sire_prv[0] or {}).get("raced_offspring")
                if sire_prv
                else None,
                "mare": (dam_prv[0] or {}).get("parent_name") if dam_prv else None,
                "mare_prv": (dam_prv[0] or {}).get("prv") if dam_prv else None,
                "mare_wins": (dam_prv[0] or {}).get("wins") if dam_prv else None,
                "mare_win_rate": (dam_prv[0] or {}).get("win_rate") if dam_prv else None,
                "mare_raced_offspring": (dam_prv[0] or {}).get("raced_offspring") if dam_prv else None,
            }
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stats_scope": "STATIC_DESCRIPTIVE_NOT_ASOF",
        "ml_status": "DO_NOT_TRAIN_YET",
        "metric_definition": {
            "primary": "PRV (Progeny Racing Value)",
            "formula": f"PRV = wins*{WIN_W} + seconds*{SECOND_W} + thirds*{THIRD_W}",
            "source_fields": "asbdavani /productions p1/p2/p3/starts/blood",
            "purse_note": "Prize money is not present on productions pages; PRV is place-weighted success.",
            "eligibility_prv": {
                "min_raced_offspring": MIN_RACED_OFFSPRING,
                "min_starts": MIN_STARTS,
            },
            "eligibility_win_rate": {"min_starts": WIN_RATE_MIN_STARTS},
            "breed_scope": "Offspring blood (race breed), not an independently labeled parent breed field.",
        },
        "harvest_summary": {
            "parents_total": len(parents),
            "sires": len(sires),
            "dams": len(dams),
            "offspring_rows": sum(int(p.get("offspring_count") or 0) for p in parents),
        },
        "headlines": headlines,
        "by_breed": by_breed,
        "warning": (
            "آمار توصیفی ایستا است؛ برای پیش‌بینی باید as-of تاریخ مسابقه محاسبه شود "
            "تا نتایج آینده کره‌ها نشت نکند."
        ),
    }


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# باارزش‌ترین نریان و مادیان هر نژاد (تولید کرهٔ کورسی)",
        "",
        f"- Generated (UTC): `{report['generated_at_utc']}`",
        f"- Scope: `{report['stats_scope']}`",
        f"- ML: `{report['ml_status']}`",
        "",
        "## معیار ارزش",
        "",
        f"- امتیاز اصلی **PRV** = `{report['metric_definition']['formula']}`",
        "- منبع: صفحهٔ `/productions` سایت asbdavani (برد/دوم/سوم/استارت/نژاد کره)",
        "- جایزهٔ نقدی روی این صفحه نیست؛ ارزش با وزن‌دهی مقام‌ها تقریب زده شده",
        (
            f"- حداقل واجد شرایط PRV: "
            f"{report['metric_definition']['eligibility_prv']['min_raced_offspring']} کرهٔ مسابقه‌رفته "
            f"و {report['metric_definition']['eligibility_prv']['min_starts']} استارت در همان نژاد"
        ),
        "- تفکیک نژاد بر اساس **نژاد کره (blood)** است",
        "",
        "## خلاصهٔ برداشت",
        "",
        f"- والدین: {report['harvest_summary']['parents_total']} "
        f"(نریان {report['harvest_summary']['sires']} / مادیان {report['harvest_summary']['dams']})",
        f"- ردیف کره: {report['harvest_summary']['offspring_rows']}",
        "",
        "## نتیجهٔ اصلی (رتبهٔ ۱ هر نژاد بر اساس PRV)",
        "",
        "| نژاد | بهترین نریان | PRV | برد کره‌ها | win% | کرهٔ مسابقه‌رفته | بهترین مادیان | PRV | برد کره‌ها | win% | کرهٔ مسابقه‌رفته |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for h in report.get("headlines") or []:
        lines.append(
            "| {breed} | {stallion} | {sp} | {sw} | {swr} | {sro} | {mare} | {mp} | {mw} | {mwr} | {mro} |".format(
                breed=h.get("breed") or "",
                stallion=h.get("stallion") or "—",
                sp=h.get("stallion_prv") if h.get("stallion_prv") is not None else "—",
                sw=h.get("stallion_wins") if h.get("stallion_wins") is not None else "—",
                swr=h.get("stallion_win_rate") if h.get("stallion_win_rate") is not None else "—",
                sro=h.get("stallion_raced_offspring")
                if h.get("stallion_raced_offspring") is not None
                else "—",
                mare=h.get("mare") or "—",
                mp=h.get("mare_prv") if h.get("mare_prv") is not None else "—",
                mw=h.get("mare_wins") if h.get("mare_wins") is not None else "—",
                mwr=h.get("mare_win_rate") if h.get("mare_win_rate") is not None else "—",
                mro=h.get("mare_raced_offspring") if h.get("mare_raced_offspring") is not None else "—",
            )
        )

    for blood, block in (report.get("by_breed") or {}).items():
        lines += [
            "",
            f"## {block.get('breed')} (`{blood}`)",
            "",
            "### نریان — Top PRV",
            "",
        ]
        lines.append("| رتبه | نام | PRV | برد | دوم | سوم | استارت | win% | کره | کرهٔ برنده‌ |")
        lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in block.get("top_stallions_by_prv") or []:
            lines.append(
                f"| {r['rank']} | {r.get('parent_name')} | {r.get('prv')} | {r.get('wins')} | "
                f"{r.get('seconds')} | {r.get('thirds')} | {r.get('starts')} | {r.get('win_rate')} | "
                f"{r.get('raced_offspring')} | {r.get('winning_offspring')} |"
            )
        lines += ["", "### مادیان — Top PRV", ""]
        lines.append("| رتبه | نام | PRV | برد | دوم | سوم | استارت | win% | کره | کرهٔ برنده‌ |")
        lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in block.get("top_mares_by_prv") or []:
            lines.append(
                f"| {r['rank']} | {r.get('parent_name')} | {r.get('prv')} | {r.get('wins')} | "
                f"{r.get('seconds')} | {r.get('thirds')} | {r.get('starts')} | {r.get('win_rate')} | "
                f"{r.get('raced_offspring')} | {r.get('winning_offspring')} |"
            )

    lines += [
        "",
        "## هشدار",
        "",
        report.get("warning") or "",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
