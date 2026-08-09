"""
Market-Specific Analytics Engine.

Never reuse one ranking model across betting markets.
Each market has its own scoring model and answer payload.
"""

from __future__ import annotations

from src.markets.answer import MarketAnswer, format_market_answer
from src.markets.constants import MARKET_TYPES, PLATFORM_VERSION

__all__ = [
    "MARKET_TYPES",
    "PLATFORM_VERSION",
    "MarketAnswer",
    "format_market_answer",
]
