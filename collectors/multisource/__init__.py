"""Multi-source package."""

from collectors.multisource.dedupe_cross import cross_source_dedupe
from collectors.multisource.nlp_platform import analyze_platform_review

__all__ = ["cross_source_dedupe", "analyze_platform_review"]
