"""Five-Parreh (پنج‌پره) — Phase 1 combination engine

## What it means

**Five-Parreh** is a multi-race ticket covering **exactly five consecutive races**.
The bettor selects one or more horses in each race. Every ticket line is one
horse from Race 1 × Race 2 × Race 3 × Race 4 × Race 5.

This phase builds the **full set of combinations** from those selections. It does
**not** predict winners, rank tickets, use scores, or compute probabilities.

## How combinations are generated

Given five race selections (order preserved):

```text
Race 1 = [A, B, C]
Race 2 = [D, E, F]
Race 3 = [G, H, I]
Race 4 = [J, K, L]
Race 5 = [M, N, O]
```

the engine forms the Cartesian product:

```text
3 × 3 × 3 × 3 × 3 = 243 combinations
```

Each combination contains exactly one horse from each race, e.g.
`(A, D, G, J, M)`, `(A, D, G, J, N)`, … through `(C, F, I, L, O)`.

Generation is **deterministic**: race order and within-race horse order are
preserved; `itertools.product` walks left-to-right.

## Cost calculation

Cost is purely arithmetic. The domain does **not** hardcode a stake.

```text
total_cost = total_combinations × price_per_combination
```

Example (caller uses تومان):

```text
243 × 10_000 = 2_430_000 تومان
```

## Selection count examples

| Selections per race | Total combinations |
|---------------------|--------------------|
| `[2,2,2,2,2]`       | 32                 |
| `[3,3,3,3,3]`       | 243                |
| `[2,3,2,3,2]`       | 72                 |
| `[1,2,3,2,1]`       | 12                 |

## Summary shape

```json
{
  "race_count": 5,
  "selections_per_race": [3, 3, 3, 3, 3],
  "total_combinations": 243,
  "price_per_combination": 10000,
  "total_cost": 2430000
}
```

## Python usage

```python
from src.five_parreh import generate_combinations

result = generate_combinations(
    {
        "races": [
            {"race_id": "R1", "horses": ["A", "B", "C"]},
            {"race_id": "R2", "horses": ["D", "E", "F"]},
            {"race_id": "R3", "horses": ["G", "H", "I"]},
            {"race_id": "R4", "horses": ["J", "K", "L"]},
            {"race_id": "R5", "horses": ["M", "N", "O"]},
        ]
    },
    price_per_combination=10_000,
)
print(result.summary.total_combinations)  # 243
print(result.summary.total_cost)          # 2430000
```

## Validation

- Exactly **5** races are required.
- No race may have an empty horse list.
- Duplicate `horse_id` values within the same race are rejected.
- Empty / missing horse identifiers are rejected with a clear error.

## Explicit non-goals (this phase)

- Does **not** predict or rank combinations
- Does **not** use score to eliminate combinations
- Does **not** fabricate or derive probabilities
- Does **not** integrate Telegram
- Does **not** change the freeze-backed prediction engine

## HTTP (optional)

`POST /five-parreh/combinations` — see OpenAPI `/docs`. Large combination
lists are omitted or rejected above a safe threshold; summary/cost still work.
