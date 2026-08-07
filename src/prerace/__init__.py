"""
Pre-Race Decision Engine — strongest pre-race intelligence for Iranian racing.

Not a historical stats website. Input = race card + history + weather + field.
Output = complete pre-race intelligence report with explainability + validation.
"""

from __future__ import annotations

from src.prerace.engine import build_prerace_report
from src.prerace.report import format_prerace_report

__all__ = ["build_prerace_report", "format_prerace_report"]

PLATFORM_VERSION = "1.0.0"
