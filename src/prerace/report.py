"""Human-readable pre-race intelligence report."""

from __future__ import annotations

from typing import Any


def format_prerace_report(payload: dict[str, Any]) -> str:
    race = payload.get("race") or {}
    ctx = payload.get("race_context") or {}
    reports = payload.get("reports") or {}
    horses = payload.get("horses") or []
    validation = payload.get("validation") or []
    lines = [
        "══════════════════════════════════════",
        "PRE-RACE INTELLIGENCE REPORT",
        "══════════════════════════════════════",
        f"Race: {race.get('race_name') or '—'}  (id={race.get('race_id')})",
        f"Date/Track: {race.get('race_date')} · {race.get('racecourse_code')}",
        f"Distance/Class: {race.get('distance')} · {race.get('class_code')}",
        f"Field size: {race.get('field_size')}",
        f"Status: {payload.get('status')} · publishable={payload.get('publishable')}",
        "",
        "── Race Context ──",
        f"Race Strength:      {ctx.get('race_strength')}",
        f"Field Strength:     {ctx.get('field_strength')}",
        f"Competition Level:  {ctx.get('competition_level')}",
        f"Weather Impact:     {ctx.get('weather_impact')}",
        f"Track Suitability:  {ctx.get('track_suitability')}",
        f"Expected Pace:      {ctx.get('expected_pace')}",
        f"Race Shape:         {ctx.get('race_shape')}",
    ]
    expl = (ctx.get("explanation") or {})
    if expl.get("why"):
        lines.append(f"Why: {expl['why']}")
    lines += ["", "── Recommendations ──"]
    for key in (
        "best_win_candidate",
        "best_place_candidate",
        "best_head_to_head_candidate",
        "best_value_horse",
        "most_underrated_horse",
        "most_overrated_horse",
        "dark_horse",
        "high_risk_horse",
        "most_reliable_horse",
        "most_improved_horse",
        "best_long_shot",
    ):
        item = reports.get(key)
        if not item:
            lines.append(f"{key}: —")
            continue
        lines.append(
            f"{item.get('label')}: {item.get('horse')} "
            f"(chance={item.get('todays_chance_score')}, "
            f"p_win={item.get('winning_probability')}, "
            f"conf={item.get('confidence')}, n={item.get('sample_size')}, "
            f"dq={item.get('data_quality')})"
        )
        if item.get("why"):
            lines.append(f"  Why: {item['why']}")

    lines += ["", "── Field (by Today's Chance) ──"]
    for h in horses[:12]:
        lines.append(
            f"  {h.get('expected_finish_position'):>4} {h.get('horse')} "
            f"chance={h.get('todays_chance_score')} "
            f"p_win={h.get('winning_probability')} "
            f"p_top3={h.get('top3_probability')} "
            f"risk={h.get('risk_score')} conf={h.get('confidence')}"
        )

    if validation:
        lines += ["", "── Validation Warnings ──"]
        for v in validation[:30]:
            lines.append(f"  [{v.get('severity')}] {v.get('code')}: {v.get('message')}")
    else:
        lines += ["", "── Validation ──", "  No issues detected"]

    lines.append("══════════════════════════════════════")
    return "\n".join(lines)
