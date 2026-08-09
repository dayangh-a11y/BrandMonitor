"""Telegram bot thin client over the Prediction / Five-Parreh HTTP API.

Contains no scoring, rank_race, ML, pedigree, or combination-generation logic.
"""

from __future__ import annotations

__all__ = ["main"]


def main() -> None:
    from src.telegram_bot.bot import main as _main

    _main()
