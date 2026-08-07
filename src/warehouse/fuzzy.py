"""Fuzzy identity matching helpers (stdlib — no ML).

Persian-aware normalization lives in ``src.identity.normalize``.
This module re-exports helpers for backward compatibility with warehouse ER.
"""

from __future__ import annotations

from src.identity.normalize import name_similarity, normalize_name

similarity = name_similarity


def find_duplicate_pairs(
    names: list[str],
    *,
    threshold: float = 0.92,
) -> list[tuple[str, str, float]]:
    """Return duplicate candidate pairs (normalized-equal + fuzzy)."""
    originals: dict[str, list[str]] = {}
    for raw in names:
        key = normalize_name(raw)
        if not key:
            continue
        originals.setdefault(key, [])
        cleaned = raw.strip()
        if cleaned not in originals[key]:
            originals[key].append(cleaned)

    pairs: list[tuple[str, str, float]] = []
    for group in originals.values():
        if len(group) < 2:
            continue
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                pairs.append((left, right, 1.0))

    cleaned_keys = sorted(originals.keys())
    for i, left in enumerate(cleaned_keys):
        for right in cleaned_keys[i + 1 :]:
            score = similarity(left, right)
            if score >= threshold:
                pairs.append((originals[left][0], originals[right][0], score))
    return pairs
