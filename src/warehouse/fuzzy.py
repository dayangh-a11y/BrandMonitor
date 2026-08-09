"""Fuzzy identity matching helpers (stdlib — no ML).

Persian-aware normalization lives in ``src.identity.normalize``.
This module re-exports helpers for backward compatibility with warehouse ER.
"""

from __future__ import annotations

from collections import defaultdict

from src.identity.normalize import name_similarity, normalize_name

similarity = name_similarity


def find_duplicate_pairs(
    names: list[str],
    *,
    threshold: float = 0.92,
) -> list[tuple[str, str, float]]:
    """
    Return duplicate candidate pairs (normalized-equal + fuzzy).

    Fuzzy comparisons are blocked by the first two normalized characters so
    nationwide catalogs (thousands of owners/horses) stay tractable. Exact
    normalized collisions are always emitted.
    """
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

    # Prefix blocking — avoid O(n²) over the full nationwide catalog.
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for key in originals:
        prefix = key[:2] if len(key) >= 2 else key
        by_prefix[prefix].append(key)

    seen: set[tuple[str, str]] = set()
    for keys in by_prefix.values():
        keys_sorted = sorted(keys)
        for i, left in enumerate(keys_sorted):
            for right in keys_sorted[i + 1 :]:
                pair = (left, right) if left < right else (right, left)
                if pair in seen:
                    continue
                seen.add(pair)
                score = similarity(left, right)
                if score >= threshold:
                    pairs.append((originals[left][0], originals[right][0], score))
    return pairs
