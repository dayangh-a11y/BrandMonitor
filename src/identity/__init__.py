"""
Horse Identity Resolution Engine.

Never rely on exact string matching.
Every horse gets one permanent horse_id; future lookups use horse_id.
"""

from __future__ import annotations

from src.identity.build import build_horse_identity
from src.identity.normalize import normalize_name, normalize_persian_text, name_similarity
from src.identity.profile import HorseQuery
from src.identity.report import duplicate_merge_report, format_duplicate_report
from src.identity.resolve import (
    get_horse,
    horse_id_for_warehouse,
    resolve_horse,
    resolve_horse_id,
    warehouse_ids_for_horse,
)

__all__ = [
    "HorseQuery",
    "build_horse_identity",
    "duplicate_merge_report",
    "format_duplicate_report",
    "get_horse",
    "horse_id_for_warehouse",
    "name_similarity",
    "normalize_name",
    "normalize_persian_text",
    "resolve_horse",
    "resolve_horse_id",
    "warehouse_ids_for_horse",
]

PLATFORM_VERSION = "1.0.0"
