from __future__ import annotations

import hashlib
import re

from models.review import Review


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_review_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").strip().casefold())


def review_fingerprint(review: Review, *, branch_key: str = "") -> str:
    """Stable fingerprint for duplicate detection across rescrapes."""
    external = (review.external_id or "").strip()
    if external:
        base = f"ext::{branch_key}::{external}"
    else:
        base = "::".join(
            [
                "fallback",
                branch_key,
                (review.author or "").strip().casefold(),
                (review.published_at or "").strip().casefold(),
                normalize_review_text(review.text)[:240],
                str(review.rating),
            ]
        )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def is_duplicate_fingerprint(existing: set[str], fingerprint: str) -> bool:
    return fingerprint in existing


def branch_identity_key(*, place_id: str = "", name: str = "", address: str = "") -> str:
    if place_id.strip():
        return f"place::{place_id.strip()}"
    return f"name::{name.strip().casefold()}::{address.strip().casefold()}"
