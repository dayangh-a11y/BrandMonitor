"""Phase 8 — Telegram output design (presentation only; no bot code)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.night_run.paths import NIGHT_DIR
from src.prediction_engine.service import rank_race
from src.night_run.paths import DB_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


COMMAND_MAP = {
    "/race": "GET /race/{race_id} + /ranking",
    "/next": "upcoming race discovery (future) → /race/{id}/ranking",
    "/horse": "GET /horse/{horse_id}/analysis",
    "/form": "GET /horse/{horse_id}/form",
    "/pedigree": "GET /horse/{horse_id}/pedigree",
    "/compare": "multi horse_id analysis merge (engine-side)",
    "/predict": "alias of /race ranking — scores not probabilities",
}


def render_race_card(ranking: dict[str, Any]) -> str:
    """Pure presentation helper — no analytics beyond formatting engine JSON."""
    rc = ranking.get("race_conditions") or {}
    track = rc.get("track") or "?"
    dist = rc.get("distance")
    name = rc.get("race_name") or ""
    lines = [
        f"🏇 {track}",
        f"{name} | {dist} متر" if dist else name,
        "",
    ]
    medals = ["🥇", "🥈", "🥉"]
    for i, h in enumerate(ranking.get("top_3") or []):
        medal = medals[i] if i < 3 else "•"
        lines.append(f"{medal} {h.get('display_name') or h.get('horse_id')}")
        lines.append(f"Score: {h.get('score')}")
        # enrich from full horses list
        full = next(
            (x for x in ranking.get("horses") or [] if x.get("horse_id") == h.get("horse_id")),
            {},
        )
        if i == 0:
            lines.append(f"Confidence: {full.get('confidence')}")
            lines.append(f"Data quality: {full.get('data_quality')}")
        lines.append("")
    warns = ranking.get("warnings") or []
    if warns:
        lines.append("⚠️ هشدار:")
        for w in warns[:5]:
            lines.append(f"- {w}")
        lines.append("")
    lines.append("جزئیات اختیاری: [فرم اخیر] [شجره] [میادین] [مسافت] [تحلیل کامل]")
    lines.append(
        f"(methodology={ranking.get('methodology_version')}; score≠probability)"
    )
    return "\n".join(lines)


def run_phase8() -> dict[str, Any]:
    out = NIGHT_DIR / "phase8_telegram_design"
    out.mkdir(parents=True, exist_ok=True)

    design = {
        "generated_at_utc": _utc_now(),
        "telegram_ui_implemented": False,
        "role": "PRESENTATION_LAYER_ONLY",
        "commands": COMMAND_MAP,
        "card_sections": [
            "header_track_distance",
            "top_pick_with_score_confidence",
            "top_2_top_3",
            "warnings",
            "optional_form",
            "optional_pedigree",
            "optional_track",
            "optional_distance",
            "optional_full_analysis",
        ],
        "engine_fields_required": [
            "race_id",
            "as_of_date",
            "race_conditions",
            "horses[].horse_id",
            "horses[].rank",
            "horses[].score",
            "horses[].confidence",
            "horses[].data_quality",
            "horses[].evidence",
            "horses[].feature_summary",
            "warnings",
            "methodology_version",
        ],
        "forbidden": [
            "analytical calculations exclusive to Telegram handlers",
            "using display names as primary identifiers",
            "calling score a probability",
            "betting tips language",
        ],
    }

    example_text = None
    sample_race_id = None
    sample_path = NIGHT_DIR / "phase6_prediction_engine" / "sample_rank_race.json"
    ranking = None
    if sample_path.exists():
        ranking = json.loads(sample_path.read_text(encoding="utf-8"))
        sample_race_id = ranking.get("race_id")
        example_text = render_race_card(ranking)
    elif DB_PATH.exists():
        # fallback tiny sample
        import sqlite3

        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT race_id FROM wh_race_results GROUP BY race_id HAVING COUNT(*)>=6 ORDER BY race_id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            sample_race_id = int(row[0])
            ranking = rank_race(sample_race_id, db_path=DB_PATH)
            example_text = render_race_card(ranking)

    (out / "telegram_output_design.json").write_text(
        json.dumps(design, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if example_text:
        (out / "example_race_card.txt").write_text(example_text + "\n", encoding="utf-8")
    if ranking:
        (out / "example_engine_payload.json").write_text(
            json.dumps(ranking, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    (out / "TELEGRAM_OUTPUT_DESIGN.md").write_text(
        "\n".join(
            [
                "# Phase 8 — Telegram Output Design",
                "",
                "- Bot UI: **not built**",
                "- Telegram = presentation layer only",
                "- All numbers come from Prediction Engine / API JSON",
                "",
                "## Commands → Engine",
                "",
                *[f"- `{k}` → `{v}`" for k, v in COMMAND_MAP.items()],
                "",
                "## Example card",
                "",
                "```",
                example_text or "(no sample)",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "status": "COMPLETE",
        "phase": 8,
        "telegram_implemented": False,
        "design_ready": True,
        "sample_race_id": sample_race_id,
        "output_dir": str(out),
    }
