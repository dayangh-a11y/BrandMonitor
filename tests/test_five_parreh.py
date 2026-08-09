"""Unit tests for Five-Parreh Phase 1 combination engine."""

from __future__ import annotations

import pytest

from src.five_parreh import (
    FiveParrehValidationError,
    calculate_cost,
    generate_combinations,
)


def _races(counts: list[int], *, prefix: str = "R") -> list[dict]:
    races = []
    letter = ord("A")
    for i, n in enumerate(counts, start=1):
        horses = []
        for _ in range(n):
            horses.append(chr(letter))
            letter += 1
        races.append({"race_id": f"{prefix}{i}", "horses": horses})
    return races


def test_two_each_equals_32() -> None:
    result = generate_combinations({"races": _races([2, 2, 2, 2, 2])}, price_per_combination=1)
    assert result.summary.selections_per_race == (2, 2, 2, 2, 2)
    assert result.summary.total_combinations == 32
    assert len(result.combinations) == 32


def test_three_each_equals_243() -> None:
    result = generate_combinations(
        {"races": _races([3, 3, 3, 3, 3])},
        price_per_combination=10_000,
    )
    assert result.summary.race_count == 5
    assert result.summary.selections_per_race == (3, 3, 3, 3, 3)
    assert result.summary.total_combinations == 243
    assert len(result.combinations) == 243
    assert result.summary.total_cost == 2_430_000


def test_mixed_selection_counts() -> None:
    assert generate_combinations({"races": _races([2, 3, 2, 3, 2])}).summary.total_combinations == 72
    assert generate_combinations({"races": _races([1, 2, 3, 2, 1])}).summary.total_combinations == 12


def test_exactly_five_races_required() -> None:
    with pytest.raises(FiveParrehValidationError, match="Exactly 5 races"):
        generate_combinations({"races": _races([2, 2, 2, 2])})
    with pytest.raises(FiveParrehValidationError, match="Exactly 5 races"):
        generate_combinations({"races": _races([1, 1, 1, 1, 1, 1])})


def test_empty_race_rejected() -> None:
    races = _races([2, 2, 2, 2, 2])
    races[2]["horses"] = []
    with pytest.raises(FiveParrehValidationError, match="no selected horses"):
        generate_combinations({"races": races})


def test_duplicate_horse_within_race_rejected() -> None:
    races = _races([2, 2, 2, 2, 2])
    races[0]["horses"] = ["A", "A"]
    with pytest.raises(FiveParrehValidationError, match="duplicate horse_id"):
        generate_combinations({"races": races})


def test_invalid_horse_identifier() -> None:
    races = _races([1, 1, 1, 1, 1])
    races[0]["horses"] = [""]
    with pytest.raises(FiveParrehValidationError, match="Invalid horse identifier"):
        generate_combinations({"races": races})
    races[0]["horses"] = [{"horse_name": "only-name"}]
    with pytest.raises(FiveParrehValidationError, match="missing horse_id"):
        generate_combinations({"races": races})


def test_cost_calculation() -> None:
    assert calculate_cost(243, 10_000) == 2_430_000
    assert calculate_cost(32, 500) == 16_000
    with pytest.raises(FiveParrehValidationError):
        calculate_cost(10, -1)


def test_summary_without_price_leaves_cost_none() -> None:
    result = generate_combinations({"races": _races([2, 2, 2, 2, 2])})
    assert result.summary.price_per_combination is None
    assert result.summary.total_cost is None


def test_deterministic_ordering() -> None:
    races = [
        {"race_id": "R1", "horses": ["A", "B"]},
        {"race_id": "R2", "horses": ["C", "D"]},
        {"race_id": "R3", "horses": ["E"]},
        {"race_id": "R4", "horses": ["F"]},
        {"race_id": "R5", "horses": ["G", "H"]},
    ]
    a = generate_combinations({"races": races})
    b = generate_combinations({"races": races})
    assert [c.horse_ids() for c in a.combinations] == [c.horse_ids() for c in b.combinations]
    # product order: leftmost race varies slowest
    assert a.combinations[0].horse_ids() == ("A", "C", "E", "F", "G")
    assert a.combinations[1].horse_ids() == ("A", "C", "E", "F", "H")
    assert a.combinations[2].horse_ids() == ("A", "D", "E", "F", "G")
    assert a.combinations[-1].horse_ids() == ("B", "D", "E", "F", "H")
    assert len(a.combinations) == 8


def test_combination_has_five_slots() -> None:
    result = generate_combinations({"races": _races([1, 1, 1, 1, 1])})
    c = result.combinations[0]
    assert c.race_1.horse_id and c.race_5.horse_id
    d = result.to_dict()
    assert d["total_combinations"] == 1
    assert d["combinations"][0]["race_1"]["horse_id"]
