"""Compute pre-race features for one observation from prior histories."""

from __future__ import annotations

from datetime import date
from statistics import median
from typing import Any, Sequence

from src.prediction_foundation.shrinkage import form_trend
from src.prediction_foundation.types import (
    FeatureCell,
    ObservationKeys,
    missing_cell,
    rate_cell,
    reliability_from_n,
    value_cell,
)

# Global priors (empirical defaults; refined during build from TRAIN priors only ideally)
DEFAULT_WIN_PRIOR = 0.12
DEFAULT_TOP3_PRIOR = 0.33
PRIOR_STRENGTH = 5.0


def _valid_finishes(rows: Sequence[dict[str, Any]]) -> list[int]:
    out: list[int] = []
    for r in rows:
        f = r.get("finish")
        if f is not None and int(f) >= 1:
            out.append(int(f))
    return out


def _wins(rows: Sequence[dict[str, Any]]) -> int:
    return sum(1 for r in rows if r.get("finish") == 1)


def _top3(rows: Sequence[dict[str, Any]]) -> int:
    return sum(1 for r in rows if r.get("finish") is not None and int(r["finish"]) in (1, 2, 3))


def compute_features(
    keys: ObservationKeys,
    *,
    horse_priors: list[dict[str, Any]],
    trainer_priors: list[dict[str, Any]],
    owner_priors: list[dict[str, Any]],
    win_prior: float = DEFAULT_WIN_PRIOR,
    top3_prior: float = DEFAULT_TOP3_PRIOR,
    owner_min_starts_for_use: int = 5,
) -> dict[str, FeatureCell]:
    """
    horse/trainer/owner_priors: chronologically sorted rows with keys:
      race_date(date), finish, track, dist, surface, class_code
    Must contain ONLY races with race_date < keys.race_date.
    """
    feats: dict[str, FeatureCell] = {}
    prior = horse_priors
    n = len(prior)
    finishes = _valid_finishes(prior)
    wins = _wins(prior)
    places = _top3(prior)

    # A) Horse history
    feats["career_starts_before_race"] = value_cell(n, sample_n=n)
    feats["career_wins_before_race"] = value_cell(wins, sample_n=n)
    feats["career_places_before_race"] = value_cell(places, sample_n=n)
    feats["career_win_rate"] = rate_cell(wins, n, prior_mean=win_prior, prior_strength=PRIOR_STRENGTH)
    feats["career_top3_rate"] = rate_cell(places, n, prior_mean=top3_prior, prior_strength=PRIOR_STRENGTH)
    if finishes:
        feats["career_avg_finish"] = value_cell(sum(finishes) / len(finishes), sample_n=len(finishes))
        feats["career_median_finish"] = value_cell(float(median(finishes)), sample_n=len(finishes))
        feats["career_best_finish"] = value_cell(min(finishes), sample_n=len(finishes))
    else:
        feats["career_avg_finish"] = missing_cell()
        feats["career_median_finish"] = missing_cell()
        feats["career_best_finish"] = missing_cell()

    # B) Recent form
    last5 = prior[-5:]
    last3 = prior[-3:]
    feats["recent_form_n"] = value_cell(len(last5), sample_n=len(last5))
    last5_f = _valid_finishes(last5)
    last3_f = _valid_finishes(last3)
    if last5_f:
        # last finish may be invalid even if others valid
        lf = prior[-1].get("finish")
        if lf is not None and int(lf) >= 1:
            feats["last_finish"] = value_cell(int(lf), sample_n=1)
        else:
            feats["last_finish"] = missing_cell()
        feats["avg_finish_last5"] = value_cell(sum(last5_f) / len(last5_f), sample_n=len(last5_f))
        feats["top3_rate_last5"] = rate_cell(
            _top3(last5), len(last5), prior_mean=top3_prior, prior_strength=PRIOR_STRENGTH
        )
        feats["win_rate_last5"] = rate_cell(
            _wins(last5), len(last5), prior_mean=win_prior, prior_strength=PRIOR_STRENGTH
        )
        ft = form_trend(last5_f)
        feats["form_trend"] = value_cell(ft, sample_n=len(last5_f)) if ft is not None else missing_cell()
    else:
        feats["last_finish"] = missing_cell()
        feats["avg_finish_last5"] = missing_cell()
        feats["top3_rate_last5"] = missing_cell()
        feats["win_rate_last5"] = missing_cell()
        feats["form_trend"] = missing_cell()
    if last3_f:
        feats["avg_finish_last3"] = value_cell(sum(last3_f) / len(last3_f), sample_n=len(last3_f))
    else:
        feats["avg_finish_last3"] = missing_cell()

    # days since last
    if prior:
        prev_d: date = prior[-1]["race_date"]
        cur_d = date.fromisoformat(keys.race_date[:10])
        feats["days_since_last_race"] = value_cell((cur_d - prev_d).days, sample_n=1)
    else:
        feats["days_since_last_race"] = missing_cell()

    # C) Distance
    target_dist = keys.distance
    if target_dist is None:
        for name in (
            "starts_same_distance",
            "wins_same_distance",
            "top3_same_distance",
            "win_rate_same_distance",
            "top3_rate_same_distance",
            "avg_finish_same_distance",
            "distance_difference_from_target",
            "distance_sample_n",
        ):
            feats[name] = missing_cell()
    else:
        same = [r for r in prior if r.get("dist") == target_dist]
        dn = len(same)
        feats["distance_sample_n"] = value_cell(dn, sample_n=dn)
        feats["starts_same_distance"] = value_cell(dn, sample_n=dn)
        feats["wins_same_distance"] = value_cell(_wins(same), sample_n=dn)
        feats["top3_same_distance"] = value_cell(_top3(same), sample_n=dn)
        feats["win_rate_same_distance"] = rate_cell(
            _wins(same), dn, prior_mean=win_prior, prior_strength=PRIOR_STRENGTH
        )
        feats["top3_rate_same_distance"] = rate_cell(
            _top3(same), dn, prior_mean=top3_prior, prior_strength=PRIOR_STRENGTH
        )
        sf = _valid_finishes(same)
        feats["avg_finish_same_distance"] = (
            value_cell(sum(sf) / len(sf), sample_n=len(sf)) if sf else missing_cell()
        )
        with_dist = [r for r in prior if r.get("dist") is not None]
        if with_dist:
            diffs = [abs(int(r["dist"]) - int(target_dist)) for r in with_dist]
            feats["distance_difference_from_target"] = value_cell(
                sum(diffs) / len(diffs), sample_n=len(diffs)
            )
        else:
            feats["distance_difference_from_target"] = missing_cell()

    # D) Track
    track = keys.track
    if not track:
        for name in (
            "starts_at_track",
            "wins_at_track",
            "top3_at_track",
            "avg_finish_at_track",
            "track_win_rate",
            "track_top3_rate",
            "track_sample_n",
        ):
            feats[name] = missing_cell()
    else:
        same_t = [r for r in prior if r.get("track") == track]
        tn = len(same_t)
        feats["track_sample_n"] = value_cell(tn, sample_n=tn)
        feats["starts_at_track"] = value_cell(tn, sample_n=tn)
        feats["wins_at_track"] = value_cell(_wins(same_t), sample_n=tn)
        feats["top3_at_track"] = value_cell(_top3(same_t), sample_n=tn)
        feats["track_win_rate"] = rate_cell(
            _wins(same_t), tn, prior_mean=win_prior, prior_strength=PRIOR_STRENGTH
        )
        feats["track_top3_rate"] = rate_cell(
            _top3(same_t), tn, prior_mean=top3_prior, prior_strength=PRIOR_STRENGTH
        )
        tf = _valid_finishes(same_t)
        feats["avg_finish_at_track"] = (
            value_cell(sum(tf) / len(tf), sample_n=len(tf)) if tf else missing_cell()
        )

    # E) Class — do not invent
    cls = keys.class_code
    if not cls:
        for name in (
            "starts_same_class",
            "wins_same_class",
            "top3_same_class",
            "avg_finish_same_class",
            "class_win_rate",
            "class_top3_rate",
            "class_sample_n",
        ):
            feats[name] = missing_cell()
    else:
        same_c = [r for r in prior if r.get("class_code") == cls]
        cn = len(same_c)
        feats["class_sample_n"] = value_cell(cn, sample_n=cn)
        feats["starts_same_class"] = value_cell(cn, sample_n=cn)
        feats["wins_same_class"] = value_cell(_wins(same_c), sample_n=cn)
        feats["top3_same_class"] = value_cell(_top3(same_c), sample_n=cn)
        feats["class_win_rate"] = rate_cell(
            _wins(same_c), cn, prior_mean=win_prior, prior_strength=PRIOR_STRENGTH
        )
        feats["class_top3_rate"] = rate_cell(
            _top3(same_c), cn, prior_mean=top3_prior, prior_strength=PRIOR_STRENGTH
        )
        cf = _valid_finishes(same_c)
        feats["avg_finish_same_class"] = (
            value_cell(sum(cf) / len(cf), sample_n=len(cf)) if cf else missing_cell()
        )

    # F) Breed
    breed = keys.surface
    if not breed:
        feats["breed"] = missing_cell()
        feats["breed_starts"] = missing_cell()
        feats["breed_win_rate"] = missing_cell()
        feats["breed_top3_rate"] = missing_cell()
    else:
        feats["breed"] = value_cell(breed)
        same_b = [r for r in prior if r.get("surface") == breed]
        bn = len(same_b)
        feats["breed_starts"] = value_cell(bn, sample_n=bn)
        feats["breed_win_rate"] = rate_cell(
            _wins(same_b), bn, prior_mean=win_prior, prior_strength=PRIOR_STRENGTH
        )
        feats["breed_top3_rate"] = rate_cell(
            _top3(same_b), bn, prior_mean=top3_prior, prior_strength=PRIOR_STRENGTH
        )

    # G) Trainer
    if keys.trainer_id is None:
        for name in (
            "trainer_starts_prior",
            "trainer_wins_prior",
            "trainer_win_rate_prior",
            "trainer_top3_rate_prior",
            "trainer_recent_form",
            "trainer_sample_n",
        ):
            feats[name] = missing_cell()
    else:
        tp = trainer_priors
        tn = len(tp)
        feats["trainer_sample_n"] = value_cell(tn, sample_n=tn)
        feats["trainer_starts_prior"] = value_cell(tn, sample_n=tn)
        feats["trainer_wins_prior"] = value_cell(_wins(tp), sample_n=tn)
        feats["trainer_win_rate_prior"] = rate_cell(
            _wins(tp), tn, prior_mean=win_prior, prior_strength=PRIOR_STRENGTH
        )
        feats["trainer_top3_rate_prior"] = rate_cell(
            _top3(tp), tn, prior_mean=top3_prior, prior_strength=PRIOR_STRENGTH
        )
        t_last = _valid_finishes(tp[-5:])
        feats["trainer_recent_form"] = (
            value_cell(sum(t_last) / len(t_last), sample_n=len(t_last)) if t_last else missing_cell()
        )

    # H) Owner — only if sufficient evidence
    if keys.owner_id is None:
        feats["owner_starts_prior"] = missing_cell()
        feats["owner_win_rate_prior"] = missing_cell()
        feats["owner_top3_rate_prior"] = missing_cell()
    else:
        op = owner_priors
        on = len(op)
        if on < owner_min_starts_for_use:
            # Keep starts visible but mark rates missing/low — do not force weak owner signal
            feats["owner_starts_prior"] = FeatureCell(
                value=on,
                is_missing=False,
                sample_n=on,
                reliability=reliability_from_n(on),
            )
            feats["owner_win_rate_prior"] = missing_cell()
            feats["owner_top3_rate_prior"] = missing_cell()
            feats["owner_win_rate_prior"].sample_n = on
            feats["owner_top3_rate_prior"].sample_n = on
        else:
            feats["owner_starts_prior"] = value_cell(on, sample_n=on)
            feats["owner_win_rate_prior"] = rate_cell(
                _wins(op), on, prior_mean=win_prior, prior_strength=PRIOR_STRENGTH
            )
            feats["owner_top3_rate_prior"] = rate_cell(
                _top3(op), on, prior_mean=top3_prior, prior_strength=PRIOR_STRENGTH
            )

    # I) Current race conditions
    feats["race_track"] = value_cell(keys.track) if keys.track else missing_cell()
    feats["race_distance"] = value_cell(keys.distance) if keys.distance is not None else missing_cell()
    feats["race_class"] = value_cell(keys.class_code) if keys.class_code else missing_cell()
    feats["race_breed"] = value_cell(keys.surface) if keys.surface else missing_cell()
    # age_category passed via keys extension? use class join separately — placeholder from keys
    # assigned in build via flags/meta; here from optional attribute
    age_cat = getattr(keys, "age_category", None)
    feats["age_category"] = value_cell(age_cat) if age_cat else missing_cell()
    if keys.weight is None or float(keys.weight) <= 0:
        feats["assigned_weight"] = missing_cell()
    else:
        feats["assigned_weight"] = value_cell(float(keys.weight))
    if keys.field_size is None or keys.field_size <= 0:
        feats["field_size"] = missing_cell()
    else:
        feats["field_size"] = value_cell(int(keys.field_size))

    return feats


def compute_targets(finish: int | None) -> dict[str, Any]:
    if finish is None or int(finish) < 1:
        return {"target_win": None, "target_top3": None, "target_finish": None}
    f = int(finish)
    return {
        "target_win": 1 if f == 1 else 0,
        "target_top3": 1 if f in (1, 2, 3) else 0,
        "target_finish": f,
    }
