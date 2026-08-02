from __future__ import annotations

from models.review import Review


def filter_incremental_reviews(
    reviews: list[Review],
    *,
    known_external_ids: set[str],
    known_fingerprints: set[str],
    fingerprint_fn,
    branch_key: str = "",
) -> tuple[list[Review], list[Review]]:
    """
    Split reviews into new vs existing.

    - new_reviews: not seen before (insert path)
    - existing_reviews: already known (update path)
    """
    new_reviews: list[Review] = []
    existing_reviews: list[Review] = []

    for review in reviews:
        external = (review.external_id or "").strip()
        fp = fingerprint_fn(review, branch_key=branch_key)
        if external and external in known_external_ids:
            existing_reviews.append(review)
            continue
        if fp in known_fingerprints:
            existing_reviews.append(review)
            continue
        new_reviews.append(review)

    return new_reviews, existing_reviews
