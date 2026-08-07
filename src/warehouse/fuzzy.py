"""Fuzzy identity matching helpers (stdlib — no ML)."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[\"'`]", "", text)
    return text


def similarity(a: str | None, b: str | None) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def find_duplicate_pairs(
    names: list[str],
    *,
    threshold: float = 0.92,
) -> list[tuple[str, str, float]]:
    """Return duplicate candidate pairs (exact-normalized + fuzzy)."""
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
    # Exact after normalization (different original strings → same key)
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
