"""Five-Parreh combination generation and cost (Phase 1).

Phase 1 only: selection → Cartesian product → count → cost.
No ranking, scoring, probability, or optimization.
"""

from __future__ import annotations

import itertools
from typing import Any, Iterable, Mapping, Sequence

from src.five_parreh.errors import FiveParrehValidationError
from src.five_parreh.models import (
    Combination,
    CombinationSummary,
    FiveParrehResult,
    RaceSelection,
)
from src.five_parreh.validation import REQUIRED_RACE_COUNT, normalize_selections


def calculate_cost(
    total_combinations: int,
    price_per_combination: int | float,
) -> int | float:
    """Return ``total_combinations * price_per_combination``.

    ``price_per_combination`` is caller-supplied (e.g. تومان). The domain does
    **not** hardcode a betting stake.
    """
    if total_combinations < 0:
        raise FiveParrehValidationError("total_combinations must be >= 0")
    if isinstance(price_per_combination, bool) or not isinstance(
        price_per_combination, (int, float)
    ):
        raise FiveParrehValidationError("price_per_combination must be a number")
    if price_per_combination < 0:
        raise FiveParrehValidationError("price_per_combination must be >= 0")
    product = total_combinations * price_per_combination
    # Prefer int when exact.
    if isinstance(product, float) and product.is_integer():
        return int(product)
    if isinstance(price_per_combination, int):
        return int(product)
    return product


def build_summary(
    selections: Sequence[RaceSelection],
    *,
    price_per_combination: int | float | None = None,
) -> CombinationSummary:
    """Build count/cost summary without enumerating combinations."""
    if len(selections) != REQUIRED_RACE_COUNT:
        raise FiveParrehValidationError(
            f"Exactly {REQUIRED_RACE_COUNT} races required, got {len(selections)}"
        )
    counts = tuple(len(r.horses) for r in selections)
    total = 1
    for n in counts:
        if n <= 0:
            raise FiveParrehValidationError("Empty race is not allowed")
        total *= n

    total_cost: int | float | None = None
    if price_per_combination is not None:
        total_cost = calculate_cost(total, price_per_combination)

    return CombinationSummary(
        race_count=REQUIRED_RACE_COUNT,
        selections_per_race=counts,
        total_combinations=total,
        price_per_combination=price_per_combination,
        total_cost=total_cost,
        race_ids=tuple(r.race_id for r in selections),
    )


def generate_combinations(
    selections: Iterable[Any] | Mapping[str, Any] | Sequence[RaceSelection],
    *,
    price_per_combination: int | float | None = None,
    include_combinations: bool = True,
) -> FiveParrehResult:
    """Generate the Cartesian product of horse picks across exactly five races.

    Order is deterministic: races stay in input order; within each race, horse
    order is preserved; ``itertools.product`` walks left-to-right.

    Does **not** rank, score, filter, or assign probabilities.
    """
    races = normalize_selections(selections)
    summary = build_summary(races, price_per_combination=price_per_combination)

    combos: tuple[Combination, ...]
    if include_combinations:
        product = itertools.product(*(r.horses for r in races))
        built: list[Combination] = []
        for idx, picks in enumerate(product):
            built.append(
                Combination(
                    race_1=picks[0],
                    race_2=picks[1],
                    race_3=picks[2],
                    race_4=picks[3],
                    race_5=picks[4],
                    index=idx,
                )
            )
        combos = tuple(built)
        if len(combos) != summary.total_combinations:
            # Defensive — should never happen.
            raise RuntimeError("Combination count mismatch")
    else:
        combos = ()

    return FiveParrehResult(summary=summary, combinations=combos, selections=races)
