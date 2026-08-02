from __future__ import annotations

from dataclasses import dataclass, field

from collectors.dedupe import review_content_hash, review_fingerprint
from models.review import Review


@dataclass
class ReviewDiff:
    new_reviews: list[Review] = field(default_factory=list)
    edited_reviews: list[Review] = field(default_factory=list)
    unchanged_reviews: list[Review] = field(default_factory=list)
    deleted_keys: list[str] = field(default_factory=list)
    deleted_review_ids: list[int] = field(default_factory=list)


def filter_incremental_reviews(
    reviews: list[Review],
    *,
    known_external_ids: set[str],
    known_fingerprints: set[str],
    fingerprint_fn=review_fingerprint,
    branch_key: str = "",
) -> tuple[list[Review], list[Review]]:
    """
    Backward-compatible split into new vs existing.

    Prefer `diff_reviews` for new/edited/deleted semantics.
    """
    diff = diff_reviews(
        reviews,
        known_external_ids=known_external_ids,
        known_fingerprints=known_fingerprints,
        known_content_hashes={},
        active_rows=[],
        fingerprint_fn=fingerprint_fn,
        branch_key=branch_key,
    )
    return diff.new_reviews, diff.edited_reviews + diff.unchanged_reviews


def diff_reviews(
    reviews: list[Review],
    *,
    known_external_ids: set[str],
    known_fingerprints: set[str],
    known_content_hashes: dict[str, str],
    active_rows: list[dict],
    fingerprint_fn=review_fingerprint,
    branch_key: str = "",
) -> ReviewDiff:
    """Detect new, edited, unchanged, and deleted reviews for one branch snapshot."""
    diff = ReviewDiff()
    seen_keys: set[str] = set()

    for review in reviews:
        if not review.content_hash:
            review.content_hash = review_content_hash(review)
        external = (review.external_id or "").strip()
        fp = fingerprint_fn(review, branch_key=branch_key)
        key = external or fp
        seen_keys.add(key)

        known = (bool(external) and external in known_external_ids) or (fp in known_fingerprints)
        if not known:
            diff.new_reviews.append(review)
            continue

        previous_hash = known_content_hashes.get(key, "")
        if previous_hash and previous_hash != review.content_hash:
            diff.edited_reviews.append(review)
        else:
            diff.unchanged_reviews.append(review)

    for row in active_rows:
        key = str(row.get("key") or "")
        if key and key not in seen_keys:
            diff.deleted_keys.append(key)
            diff.deleted_review_ids.append(int(row["id"]))

    return diff
