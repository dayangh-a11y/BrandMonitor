"""Per-horse Today's Chance Score and related pre-race metrics."""

from __future__ import annotations

from typing import Any

from src.analytics.metrics import clamp
from src.markets.answer import confidence_band, data_quality_label
from src.markets.scoring import RunnerContext, reliability_from_consistency, softmax_probs, top_k_probability
from src.markets.win import win_strength
from src.prerace.types import Contribution, Explanation, HorseTodayScore


def _rest_condition(rest_days: int | None) -> float | None:
    if rest_days is None:
        return None
    # Peak around 10–21 days
    if 10 <= rest_days <= 21:
        return 90.0
    if 7 <= rest_days < 10 or 21 < rest_days <= 35:
        return 70.0
    if 3 <= rest_days < 7 or 35 < rest_days <= 60:
        return 45.0
    if rest_days < 3:
        return 25.0
    return 35.0


def _weather_suitability(
    runner: RunnerContext,
    weather: dict[str, Any] | None,
) -> float | None:
    pref = runner.meta.get("weather_pref_score")
    if pref is not None:
        return clamp(float(pref) * 100.0 if float(pref) <= 1.0 else float(pref))
    if not weather:
        return None
    # Neutral when no preference learned
    return 50.0


def _distance_suitability(runner: RunnerContext, race_distance: int | None) -> float | None:
    score = runner.meta.get("distance_pref_score")
    if score is not None:
        return clamp(float(score) * 100.0 if float(score) <= 1.0 else float(score))
    return None


def _track_suitability(runner: RunnerContext) -> float | None:
    score = runner.meta.get("track_pref_score")
    if score is not None:
        return clamp(float(score) * 100.0 if float(score) <= 1.0 else float(score))
    return None


def score_horse_today(
    runner: RunnerContext,
    field: list[RunnerContext],
    *,
    race_distance: int | None = None,
    weather: dict[str, Any] | None = None,
    field_competition: float = 50.0,
) -> tuple[float, list[Contribution], dict[str, float | None]]:
    """
    Today's Chance Score 0..100 with weighted contributions.
    Distinct from raw season ranking — blends form, suitability, rest, fatigue.
    """
    parts: list[Contribution] = []

    def add(metric: str, value, weight: float, mapped: float | None, note: str) -> None:
        if mapped is None:
            return
        parts.append(Contribution(metric, value, weight, weight * mapped, note))

    ws = win_strength(runner)
    add("win_strength", ws, 0.22, ws, "Win-market strength (not season rank)")
    add("form_score_5", runner.form_score_5, 0.16, runner.form_score_5, "Recent form")
    add(
        "sex_adjusted_pr",
        runner.sex_adjusted_pr or runner.performance_rating,
        0.12,
        runner.sex_adjusted_pr or runner.performance_rating,
        "Sex-adjusted / performance rating",
    )
    dist = _distance_suitability(runner, race_distance)
    add("distance_suitability", dist, 0.10, dist, "Distance preference")
    track = _track_suitability(runner)
    add("track_suitability", track, 0.08, track, "Track preference")
    weather_s = _weather_suitability(runner, weather)
    add("weather_suitability", weather_s, 0.06, weather_s, "Weather preference")
    rest = _rest_condition(runner.rest_days)
    add("rest_condition", runner.rest_days, 0.08, rest, "Rest days fitness")
    fatigue = runner.fatigue_score if hasattr(runner, "fatigue_score") else runner.meta.get("fatigue")
    # fatigue on RunnerContext - check scoring.py - we have fatigue in metrics but not on RunnerContext
    fat = runner.meta.get("fatigue_score")
    if fat is not None:
        # lower fatigue better → invert
        add("fatigue", fat, 0.06, clamp(100.0 - float(fat)), "Lower fatigue preferred")
    add(
        "consistency",
        runner.consistency_score,
        0.06,
        runner.consistency_score,
        "Finish consistency",
    )
    add(
        "horse_jockey_combo",
        runner.meta.get("jockey_score"),
        0.03,
        (
            float(runner.meta["jockey_score"]) * 100.0
            if runner.meta.get("jockey_score") is not None
            and float(runner.meta["jockey_score"]) <= 1.0
            else runner.meta.get("jockey_score")
        ),
        "Horse–jockey combination",
    )
    add(
        "horse_trainer_combo",
        runner.meta.get("trainer_score"),
        0.03,
        (
            float(runner.meta["trainer_score"]) * 100.0
            if runner.meta.get("trainer_score") is not None
            and float(runner.meta["trainer_score"]) <= 1.0
            else runner.meta.get("trainer_score")
        ),
        "Horse–trainer combination",
    )

    if not parts:
        score = 35.0
    else:
        tw = sum(c.weight for c in parts)
        score = clamp(sum(c.impact for c in parts) / tw)

    # Opponent difficulty penalty for soft fields facing tough competition rating
    opp = field_competition
    metrics = {
        "distance_suitability": dist,
        "track_suitability": track,
        "weather_suitability": weather_s,
        "recent_form": runner.form_score_5,
        "momentum": runner.improvement_trend,
        "consistency": runner.consistency_score,
        "fatigue": float(fat) if fat is not None else None,
        "rest_condition": rest,
        "trainer_form": (
            float(runner.meta["trainer_score"]) * 100.0
            if runner.meta.get("trainer_score") is not None
            and float(runner.meta["trainer_score"]) <= 1.0
            else runner.meta.get("trainer_score")
        ),
        "jockey_form": (
            float(runner.meta["jockey_score"]) * 100.0
            if runner.meta.get("jockey_score") is not None
            and float(runner.meta["jockey_score"]) <= 1.0
            else runner.meta.get("jockey_score")
        ),
        "horse_jockey_combination": runner.meta.get("jockey_score"),
        "horse_trainer_combination": runner.meta.get("trainer_score"),
        "opponent_difficulty": opp,
    }
    return score, parts, metrics


def build_horse_scores(
    field: list[RunnerContext],
    *,
    race_distance: int | None = None,
    weather: dict[str, Any] | None = None,
    field_competition: float = 50.0,
    h2h_matrix: list[dict[str, Any]] | None = None,
) -> list[HorseTodayScore]:
    raw_scores: dict[int, float] = {}
    details: dict[int, tuple[list[Contribution], dict[str, float | None]]] = {}
    for r in field:
        sc, contribs, metrics = score_horse_today(
            r,
            field,
            race_distance=race_distance,
            weather=weather,
            field_competition=field_competition,
        )
        raw_scores[r.horse_id] = sc
        details[r.horse_id] = (contribs, metrics)

    win_probs = softmax_probs(raw_scores, temperature=9.0)
    top2 = top_k_probability(win_probs, 2)
    top3 = top_k_probability(win_probs, 3)

    # Expected finish from inverse rank of chance scores
    ordered = sorted(field, key=lambda r: raw_scores[r.horse_id], reverse=True)
    exp_finish = {r.horse_id: float(i) for i, r in enumerate(ordered, start=1)}

    # H2H lookup
    h2h_by_horse: dict[int, dict[str, float]] = {r.horse_id: {} for r in field}
    if h2h_matrix:
        by_id = {r.horse_id: r.horse_name for r in field}
        for row in h2h_matrix:
            a, b = row.get("horse_a_id"), row.get("horse_b_id")
            if a in h2h_by_horse and b in by_id:
                h2h_by_horse[a][by_id[b]] = float(row.get("a_finishes_ahead_of_b") or 0)
            if b in h2h_by_horse and a in by_id:
                h2h_by_horse[b][by_id[a]] = float(row.get("b_finishes_ahead_of_a") or 0)

    out: list[HorseTodayScore] = []
    for r in field:
        contribs, metrics = details[r.horse_id]
        sample = r.starts
        missing_flags = sum(
            1
            for k in ("recent_form", "consistency", "distance_suitability")
            if metrics.get(k) is None
        )
        dq = data_quality_label(missing_rate=missing_flags / 3.0, sample_size=sample)
        conf = 35.0 + min(40.0, sample * 4.0) + 20.0 * win_probs[r.horse_id]
        if dq in {"poor", "insufficient", "limited_sample"}:
            conf *= 0.75
        risk = None
        if r.consistency_score is not None:
            risk = clamp(0.5 * (100.0 - float(r.consistency_score)) + 0.3 * (40.0 - min(40, sample)) + 15.0)
        reliability = reliability_from_consistency(r.consistency_score, sample)

        why = (
            f"{r.horse_name}: Today's Chance {raw_scores[r.horse_id]:.1f}, "
            f"p_win={win_probs[r.horse_id]:.1%}, expected_finish≈{exp_finish[r.horse_id]:.0f}"
        )
        explain = Explanation(
            why=why,
            contributions=contribs,
            confidence=confidence_band(conf),
            confidence_score=conf,
            sample_size=sample,
            data_quality=dq,
            warnings=["Low sample size"] if sample < 3 else [],
        )
        out.append(
            HorseTodayScore(
                horse_id=r.horse_id,
                horse_name=r.horse_name,
                todays_chance_score=raw_scores[r.horse_id],
                winning_probability=win_probs[r.horse_id],
                top2_probability=top2[r.horse_id],
                top3_probability=top3[r.horse_id],
                distance_suitability=metrics.get("distance_suitability"),
                track_suitability=metrics.get("track_suitability"),
                weather_suitability=metrics.get("weather_suitability"),
                recent_form=metrics.get("recent_form"),
                momentum=metrics.get("momentum"),
                consistency=metrics.get("consistency"),
                risk_score=risk,
                reliability=reliability,
                fatigue=metrics.get("fatigue"),
                rest_condition=metrics.get("rest_condition"),
                trainer_form=metrics.get("trainer_form"),
                jockey_form=metrics.get("jockey_form"),
                horse_jockey_combination=(
                    float(metrics["horse_jockey_combination"])
                    if metrics.get("horse_jockey_combination") is not None
                    else None
                ),
                horse_trainer_combination=(
                    float(metrics["horse_trainer_combination"])
                    if metrics.get("horse_trainer_combination") is not None
                    else None
                ),
                opponent_difficulty=metrics.get("opponent_difficulty"),
                expected_finish_position=exp_finish[r.horse_id],
                confidence=confidence_band(conf),
                confidence_score=conf,
                sample_size=sample,
                data_quality=dq,
                h2h_probs=h2h_by_horse.get(r.horse_id, {}),
                explain=explain,
            )
        )
    out.sort(key=lambda h: h.todays_chance_score, reverse=True)
    return out
