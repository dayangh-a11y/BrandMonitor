from __future__ import annotations

import hashlib
import re

from models.review import Review


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_review_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").strip().casefold())


def review_content_hash(review: Review) -> str:
    """Hash of mutable review content (detect edits)."""
    payload = "::".join(
        [
            normalize_review_text(review.text),
            str(float(review.rating or 0)),
            (review.published_at or "").strip().casefold(),
            (review.owner_response or "").strip().casefold(),
            (review.owner_response_at or "").strip().casefold(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def review_fingerprint(
    review: Review,
    *,
    branch_key: str = "",
    strategy: str = "auto",
) -> str:
    """
    Stable identity fingerprint for duplicate detection.

    Strategies:
    - external_id: prefer provider review id
    - author_date_text: author + date + text prefix + rating
    - content: content hash only (weaker identity)
    - auto: external_id if present else author_date_text
    """
    external = (review.external_id or "").strip()
    if strategy in {"auto", "external_id"} and external:
        base = f"ext::{branch_key}::{external}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    if strategy == "content":
        base = f"content::{branch_key}::{review_content_hash(review)}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    # author_date_text / auto fallback
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


def review_fingerprints_multi(review: Review, *, branch_key: str = "") -> dict[str, str]:
    """Compute multiple fingerprint strategies for one review."""
    return {
        "external_id": review_fingerprint(review, branch_key=branch_key, strategy="external_id"),
        "author_date_text": review_fingerprint(
            review, branch_key=branch_key, strategy="author_date_text"
        ),
        "content": review_fingerprint(review, branch_key=branch_key, strategy="content"),
        "auto": review_fingerprint(review, branch_key=branch_key, strategy="auto"),
    }


def is_duplicate_fingerprint(existing: set[str], fingerprint: str) -> bool:
    return fingerprint in existing


def branch_identity_key(*, place_id: str = "", name: str = "", address: str = "") -> str:
    if place_id.strip():
        return f"place::{place_id.strip()}"
    return f"name::{name.strip().casefold()}::{address.strip().casefold()}"
