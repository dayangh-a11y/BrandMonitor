"""
Pre-Race Decision Engine — strongest pre-race intelligence for Iranian racing.

Not a historical stats website. Input = race card + history + weather + field.
Output = complete pre-race intelligence report with explainability + validation.
"""

from __future__ import annotations

from src.prerace.benchmark import (
    build_mashhad_week2_1000m_benchmark,
    load_benchmark,
    verify_benchmark_file,
)
from src.prerace.engine import build_prerace_report
from src.prerace.evaluation import evaluate_benchmark, evaluate_benchmark_file
from src.prerace.report import format_prerace_report

__all__ = [
    "build_mashhad_week2_1000m_benchmark",
    "build_prerace_report",
    "evaluate_benchmark",
    "evaluate_benchmark_file",
    "format_prerace_report",
    "load_benchmark",
    "verify_benchmark_file",
]

PLATFORM_VERSION = "1.0.0"
