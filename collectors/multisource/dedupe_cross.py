"""Cross-source duplicate detection and merge."""

from __future__ import annotations

from difflib import SequenceMatcher

from collectors.normalize.text import normalize_persian
from collectors.providers.base import UnifiedReview


def _sim(a: str, b: str) -> float:
    na, nb = normalize_persian(a).casefold(), normalize_persian(b).casefold()
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def cross_source_dedupe(
    rows: list[UnifiedReview],
    *,
    text_threshold: float = 0.90,
) -> tuple[list[UnifiedReview], int]:
    """
    Merge duplicates across sources when text/rating/date/branch/reviewer align.

    Keeps the richest record and records alternate sources in metadata['also_seen_on'].
    """
    buckets: dict[str, list[UnifiedReview]] = {}
    for r in rows:
        key = f"{normalize_persian(r.brand).casefold()}|{normalize_persian(r.branch).casefold()}|{normalize_persian(r.city).casefold()}"
        buckets.setdefault(key, []).append(r)

    kept: list[UnifiedReview] = []
    dropped = 0
    for group in buckets.values():
        accepted: list[UnifiedReview] = []
        ranked = sorted(
            group,
            key=lambda r: (
                -len(normalize_persian(r.review)),
                -len(r.reply or ""),
                0 if r.latitude is not None else 1,
                r.source,
            ),
        )
        for row in ranked:
            dup_of = None
            for prev in accepted:
                same_rating = (
                    row.rating is not None
                    and prev.rating is not None
                    and abs(float(row.rating) - float(prev.rating)) < 0.15
                )
                same_date = bool(row.review_date) and row.review_date[:10] == (prev.review_date or "")[:10]
                same_reviewer = bool(row.reviewer) and normalize_persian(row.reviewer).casefold() == normalize_persian(
                    prev.reviewer
                ).casefold()
                text_close = _sim(row.review, prev.review) >= text_threshold
                # Require strong text match plus at least one supporting signal
                if text_close and (same_rating or same_date or same_reviewer or not row.reviewer):
                    dup_of = prev
                    break
            if dup_of is not None:
                dropped += 1
                seen = list(dup_of.metadata.get("also_seen_on") or [])
                if row.source not in seen and row.source != dup_of.source:
                    seen.append(row.source)
                dup_of.metadata["also_seen_on"] = seen
                # Prefer filling missing fields from duplicate
                if not dup_of.reply and row.reply:
                    dup_of.reply = row.reply
                    dup_of.reply_date = row.reply_date
                if dup_of.photos_count is None and row.photos_count is not None:
                    dup_of.photos_count = row.photos_count
                if not dup_of.url and row.url:
                    dup_of.url = row.url
                continue
            accepted.append(row)
        kept.extend(accepted)
    return kept, dropped
