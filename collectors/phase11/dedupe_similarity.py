"""Near-duplicate review detection (keep one if text similarity > threshold)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher


_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    t = (text or "").strip().casefold()
    t = _WS.sub(" ", t)
    return t


def text_similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Fast reject
    if abs(len(na) - len(nb)) / max(len(na), len(nb)) > 0.5:
        # still compute — short texts may differ in length ratio
        pass
    return SequenceMatcher(None, na, nb).ratio()


def dedupe_reviews(
    rows: list[dict],
    *,
    text_key: str = "review_text",
    threshold: float = 0.90,
) -> tuple[list[dict], int]:
    """
    Drop near-duplicates within same brand+branch when similarity > threshold.
    Keeps the first (prefer longer text / higher confidence if present).
    """
    kept: list[dict] = []
    dropped = 0
    # Bucket by brand+branch to limit O(n^2)
    buckets: dict[str, list[dict]] = {}
    order: list[dict] = []
    for row in rows:
        key = f"{row.get('brand','')}|{row.get('branch_name','')}"
        buckets.setdefault(key, []).append(row)
        order.append(row)

    survivors: set[int] = set()
    for key, group in buckets.items():
        # Prefer richer rows first
        ranked = sorted(
            group,
            key=lambda r: (
                -len(normalize_text(r.get(text_key) or "")),
                -float(r.get("confidence_score") or 0),
                r.get("review_id") or "",
            ),
        )
        accepted: list[dict] = []
        for row in ranked:
            text = row.get(text_key) or ""
            dup = False
            for prev in accepted:
                if text_similarity(text, prev.get(text_key) or "") >= threshold:
                    dup = True
                    break
            if dup:
                dropped += 1
                continue
            accepted.append(row)
            survivors.add(id(row))

    for row in order:
        if id(row) in survivors:
            kept.append(row)
    return kept, dropped
