"""Dynamic field discovery — no hardcoded source field names."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.prediction_market.client import MosharekatClient


def walk_fields(
    obj: Any,
    prefix: str = "",
    *,
    acc: dict[str, set[str]] | None = None,
    samples: dict[str, Any] | None = None,
    max_list_items: int = 6,
) -> tuple[dict[str, set[str]], dict[str, Any]]:
    """Recursively inventory every JSON path and observed types."""
    if acc is None:
        acc = defaultdict(set)
    if samples is None:
        samples = {}

    if isinstance(obj, dict):
        acc[prefix or "$"].add("object")
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if path not in samples:
                if isinstance(value, (str, int, float, bool)) or value is None:
                    samples[path] = value
                elif isinstance(value, list):
                    samples[path] = f"list[{len(value)}]"
                else:
                    samples[path] = "object"
            walk_fields(
                value, path, acc=acc, samples=samples, max_list_items=max_list_items
            )
    elif isinstance(obj, list):
        acc[prefix or "$"].add("array")
        for item in obj[:max_list_items]:
            walk_fields(
                item,
                f"{prefix}[]",
                acc=acc,
                samples=samples,
                max_list_items=max_list_items,
            )
    else:
        acc[prefix or "$"].add(type(obj).__name__)
    return acc, samples


def inventory_to_rows(
    acc: dict[str, set[str]], samples: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path, types in sorted(acc.items()):
        rows.append(
            {
                "path": path,
                "types": sorted(types),
                "sample": samples.get(path),
            }
        )
    return rows


def discover_prediction_fields(
    *,
    client: MosharekatClient | None = None,
    day_sample: int = 3,
    race_sample: int = 3,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    """
    Hit public mosharekat endpoints and emit a field inventory report.

    Field names are discovered from payloads — not declared in code.
    """
    client = client or MosharekatClient()
    out = Path(output_dir) if output_dir else Path("docs/prediction_market")
    out.mkdir(parents=True, exist_ok=True)

    acc: dict[str, set[str]] = defaultdict(set)
    samples: dict[str, Any] = {}
    endpoints: list[dict[str, Any]] = []

    days_payload = {"success": True, "data": {"race_days": client.list_race_days()}}
    walk_fields(days_payload, "days", acc=acc, samples=samples)
    endpoints.append(
        {
            "method": "GET",
            "path": "/api/v1/races/days?limit=500",
            "auth": False,
            "records": len(days_payload["data"]["race_days"]),
        }
    )

    days = days_payload["data"]["race_days"]
    (out / "available_race_days.json").write_text(
        json.dumps(days, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    races_seen = 0
    for day in days[: max(1, day_sample)]:
        day_id = day.get("id")
        if day_id is None:
            continue
        card = client.fetch_racecard(day_id)
        walk_fields(card, "racecard", acc=acc, samples=samples)
        endpoints.append(
            {
                "method": "GET",
                "path": f"/api/v1/races/racecard?day_id={day_id}",
                "auth": False,
                "day_id": day_id,
            }
        )
        data = card.get("data") if isinstance(card, dict) else None
        races = []
        if isinstance(data, dict) and isinstance(data.get("races"), list):
            races = [r for r in data["races"] if isinstance(r, dict)]
        for race in races[: max(1, race_sample)]:
            rid = race.get("id")
            if rid is None:
                continue
            odds = client.fetch_odds(rid)
            walk_fields(odds, "odds", acc=acc, samples=samples)
            endpoints.append(
                {
                    "method": "GET",
                    "path": f"/api/v1/pools/race/{rid}/odds",
                    "auth": False,
                    "race_id": rid,
                }
            )
            survey = client.fetch_survey_statistics(rid)
            walk_fields(survey, "survey", acc=acc, samples=samples)
            endpoints.append(
                {
                    "method": "GET",
                    "path": f"/api/v1/races/{rid}/survey-statistics",
                    "auth": False,
                    "race_id": rid,
                }
            )
            races_seen += 1

    rows = inventory_to_rows(acc, samples)
    (out / "discovered_fields.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # Auth-gated surfaces found in SPA (documented, not fetched)
    auth_endpoints = [
        {"method": "GET", "path": "/api/v1/bets", "auth": True},
        {"method": "GET", "path": "/api/v1/bets/summary", "auth": True},
        {"method": "GET", "path": "/api/v1/wallet", "auth": True},
        {"method": "GET", "path": "/api/v1/payments", "auth": True},
        {"method": "GET", "path": "/api/v1/pools", "auth": True},
        {"method": "GET", "path": "/api/v1/admin/racecard/:id/survey", "auth": True},
        {"method": "GET", "path": "/api/v1/admin/racecard/:id/pick-chart", "auth": True},
        {"method": "GET", "path": "/api/v1/admin/pools/:id/pick-statistics", "auth": True},
        {"method": "GET", "path": "/api/v1/admin/pools/bet-results", "auth": True},
    ]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "web": "https://mosharekat.asbdavani.app",
            "api": "https://api-mosharekat.asbdavani.app/api/v1",
            "legacy": "https://my.asbdavani.org",
            "main_site": "https://asbdavani.app",
        },
        "public_endpoints_sampled": endpoints,
        "auth_required_endpoints_from_spa": auth_endpoints,
        "race_days_available": len(days),
        "races_sampled": races_seen,
        "field_count": len(rows),
        "fields": rows,
        "notes": [
            "Individual PredictionEntries (user bets) require authentication; "
            "public history exposes market odds, survey vote counts, pools, and winners.",
            "Field names are discovered from live JSON — regenerating this report "
            "updates the inventory when the API schema changes.",
            "Pool types observed in payloads include WIN_1ST, WIN_2ND, WIN_3RD, "
            "QUINELLA, PICK_3/5/6, SURVEY (discovered, not hardcoded in collectors).",
        ],
    }
    (out / "discovery_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # Human-readable markdown
    lines = [
        "# Prediction Market Field Discovery",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Sources",
        "",
        f"- Web: `{report['source']['web']}`",
        f"- API: `{report['source']['api']}`",
        f"- Legacy: `{report['source']['legacy']}`",
        "",
        f"**Race days available (public):** {len(days)}",
        f"**Fields discovered:** {len(rows)}",
        "",
        "## Public endpoints",
        "",
        "| Method | Path | Auth |",
        "|--------|------|------|",
        "| GET | `/api/v1/races/days?limit=500` | no |",
        "| GET | `/api/v1/races/racecard?day_id=` | no |",
        "| GET | `/api/v1/pools/race/{race_id}/odds` | no |",
        "| GET | `/api/v1/races/{race_id}/survey-statistics` | no |",
        "| GET | `/api/v1/system/notice` | no |",
        "",
        "## Auth-required (SPA)",
        "",
    ]
    for ep in auth_endpoints:
        lines.append(f"- `{ep['path']}`")
    lines += [
        "",
        "## Discovered fields",
        "",
        "Full machine-readable inventory: [`discovered_fields.json`](discovered_fields.json).",
        "",
        "| Path | Types | Sample |",
        "|------|-------|--------|",
    ]
    for row in rows[:400]:
        sample = json.dumps(row["sample"], ensure_ascii=False, default=str)
        if len(sample) > 80:
            sample = sample[:77] + "..."
        types = ",".join(row["types"])
        lines.append(f"| `{row['path']}` | {types} | {sample} |")
    if len(rows) > 400:
        lines.append(f"| … | {len(rows) - 400} more | see JSON |")
    (out / "DISCOVERY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
