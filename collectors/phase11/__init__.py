"""Phase 11 package."""

from collectors.phase11.dedupe_similarity import dedupe_reviews, text_similarity
from collectors.phase11.nlp import analyze_review

__all__ = ["analyze_review", "dedupe_reviews", "text_similarity"]
