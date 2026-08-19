"""Format virtual race intelligence report."""

from __future__ import annotations

from typing import Any

from src.prerace.report import format_prerace_report


def format_virtual_race_report(payload: dict[str, Any]) -> str:
    text = format_prerace_report(payload)
    race = payload.get("race") or {}
    conf = payload.get("confidence") or {}
    risk = payload.get("risk") or {}
    header = [
        "══════════════════════════════════════",
        "VIRTUAL RACE INTELLIGENCE REPORT",
        "(hypothetical — no database race_id)",
        "══════════════════════════════════════",
        f"Resolved {race.get('resolved')}/{race.get('entered')} runners · "
        f"unresolved={race.get('unresolved')}",
        f"Field confidence: {conf.get('field_confidence')} "
        f"({conf.get('field_confidence_score')}) · "
        f"field risk={risk.get('field_risk_score')}",
        "",
    ]
    # Replace first banner block from prerace formatter
    if text.startswith("══"):
        rest = text.split("\n", 3)
        # drop first 3 lines of banner roughly — keep body after PRE-RACE header block
        lines = text.splitlines()
        # Find "── Race Context ──" and keep from race meta onward, but simpler: prepend
        body_start = 0
        for i, line in enumerate(lines):
            if line.startswith("Race:"):
                body_start = i
                break
        return "\n".join(header + lines[body_start:])
    return "\n".join(header) + text
