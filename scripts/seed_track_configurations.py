#!/usr/bin/env python3
"""Seed Track Configuration reference table and emit the display table.

Does not overwrite historical race/result data.
Does not run horse performance / ranking / enrichment analysis.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.racecourses.schema import list_track_configurations, seed_track_configurations
from src.racecourses.track_config import (
    SOURCE_NOTE,
    configuration_table_rows,
    resolve_track_configuration,
)

ART = Path("/opt/cursor/artifacts")


def main() -> int:
    db = ROOT / "output" / "historical" / "horse_racing.db"
    engine = create_engine(f"sqlite:///{db}")
    with Session(engine) as session:
        seed = seed_track_configurations(session)
        rows_db = list_track_configurations(session)
        db_rows = [
            {
                "track_id": row.track_id,
                "track_name": row.track_name,
                "city": row.city,
                "straight_length_m": row.straight_length_m,
                "straight_length_category": row.straight_length_category,
                "source": row.source,
                "source_url": row.source_url,
                "source_confidence": row.source_confidence,
            }
            for row in rows_db
        ]
        session.commit()

    display = configuration_table_rows()
    ART.mkdir(parents=True, exist_ok=True)

    # Markdown table
    md = [
        "# Track Configuration Table",
        "",
        SOURCE_NOTE,
        "",
        "> `straight_length_m` = home straight from final turn → finish. "
        "**Not** race distance. **Not** total track length.",
        "",
        "| میدان | شهر | Straight Length | دسته | Source | Confidence |",
        "|---|---|---:|---|---|---:|",
    ]
    for r in display:
        md.append(
            f"| {r['میدان']} | {r['شهر']} | {r['Straight Length']} | "
            f"{r['دسته']} | {r['Source']} | {r['Confidence']} |"
        )
    md += [
        "",
        "## Match rules",
        "",
        "- Apply only when race `racecourse_code` / track / city confidently maps to `track_id`.",
        "- Ambiguous names → do not apply Track Configuration (no guessing).",
        "- Conflicting new sources are reported; prior values are not overwritten without confirmation.",
        "",
        "## Feature Set columns",
        "",
        "- `straight_length_m`",
        "- `straight_length_category` — Short (<200), Medium (200–275), Long (≥276)",
        "",
        "## Track Context (Performance Score)",
        "",
        "Race Distance, Straight Length, Track/City, Breed, Horse Age, Weight, "
        "Starting Gate, Finish Position, Finish Time, Number of Runners.",
    ]
    md_path = ART / "track_configuration_table.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    csv_path = ART / "track_configuration_table.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "track_id",
                "track_name",
                "city",
                "straight_length_m",
                "straight_length_category",
                "source",
                "source_url",
                "source_confidence",
            ],
        )
        w.writeheader()
        for row in db_rows:
            w.writerow(row)

    # Sanity: WH city labels resolve
    match_checks = {
        label: (resolve_track_configuration(track_name=label) or resolve_track_configuration(city=label))
        for label in [
            "مشهد",
            "آق قلا",
            "تهران",
            "کیش",
            "گنبدکاووس",
            "بندرترکمن",
            "اهواز",
            "یزد",
            "ثامن مشهد",
            "نوروزآباد تهران",
            "انبارآلوم",  # no config → None
            "شهر فرضی",
        ]
    }
    match_summary = {
        k: (v.track_id if v else None, v.straight_length_m if v else None) for k, v in match_checks.items()
    }

    summary = {
        "seed": seed,
        "rows": len(db_rows),
        "display": display,
        "match_checks": match_summary,
        "artifacts": {
            "markdown": str(md_path),
            "csv": str(csv_path),
        },
        "rules": {
            "not_race_distance": True,
            "not_total_track_length": True,
            "no_guess_on_ambiguous": True,
            "no_overwrite_history": True,
            "conflict_requires_confirmation": True,
        },
    }
    summary_path = ART / "track_configuration_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
