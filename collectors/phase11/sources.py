"""Pluggable Phase 11 source adapters (stubs for non-Maps sources)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    display_name: str
    implemented: bool
    notes: str


PHASE11_SOURCES: list[SourceSpec] = [
    SourceSpec(
        "google_maps",
        "Google Maps Reviews",
        True,
        "Primary collector via collectors.google_maps",
    ),
    SourceSpec(
        "balad",
        "بلد",
        False,
        "Adapter stub — not implemented in Phase 11; reserved review_source=balad",
    ),
    SourceSpec(
        "neshan",
        "نشان",
        False,
        "Adapter stub — not implemented in Phase 11; reserved review_source=neshan",
    ),
    SourceSpec(
        "official_branch_page",
        "صفحه رسمی شعبه",
        False,
        "Reserved for official site parsers when URLs are curated",
    ),
    SourceSpec(
        "public_complaint",
        "وب‌سایت ثبت شکایت عمومی",
        False,
        "Reserved for public complaint portals",
    ),
    SourceSpec(
        "news",
        "خبرهای معتبر",
        False,
        "Reserved for cited news items about brands/branches",
    ),
]


def list_sources() -> list[dict]:
    return [
        {
            "source_id": s.source_id,
            "display_name": s.display_name,
            "implemented": s.implemented,
            "notes": s.notes,
        }
        for s in PHASE11_SOURCES
    ]
