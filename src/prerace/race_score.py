"""Race-level pre-race context scores."""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from src.analytics.metrics import clamp
from src.markets.answer import confidence_band, data_quality_label
from src.markets.scoring import RunnerContext
from src.prerace.types import Contribution, Explanation, RaceContextScore


def _weather_impact(weather: dict[str, Any] | None) -> tuple[float, list[Contribution]]:
    """
    0 = benign, 100 = severe disruption risk.
    Derived from rainfall / wind / visibility — no fabricated forecasts.
    """
    if not weather:
        return 25.0, [
            Contribution("weather", None, 1.0, 25.0, "No weather row — neutral-low impact assumed")
        ]
    contribs: list[Contribution] = []
    rain = weather.get("rainfall_mm") or weather.get("rainfall_day_mm") or 0.0
    wind = weather.get("wind_speed_kmh") or 0.0
    vis = weather.get("visibility_m")
    score = 0.0
    rain_c = clamp(float(rain) * 8.0)
    wind_c = clamp(float(wind) * 1.5)
    vis_c = 0.0
    if vis is not None and float(vis) > 0:
        vis_c = clamp(100.0 - float(vis) / 100.0)
    score = clamp(0.45 * rain_c + 0.35 * wind_c + 0.20 * vis_c)
    contribs.append(Contribution("rainfall_mm", rain, 0.45, rain_c, "Rain raises impact"))
    contribs.append(Contribution("wind_speed_kmh", wind, 0.35, wind_c, "Wind raises impact"))
    contribs.append(Contribution("visibility_m", vis, 0.20, vis_c, "Low visibility raises impact"))
    return score, contribs


def _expected_pace(field: list[RunnerContext], distance: int | None) -> str:
    """Heuristic pace label from field speed/form — not a fabricated sectional."""
    speeds = [r.speed_index for r in field if r.speed_index is not None]
    forms = [r.form_score_5 for r in field if r.form_score_5 is not None]
    if not speeds and not forms:
        return "unknown"
    avg_speed = mean(speeds) if speeds else 100.0
    avg_form = mean(forms) if forms else 50.0
    hot = avg_speed >= 102 or avg_form >= 65
    slow = avg_speed <= 97 and avg_form <= 40
    if distance and distance >= 2000:
        return "staying_grind" if not hot else "honest_staying"
    if hot:
        return "fast_early"
    if slow:
        return "moderate_slow"
    return "even"


def _race_shape(field: list[RunnerContext], competition: float) -> str:
    strengths = [r.strength for r in field]
    if len(strengths) < 2:
        return "sparse"
    spread = pstdev(strengths)
    if competition >= 70 and spread < 12:
        return "tight_pack"
    if spread >= 20:
        return "top_heavy"
    if competition >= 55:
        return "competitive"
    return "open"


def score_race_context(
    field: list[RunnerContext],
    *,
    distance: int | None = None,
    race_class: str | None = None,
    weather: dict[str, Any] | None = None,
    classification_difficulty: float | None = None,
) -> RaceContextScore:
    strengths = [r.strength for r in field] or [40.0]
    field_strength = mean(strengths)
    spread = pstdev(strengths) if len(strengths) >= 2 else 0.0
    # Competition: tight high-quality fields score higher
    competition = clamp(
        0.55 * field_strength + 0.25 * (100.0 - spread * 2.5) + 0.20 * min(100.0, len(field) * 8.0)
    )
    if classification_difficulty is not None:
        competition = clamp(0.7 * competition + 0.3 * float(classification_difficulty))

    weather_impact, weather_contribs = _weather_impact(weather)

    track_scores = []
    for r in field:
        ts = r.meta.get("track_pref_score")
        if ts is not None:
            track_scores.append(float(ts) * 100.0 if float(ts) <= 1.0 else float(ts))
    track_suit = mean(track_scores) if track_scores else 50.0

    race_strength = clamp(
        0.40 * field_strength
        + 0.30 * competition
        + 0.15 * (100.0 - weather_impact)
        + 0.15 * track_suit
    )

    pace = _expected_pace(field, distance)
    shape = _race_shape(field, competition)

    sample = sum(r.starts for r in field)
    missing = sum(
        1
        for r in field
        if r.performance_rating is None and r.form_score_5 is None and r.win_rate is None
    )
    dq = data_quality_label(missing_rate=missing / max(1, len(field)), sample_size=sample)
    conf = 40.0 + min(40.0, sample / 8.0) - missing * 4.0
    if not weather:
        conf -= 8.0

    contribs = [
        Contribution("field_strength", field_strength, 0.40, field_strength, "Mean runner strength"),
        Contribution("competition_level", competition, 0.30, competition, "Quality + tightness + size"),
        Contribution("weather_impact", weather_impact, 0.15, 100.0 - weather_impact, "Inverse weather disruption"),
        Contribution("track_suitability", track_suit, 0.15, track_suit, "Mean track preference"),
        *weather_contribs,
    ]
    explain = Explanation(
        why=(
            f"Race strength {race_strength:.1f}: field={field_strength:.1f}, "
            f"competition={competition:.1f}, weather_impact={weather_impact:.1f}, "
            f"pace={pace}, shape={shape}"
        ),
        contributions=contribs,
        confidence=confidence_band(conf),
        confidence_score=conf,
        sample_size=sample,
        data_quality=dq,
        warnings=["Weather data missing"] if not weather else [],
    )
    return RaceContextScore(
        race_strength=race_strength,
        field_strength=field_strength,
        competition_level=competition,
        weather_impact=weather_impact,
        track_suitability=track_suit,
        expected_pace=pace,
        race_shape=shape,
        explain=explain,
    )
