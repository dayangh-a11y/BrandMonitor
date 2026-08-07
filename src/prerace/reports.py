"""Pre-race recommendation reports — each with explainability."""

from __future__ import annotations

from typing import Any

from src.markets.scoring import RunnerContext
from src.markets.value import value_score
from src.prerace.types import HorseTodayScore


def _pick(horses: list[HorseTodayScore], key, reverse: bool = True) -> HorseTodayScore | None:
    pool = [h for h in horses if key(h) is not None]
    if not pool:
        return None
    return sorted(pool, key=key, reverse=reverse)[0]


def generate_reports(
    horses: list[HorseTodayScore],
    field: list[RunnerContext],
) -> dict[str, Any]:
    by_id = {r.horse_id: r for r in field}

    best_win = _pick(horses, lambda h: h.winning_probability)
    best_place = _pick(horses, lambda h: h.top3_probability)
    most_reliable = _pick(horses, lambda h: h.reliability)
    high_risk = _pick(horses, lambda h: h.risk_score)
    most_improved = _pick(horses, lambda h: h.momentum if h.momentum is not None else None)

    # Value / under / over from public perception vs chance
    value_rows = []
    for h in horses:
        r = by_id.get(h.horse_id)
        if r is None:
            continue
        vs, detail = value_score(r, field)
        value_rows.append((h, vs, detail))
    with_val = [(h, vs, d) for h, vs, d in value_rows if vs is not None]
    best_value = max(with_val, key=lambda t: t[1]) if with_val else None
    most_underrated = best_value
    most_overrated = min(with_val, key=lambda t: t[1]) if with_val else None

    # Dark horse: solid chance, low perception
    dark = None
    dark_score = None
    for h, vs, d in with_val:
        perc = d.get("perception")
        if perc is not None and perc < 45 and h.todays_chance_score >= 45:
            score = h.todays_chance_score - perc
            if dark is None or score > (dark_score or -999):
                dark, dark_score = h, score

    # Best H2H candidate: highest average ahead-prob across rivals
    def avg_h2h(h: HorseTodayScore) -> float | None:
        if not h.h2h_probs:
            return None
        return sum(h.h2h_probs.values()) / len(h.h2h_probs)

    best_h2h = _pick(horses, avg_h2h)

    # Long shot: low perception / high odds proxy but non-trivial chance
    long_shot = None
    for h, vs, d in with_val:
        perc = d.get("perception")
        if perc is not None and perc <= 35 and h.winning_probability >= 0.05:
            if long_shot is None or h.todays_chance_score > long_shot.todays_chance_score:
                long_shot = h

    def pack(h: HorseTodayScore | None, label: str, extra: dict | None = None) -> dict[str, Any] | None:
        if h is None:
            return None
        return {
            "label": label,
            "horse": h.horse_name,
            "horse_id": h.horse_id,
            "todays_chance_score": h.todays_chance_score,
            "winning_probability": h.winning_probability,
            "top3_probability": h.top3_probability,
            "confidence": h.confidence,
            "confidence_score": h.confidence_score,
            "sample_size": h.sample_size,
            "data_quality": h.data_quality,
            "why": h.explain.why if h.explain else None,
            "metrics_contributed": (
                [c.to_dict() for c in h.explain.contributions[:8]] if h.explain else []
            ),
            "extra": extra or {},
        }

    return {
        "best_win_candidate": pack(best_win, "Best Win Candidate"),
        "best_place_candidate": pack(best_place, "Best Place Candidate"),
        "best_head_to_head_candidate": pack(best_h2h, "Best Head-to-Head Candidate"),
        "best_value_horse": pack(
            best_value[0] if best_value else None,
            "Best Value Horse",
            {"value_score": best_value[1] if best_value else None},
        ),
        "most_underrated_horse": pack(
            most_underrated[0] if most_underrated else None,
            "Most Underrated Horse",
            {"value_score": most_underrated[1] if most_underrated else None},
        ),
        "most_overrated_horse": pack(
            most_overrated[0] if most_overrated else None,
            "Most Overrated Horse",
            {"value_score": most_overrated[1] if most_overrated else None},
        ),
        "dark_horse": pack(dark, "Dark Horse", {"dark_score": dark_score}),
        "high_risk_horse": pack(high_risk, "High Risk Horse"),
        "most_reliable_horse": pack(most_reliable, "Most Reliable Horse"),
        "most_improved_horse": pack(most_improved, "Most Improved Horse"),
        "best_long_shot": pack(long_shot, "Best Long Shot"),
    }
