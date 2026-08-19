"""Pure prediction-market metric helpers (reproducible, no I/O)."""

from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any, Iterable


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def implied_probs_from_odds(odds: dict[int, float]) -> dict[int, float]:
    """Convert decimal odds to vig-removed implied probabilities."""
    inv: dict[int, float] = {}
    for cloth, odd in odds.items():
        if odd is None or odd <= 0:
            continue
        inv[cloth] = 1.0 / float(odd)
    total = sum(inv.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in inv.items()}


def probs_from_counts(counts: dict[int, int | float]) -> dict[int, float]:
    total = float(sum(max(0.0, float(v)) for v in counts.values()))
    if total <= 0:
        return {}
    return {k: max(0.0, float(v)) / total for k, v in counts.items()}


def entropy(probs: Iterable[float]) -> float:
    h = 0.0
    for p in probs:
        if p > 0:
            h -= p * math.log(p, 2)
    return h


def normalized_confidence(probs: dict[int, float]) -> float:
    """1 - H(p)/log2(n) → 0..1 (1 = peaked / confident)."""
    if not probs:
        return 0.0
    n = len(probs)
    if n <= 1:
        return 1.0
    h = entropy(probs.values())
    return max(0.0, min(1.0, 1.0 - h / math.log(n, 2)))


def rank_by_score(scores: dict[int, float], *, descending: bool = True) -> dict[int, int]:
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1] if descending else kv[1], kv[0]))
    return {cloth: i for i, (cloth, _) in enumerate(ordered, start=1)}


def spearman_accuracy(expected_ranks: dict[int, int], actual_ranks: dict[int, int]) -> float:
    keys = [k for k in expected_ranks if k in actual_ranks]
    n = len(keys)
    if n < 2:
        return 100.0 if n == 1 and expected_ranks.get(keys[0]) == actual_ranks.get(keys[0]) else 0.0
    d2 = sum((expected_ranks[k] - actual_ranks[k]) ** 2 for k in keys)
    rho = 1.0 - (6.0 * d2) / (n * (n * n - 1))
    return max(0.0, min(100.0, (rho + 1.0) * 50.0))


def surprise_index(crowd_rank: int | None, actual_rank: int | None, field_size: int) -> float:
    if crowd_rank is None or actual_rank is None or field_size <= 1:
        return 0.0
    return abs(crowd_rank - actual_rank) / (field_size - 1) * 100.0


def upset_score(winner_crowd_rank: int | None, field_size: int) -> float:
    if winner_crowd_rank is None or field_size <= 1:
        return 0.0
    return (winner_crowd_rank - 1) / (field_size - 1) * 100.0


def favorite_failure_score(favorite_actual_rank: int | None, field_size: int) -> float:
    if favorite_actual_rank is None or field_size <= 1:
        return 0.0
    return (favorite_actual_rank - 1) / (field_size - 1) * 100.0


def prediction_difficulty(probs: dict[int, float]) -> float:
    """Entropy scaled to 0..100."""
    if not probs:
        return 0.0
    n = len(probs)
    if n <= 1:
        return 0.0
    return max(0.0, min(100.0, entropy(probs.values()) / math.log(n, 2) * 100.0))


def crowd_bias(probs: dict[int, float], actual_ranks: dict[int, int]) -> float:
    """
    Mean (p_i - 1_{finish=1}) for runners with known finishes.
    Positive ⇒ public overweighted winners less often than believed (overconfident on favorites).
    """
    if not probs:
        return 0.0
    gaps = []
    for cloth, p in probs.items():
        fin = actual_ranks.get(cloth)
        if fin is None:
            continue
        y = 1.0 if fin == 1 else 0.0
        gaps.append(p - y)
    return mean(gaps) if gaps else 0.0


def shock_score(
    *,
    favorite_failure: float,
    upset: float,
    crowd_accuracy_pct: float,
) -> float:
    return round(mean([favorite_failure, upset, 100.0 - crowd_accuracy_pct]), 3)


def merge_market_probs(
    *,
    survey_counts: dict[int, int] | None,
    win_odds: dict[int, float] | None,
) -> tuple[dict[int, float], str]:
    """Prefer survey distribution when present; else win-market implied probs."""
    if survey_counts:
        probs = probs_from_counts(survey_counts)
        if probs:
            return probs, "survey"
    if win_odds:
        probs = implied_probs_from_odds(win_odds)
        if probs:
            return probs, "win_odds"
    return {}, "none"


def pick_win_odds_map(odds_payload: dict[str, Any] | None) -> dict[int, float]:
    """
    Dynamically find a win-style odds map inside an odds payload.

    Prefers keys containing 'pish' (پیش‌بر), else first map of {runner→odd}.
    """
    if not odds_payload:
        return {}
    # Navigate into common wrappers without assuming exact schema
    root = odds_payload
    for key in ("data", "odds"):
        if isinstance(root, dict) and key in root and isinstance(root[key], dict):
            root = root[key]
    if not isinstance(root, dict):
        return {}

    candidates: list[tuple[int, str, dict[int, float]]] = []
    for market_name, market_val in root.items():
        if not isinstance(market_val, dict):
            continue
        parsed: dict[int, float] = {}
        for k, v in market_val.items():
            cloth = None
            odd = None
            if isinstance(v, dict):
                odd = _safe_float(v.get("odd") if "odd" in v else v.get("odds"))
                rid = v.get("runnerId", v.get("runner_id", k))
                try:
                    cloth = int(str(rid).split("||")[0])
                except ValueError:
                    continue
            else:
                odd = _safe_float(v)
                try:
                    cloth = int(k)
                except ValueError:
                    continue
            if cloth is not None and odd is not None and odd > 0:
                parsed[cloth] = odd
        if len(parsed) >= 2:
            prefer = 0
            name = str(market_name).lower()
            if "pish" in name or "win" in name or name in {"win_1st", "win"}:
                prefer = 2
            elif "miyan" in name or "place" in name:
                prefer = 1
            candidates.append((prefer, str(market_name), parsed))
    if not candidates:
        return {}
    candidates.sort(key=lambda x: (-x[0], -len(x[2]), x[1]))
    return candidates[0][2]


def pick_survey_counts(survey_payload: dict[str, Any] | None) -> dict[int, int]:
    """Dynamically extract horse_num→count from survey-statistics payload."""
    if not survey_payload:
        return {}
    root = survey_payload.get("data", survey_payload) if isinstance(survey_payload, dict) else {}
    stats = None
    if isinstance(root, dict):
        for key, val in root.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                # look for count-like list
                sample = val[0]
                if any(k in sample for k in ("count", "votes", "amount", "horse_num", "number")):
                    stats = val
                    break
        if stats is None and isinstance(root.get("statistics"), list):
            stats = root["statistics"]
    if not isinstance(stats, list):
        return {}
    out: dict[int, int] = {}
    for row in stats:
        if not isinstance(row, dict):
            continue
        cloth = row.get("horse_num", row.get("number", row.get("cloth", row.get("runnerId"))))
        count = row.get("count", row.get("votes", row.get("amount")))
        try:
            c = int(cloth)
            n = int(float(count)) if count is not None else 0
        except (TypeError, ValueError):
            continue
        out[c] = n
    return out


def entity_scores_from_starts(starts: list[dict[str, Any]]) -> dict[str, float | None]:
    """
    Aggregate horse/entity metrics from per-start dicts with keys:
    crowd_rank, actual_rank, crowd_prob, was_favorite, won, field_size, surprise
    """
    if not starts:
        return {}
    gaps = []
    surprises = []
    fav_fail = 0
    fav_n = 0
    upset_wins = 0
    wins = 0
    pred_ranks = []
    act_ranks = []
    popularities = []
    for s in starts:
        cr = s.get("crowd_rank")
        ar = s.get("actual_rank")
        if cr is not None and ar is not None:
            gaps.append(float(cr) - float(ar))  # >0 outperformed market
            pred_ranks.append(float(cr))
            act_ranks.append(float(ar))
            surprises.append(abs(float(cr) - float(ar)))
        if s.get("was_favorite"):
            fav_n += 1
            if ar != 1:
                fav_fail += 1
        if ar == 1:
            wins += 1
            if cr is not None and cr >= 3:
                upset_wins += 1
        if s.get("crowd_prob") is not None:
            popularities.append(float(s["crowd_prob"]))

    avg_gap = mean(gaps) if gaps else None
    overrated = mean([g for g in gaps if g < 0]) if any(g < 0 for g in gaps) else 0.0
    underrated = mean([g for g in gaps if g > 0]) if any(g > 0 for g in gaps) else 0.0
    # Flip signs to positive scores
    overrated_score = abs(overrated) if overrated else 0.0
    underrated_score = abs(underrated) if underrated else 0.0
    return {
        "public_popularity_score": round(mean(popularities) * 100, 3) if popularities else None,
        "public_trust_score": round(
            (sum(1 for s in starts if s.get("was_favorite") and s.get("actual_rank") == 1) / fav_n)
            * 100,
            3,
        )
        if fav_n
        else None,
        "overrated_score": round(overrated_score, 3),
        "underrated_score": round(underrated_score, 3),
        "unpredictability_score": round(pstdev(surprises), 3) if len(surprises) >= 2 else 0.0,
        "surprise_frequency": round(
            sum(1 for x in surprises if x >= 2) / len(surprises) * 100, 3
        )
        if surprises
        else None,
        "favorite_failure_frequency": round(fav_fail / fav_n * 100, 3) if fav_n else None,
        "upset_victory_frequency": round(upset_wins / max(wins, 1) * 100, 3) if wins else 0.0,
        "avg_prediction_rank": round(mean(pred_ranks), 3) if pred_ranks else None,
        "avg_actual_rank": round(mean(act_ranks), 3) if act_ranks else None,
        "prediction_gap": round(avg_gap, 3) if avg_gap is not None else None,
    }
