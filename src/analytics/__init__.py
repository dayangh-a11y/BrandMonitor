"""
Analytics Layer — standardized performance metrics & ranking views.

Prefix: ``anl_*``
Reads: warehouse (+ weather features when present)
Never writes Raw.
"""

from src.analytics.build import build_analytics

__all__ = ["build_analytics"]
