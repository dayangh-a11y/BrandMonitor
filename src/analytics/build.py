"""Build analytics metrics and ranking tables from warehouse data."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.analytics.metrics import (
    StartRec,
    age_band,
    age_years,
    as_date,
    combo_score,
    consistency_score,
    difficulty_index,
    distance_bucket,
    fatigue_score,
    form_score,
    parse_prize_map,
    parse_race_class,
    parse_time_seconds,
    performance_rating,
    preference_from_buckets,
    safe_rate,
    speed_index_for_run,
    trend_slope,
)
from src.analytics.models import AnlBuildRun, AnlHorseMetrics, AnlRanking, AnlSeason
from src.analytics.seasons import SeasonCluster, discover_seasons
from src.analytics.views import create_analytics_views
from src.database.features import FeatRaceWeather
from src.warehouse.models import (
    WhHorse,
    WhHorsePedigree,
    WhJockey,
    WhOwner,
    WhRace,
    WhRaceResult,
    WhRaceWeather,
    WhTrainer,
)

BUILDER_VERSION = "1.0.0"
MIN_STARTS_DEFAULT = 1


def _load_starts(session: Session) -> list[StartRec]:
    """Assemble start records with field context for difficulty/speed."""
    # Preload people / pedigree
    jockeys = {j.id: j.name for j in session.scalars(select(WhJockey)).all()}
    trainers = {t.id: t.name for t in session.scalars(select(WhTrainer)).all()}
    owners = {o.id: o.name for o in session.scalars(select(WhOwner)).all()}
    horses = {
        h.id: h
        for h in session.scalars(select(WhHorse)).all()
    }
    pedigree = {
        p.horse_id: p.sire_name
        for p in session.scalars(select(WhHorsePedigree)).all()
    }

    weather_by_race: dict[int, tuple[str | None, str | None]] = {}
    for rid, cat, track in session.execute(
        select(
            FeatRaceWeather.race_id,
            FeatRaceWeather.weather_category,
            FeatRaceWeather.track_condition,
        )
    ):
        weather_by_race[int(rid)] = (cat, track)
    # Fallback to warehouse weather if feat not built
    for wx in session.scalars(select(WhRaceWeather)).all():
        if wx.race_id not in weather_by_race:
            weather_by_race[wx.race_id] = (None, wx.track_condition)

    races = {r.id: r for r in session.scalars(select(WhRace)).all()}
    results = session.scalars(select(WhRaceResult)).all()

    # Field aggregates per race
    field_times: dict[int, list[float]] = defaultdict(list)
    field_ratings: dict[int, list[float]] = defaultdict(list)
    field_size: dict[int, int] = defaultdict(int)
    for res in results:
        if res.finish_position is None or res.finish_position <= 0:
            continue
        field_size[res.race_id] += 1
        t = parse_time_seconds(res.time_raw)
        if t:
            field_times[res.race_id].append(t)
        if res.source_rating is not None and res.source_rating > 0:
            field_ratings[res.race_id].append(float(res.source_rating))

    starts: list[StartRec] = []
    for res in results:
        if res.horse_id is None or res.finish_position is None or res.finish_position <= 0:
            continue
        race = races.get(res.race_id)
        if race is None:
            continue
        horse = horses.get(res.horse_id)
        if horse is None:
            continue
        prize_map = parse_prize_map(race.prize_json)
        prize = float(prize_map.get(int(res.finish_position), 0.0))
        wcat, tcond = weather_by_race.get(res.race_id, (None, None))
        starts.append(
            StartRec(
                horse_id=horse.id,
                horse_name=horse.name,
                race_id=race.id,
                race_date=as_date(race.race_date),
                racecourse_code=race.racecourse_code,
                breed=race.surface,
                distance=race.distance,
                race_name=race.name,
                finish=int(res.finish_position),
                time_raw=res.time_raw,
                source_rating=float(res.source_rating) if res.source_rating is not None else None,
                prize=prize,
                jockey=jockeys.get(res.jockey_id) if res.jockey_id else None,
                trainer=trainers.get(res.trainer_id) if res.trainer_id else None,
                owner=owners.get(res.owner_id) if res.owner_id else None,
                sire=pedigree.get(horse.id),
                birthdate=as_date(horse.birthdate),
                weather_category=wcat,
                track_condition=tcond,
                field_times=list(field_times.get(race.id, [])),
                field_ratings=list(field_ratings.get(race.id, [])),
                field_size=field_size.get(race.id, 0),
            )
        )
    return starts


def _filter_scope(
    starts: list[StartRec],
    *,
    season: SeasonCluster | None,
    breed: str | None = None,
) -> list[StartRec]:
    out = starts
    if season is not None:
        out = [
            s
            for s in out
            if s.race_date
            and season.start_date <= s.race_date <= season.end_date
            and (
                season.racecourse_code is None
                or s.racecourse_code == season.racecourse_code
            )
        ]
    if breed and breed != "*":
        out = [s for s in out if s.breed == breed]
    return out


def _compute_horse_metrics(
    horse_id: int,
    horse_starts: list[StartRec],
    *,
    scope: str,
    season_key: str,
    breed: str,
    max_earnings: float,
) -> AnlHorseMetrics | None:
    if not horse_starts:
        return None
    horse_starts = sorted(
        horse_starts,
        key=lambda s: s.race_date or date.min,
        reverse=True,
    )
    finishes = [s.finish for s in horse_starts]
    wins = sum(1 for f in finishes if f == 1)
    seconds = sum(1 for f in finishes if f == 2)
    thirds = sum(1 for f in finishes if f == 3)
    places = wins + seconds + thirds
    starts_n = len(finishes)
    win_rate = safe_rate(wins, starts_n)
    place_rate = safe_rate(places, starts_n)
    avg_fin = mean(finishes)
    cons = consistency_score(finishes)
    f3 = form_score(finishes, 3)
    f5 = form_score(finishes, 5)
    f10 = form_score(finishes, 10)

    # Speed / difficulty / earnings
    speed_vals: list[float] = []
    diff_vals: list[float] = []
    earnings = 0.0
    for s in horse_starts:
        earnings += s.prize
        t = parse_time_seconds(s.time_raw)
        si = speed_index_for_run(
            time_s=t, distance=s.distance, field_times=s.field_times
        )
        if si is not None:
            speed_vals.append(si)
        diff_vals.append(
            difficulty_index(
                field_ratings=s.field_ratings,
                field_size=s.field_size,
                race_class=parse_race_class(s.race_name),
            )
        )
    speed_idx = mean(speed_vals) if speed_vals else None
    diff_idx = mean(diff_vals) if diff_vals else None
    earn_idx = (earnings / max_earnings) if max_earnings > 0 else 0.0

    # Preferences
    by_track: dict[str, list[int]] = defaultdict(list)
    by_dist: dict[str, list[int]] = defaultdict(list)
    by_weather: dict[str, list[int]] = defaultdict(list)
    by_going: dict[str, list[int]] = defaultdict(list)
    by_jockey: dict[str, list[int]] = defaultdict(list)
    by_trainer: dict[str, list[int]] = defaultdict(list)
    by_class: dict[str, list[int]] = defaultdict(list)
    for s in horse_starts:
        if s.racecourse_code:
            by_track[s.racecourse_code].append(s.finish)
        by_dist[distance_bucket(s.distance)].append(s.finish)
        if s.weather_category:
            by_weather[s.weather_category].append(s.finish)
        if s.track_condition:
            by_going[s.track_condition].append(s.finish)
        if s.jockey:
            by_jockey[s.jockey].append(s.finish)
        if s.trainer:
            by_trainer[s.trainer].append(s.finish)
        by_class[parse_race_class(s.race_name)].append(s.finish)

    track_pref, track_score = preference_from_buckets(by_track)
    dist_pref, dist_score = preference_from_buckets(by_dist)
    weather_pref, weather_score = preference_from_buckets(by_weather)
    going_pref, going_score = preference_from_buckets(by_going)
    best_j, j_score = combo_score(by_jockey)
    best_t, t_score = combo_score(by_trainer)

    # Fatigue / trends
    newest = horse_starts[0]
    days_since = None
    if newest.race_date:
        # relative to next-newest? use gap between 1st and 2nd most recent
        if len(horse_starts) >= 2 and horse_starts[1].race_date and newest.race_date:
            days_since = (newest.race_date - horse_starts[1].race_date).days
            days_since = abs(days_since)
    starts_30 = 0
    if newest.race_date:
        cutoff = newest.race_date - timedelta(days=30)
        starts_30 = sum(
            1 for s in horse_starts if s.race_date and s.race_date >= cutoff
        )
    fat = fatigue_score(days_since_last=days_since, starts_last_30d=starts_30)
    slope = trend_slope(finishes, window=5)
    improving = bool(slope is not None and slope > 2.0)
    declining = bool(slope is not None and slope < -2.0)
    improvement = max(0.0, slope) if slope is not None else None
    decline = max(0.0, -slope) if slope is not None else None

    # Age / class / sire
    age = age_years(newest.birthdate, newest.race_date)
    primary_class = None
    if by_class:
        primary_class = max(by_class.items(), key=lambda kv: len(kv[1]))[0]

    perf = performance_rating(
        win_rate=win_rate,
        place_rate=place_rate,
        avg_finish=avg_fin,
        consistency=cons,
        speed_index=speed_idx,
        earnings_index=earn_idx,
        difficulty_index=diff_idx,
    )

    explain = {
        "performance_rating": perf,
        "components": {
            "win_rate": win_rate,
            "place_rate": place_rate,
            "avg_finish": avg_fin,
            "consistency_score": cons,
            "speed_index": speed_idx,
            "earnings_index": earn_idx,
            "difficulty_index": diff_idx,
            "form_score_5": f5,
        },
        "volume": {"starts": starts_n, "wins": wins, "places": places},
        "preferences": {
            "track": track_pref,
            "distance": dist_pref,
            "weather": weather_pref,
            "track_condition": going_pref,
        },
        "trends": {
            "improvement_trend": improvement,
            "decline_trend": decline,
            "fatigue_score": fat,
        },
    }
    explain_text = (
        f"PR={perf} · starts={starts_n} W={wins} "
        f"win%={(win_rate or 0)*100:.0f} place%={(place_rate or 0)*100:.0f} "
        f"avgFin={avg_fin:.2f} cons={cons} form5={f5} "
        f"speed={speed_idx} earnIdx={earn_idx:.3f} diff={diff_idx}"
    )

    return AnlHorseMetrics(
        horse_id=horse_id,
        horse_name=horse_starts[0].horse_name,
        scope=scope,
        season_key=season_key,
        breed=breed,
        starts=starts_n,
        wins=wins,
        seconds=seconds,
        thirds=thirds,
        places=places,
        win_rate=win_rate,
        place_rate=place_rate,
        avg_finish=round(avg_fin, 4),
        performance_rating=perf,
        consistency_score=cons,
        form_score_3=f3,
        form_score_5=f5,
        form_score_10=f10,
        speed_index=round(speed_idx, 3) if speed_idx is not None else None,
        earnings_index=round(earn_idx, 4),
        earnings_total=earnings,
        difficulty_index=round(diff_idx, 3) if diff_idx is not None else None,
        track_preference=track_pref,
        track_preference_score=track_score,
        distance_preference=dist_pref,
        distance_preference_score=dist_score,
        weather_preference=weather_pref,
        weather_preference_score=weather_score,
        track_condition_preference=going_pref,
        track_condition_preference_score=going_score,
        jockey_combination_score=j_score,
        best_jockey=best_j,
        trainer_combination_score=t_score,
        best_trainer=best_t,
        fatigue_score=fat,
        improvement_trend=improvement,
        decline_trend=decline,
        is_improving=improving,
        is_declining=declining,
        age_years=age,
        age_band=age_band(age),
        primary_class=primary_class,
        sire_name=horse_starts[0].sire,
        explain_json=explain,
        explain_text=explain_text,
        features_json={
            "builder_version": BUILDER_VERSION,
            "class_buckets": {k: len(v) for k, v in by_class.items()},
        },
    )


def _rank_key_success(m: AnlHorseMetrics) -> tuple:
    return (
        -(m.wins or 0),
        -(m.win_rate or 0),
        -(m.earnings_total or 0),
        (m.avg_finish or 99),
    )


def _rank_key_performance(m: AnlHorseMetrics) -> tuple:
    return (
        -(m.performance_rating or 0),
        -(m.wins or 0),
        -(m.win_rate or 0),
        (m.avg_finish or 99),
    )


def _rank_key_consistent(m: AnlHorseMetrics) -> tuple:
    return (
        -(m.consistency_score or 0),
        -(m.starts or 0),
        (m.avg_finish or 99),
    )


def _add_ranking_rows(
    session: Session,
    *,
    category: str,
    scope: str,
    season_key: str,
    segment: str,
    metrics: list[AnlHorseMetrics],
    key_fn,
    build_run_id: int,
    limit: int = 25,
    metric_primary: str = "performance_rating",
    min_starts: int = MIN_STARTS_DEFAULT,
) -> int:
    eligible = [m for m in metrics if (m.starts or 0) >= min_starts]
    eligible.sort(key=key_fn)
    now = datetime.now(timezone.utc)
    n = 0
    for rank, m in enumerate(eligible[:limit], 1):
        why = {
            "rank": rank,
            "category": category,
            "primary_metric": metric_primary,
            "performance_rating": m.performance_rating,
            "wins": m.wins,
            "win_rate": m.win_rate,
            "place_rate": m.place_rate,
            "avg_finish": m.avg_finish,
            "consistency_score": m.consistency_score,
            "form_score_5": m.form_score_5,
            "speed_index": m.speed_index,
            "earnings_total": m.earnings_total,
            "difficulty_index": m.difficulty_index,
            "explain": m.explain_json,
        }
        why_text = (
            f"#{rank} {m.horse_name}: {m.explain_text or ''} "
            f"[category={category} segment={segment}]"
        )
        session.add(
            AnlRanking(
                category=category,
                scope=scope,
                season_key=season_key,
                segment=segment,
                entity_type="horse",
                entity_key=str(m.horse_id),
                entity_id=m.horse_id,
                entity_name=m.horse_name,
                rank=rank,
                score=m.performance_rating,
                metric_primary=metric_primary,
                starts=m.starts,
                wins=m.wins,
                win_rate=m.win_rate,
                place_rate=m.place_rate,
                avg_finish=m.avg_finish,
                performance_rating=m.performance_rating,
                consistency_score=m.consistency_score,
                form_score=m.form_score_5,
                earnings_total=m.earnings_total,
                why_json=why,
                why_text=why_text,
                metrics_json=m.explain_json,
                build_run_id=build_run_id,
                computed_at=now,
            )
        )
        n += 1
    return n


def _entity_rankings_from_starts(
    session: Session,
    *,
    starts: list[StartRec],
    scope: str,
    season_key: str,
    build_run_id: int,
    limit: int = 25,
) -> int:
    """Best trainer / jockey / owner / sire by wins → win% → starts."""
    groups: dict[str, dict[str, dict[str, Any]]] = {
        "trainer": defaultdict(lambda: {"starts": 0, "wins": 0, "places": 0, "earnings": 0.0}),
        "jockey": defaultdict(lambda: {"starts": 0, "wins": 0, "places": 0, "earnings": 0.0}),
        "owner": defaultdict(lambda: {"starts": 0, "wins": 0, "places": 0, "earnings": 0.0}),
        "sire": defaultdict(lambda: {"starts": 0, "wins": 0, "places": 0, "earnings": 0.0}),
    }
    for s in starts:
        mapping = {
            "trainer": s.trainer,
            "jockey": s.jockey,
            "owner": s.owner,
            "sire": s.sire,
        }
        for etype, name in mapping.items():
            if not name:
                continue
            st = groups[etype][name]
            st["starts"] += 1
            if s.finish == 1:
                st["wins"] += 1
            if s.finish in (1, 2, 3):
                st["places"] += 1
            st["earnings"] += s.prize

    now = datetime.now(timezone.utc)
    written = 0
    category_map = {
        "trainer": "best_trainer",
        "jockey": "best_jockey",
        "owner": "best_owner",
        "sire": "best_sire",
    }
    for etype, bucket in groups.items():
        rows = []
        for name, st in bucket.items():
            wr = st["wins"] / st["starts"] if st["starts"] else 0
            pr = st["places"] / st["starts"] if st["starts"] else 0
            rows.append((name, st, wr, pr))
        rows.sort(key=lambda x: (-x[1]["wins"], -x[2], -x[1]["earnings"], -x[1]["starts"]))
        for rank, (name, st, wr, pr) in enumerate(rows[:limit], 1):
            why = {
                "wins": st["wins"],
                "starts": st["starts"],
                "win_rate": wr,
                "place_rate": pr,
                "earnings": st["earnings"],
            }
            session.add(
                AnlRanking(
                    category=category_map[etype],
                    scope=scope,
                    season_key=season_key,
                    segment="*",
                    entity_type=etype,
                    entity_key=name,
                    entity_id=None,
                    entity_name=name,
                    rank=rank,
                    score=float(st["wins"]),
                    metric_primary="wins",
                    starts=st["starts"],
                    wins=st["wins"],
                    win_rate=wr,
                    place_rate=pr,
                    avg_finish=None,
                    performance_rating=None,
                    consistency_score=None,
                    form_score=None,
                    earnings_total=st["earnings"],
                    why_json=why,
                    why_text=(
                        f"#{rank} {name}: wins={st['wins']}/{st['starts']} "
                        f"({wr*100:.0f}%) places={st['places']} earnings={st['earnings']:,.0f}"
                    ),
                    metrics_json=why,
                    build_run_id=build_run_id,
                    computed_at=now,
                )
            )
            written += 1
    return written


def _segment_rankings(
    session: Session,
    *,
    metrics: list[AnlHorseMetrics],
    starts: list[StartRec],
    scope: str,
    season_key: str,
    build_run_id: int,
) -> int:
    """Best horse by breed / age / class / distance / weather / track condition."""
    written = 0

    # By breed from metrics where breed != *
    by_breed: dict[str, list[AnlHorseMetrics]] = defaultdict(list)
    for m in metrics:
        if m.breed and m.breed != "*":
            by_breed[m.breed].append(m)
    for breed, rows in by_breed.items():
        written += _add_ranking_rows(
            session,
            category="best_by_breed",
            scope=scope,
            season_key=season_key,
            segment=breed,
            metrics=rows,
            key_fn=_rank_key_performance,
            build_run_id=build_run_id,
            metric_primary="performance_rating",
        )

    # Rebuild temporary metrics for other segments from starts
    def metrics_for(predicate, segment_label: str, category: str) -> int:
        grouped: dict[int, list[StartRec]] = defaultdict(list)
        for s in starts:
            if predicate(s):
                grouped[s.horse_id].append(s)
        if not grouped:
            return 0
        max_earn = max(
            (sum(x.prize for x in lst) for lst in grouped.values()),
            default=0.0,
        )
        ms: list[AnlHorseMetrics] = []
        for hid, lst in grouped.items():
            m = _compute_horse_metrics(
                hid,
                lst,
                scope=scope,
                season_key=season_key,
                breed="*",
                max_earnings=max_earn or 1.0,
            )
            if m:
                ms.append(m)
        return _add_ranking_rows(
            session,
            category=category,
            scope=scope,
            season_key=season_key,
            segment=segment_label,
            metrics=ms,
            key_fn=_rank_key_performance,
            build_run_id=build_run_id,
        )

    # Age bands
    age_groups: dict[str, list[StartRec]] = defaultdict(list)
    for s in starts:
        band = age_band(age_years(s.birthdate, s.race_date))
        age_groups[band].append(s)
    for band, lst in age_groups.items():
        if band == "unknown":
            continue
        written += metrics_for(lambda s, b=band: age_band(age_years(s.birthdate, s.race_date)) == b, band, "best_by_age")

    # Class
    classes = {parse_race_class(s.race_name) for s in starts}
    for cls in classes:
        if cls in {"unknown", "other"}:
            continue
        written += metrics_for(
            lambda s, c=cls: parse_race_class(s.race_name) == c,
            cls,
            "best_by_class",
        )

    # Distance buckets
    for bucket in ("sprint", "mile", "mid", "staying"):
        written += metrics_for(
            lambda s, b=bucket: distance_bucket(s.distance) == b,
            bucket,
            "best_by_distance",
        )

    # Track condition / weather
    goings = {s.track_condition for s in starts if s.track_condition}
    for g in goings:
        written += metrics_for(
            lambda s, gg=g: s.track_condition == gg,
            g,
            "best_by_track_condition",
        )
    weathers = {s.weather_category for s in starts if s.weather_category}
    for w in weathers:
        written += metrics_for(
            lambda s, ww=w: s.weather_category == ww,
            w,
            "best_by_weather",
        )

    # Young horses (2yo/3yo)
    written += metrics_for(
        lambda s: age_band(age_years(s.birthdate, s.race_date)) in {"2yo", "3yo"},
        "2-3yo",
        "best_young",
    )
    return written


def build_analytics(
    session: Session,
    *,
    racecourse_code: str | None = None,
    top_n: int = 25,
) -> dict[str, Any]:
    """Rebuild all analytics tables + SQL convenience views."""
    run = AnlBuildRun(
        status="running",
        builder_version=BUILDER_VERSION,
        params_json={"racecourse_code": racecourse_code, "top_n": top_n},
    )
    session.add(run)
    session.flush()

    try:
        session.execute(delete(AnlRanking))
        session.execute(delete(AnlHorseMetrics))
        session.execute(delete(AnlSeason))
        session.flush()

        seasons = discover_seasons(session, racecourse_code=racecourse_code)
        for s in seasons:
            session.add(
                AnlSeason(
                    season_key=s.season_key,
                    racecourse_code=s.racecourse_code,
                    label=s.label,
                    start_date=s.start_date,
                    end_date=s.end_date,
                    is_completed=s.is_completed,
                    is_latest_completed=s.is_latest_completed,
                    race_days=s.race_days,
                    heats=s.heats,
                    meta_json={"builder_version": BUILDER_VERSION},
                )
            )
        session.flush()

        all_starts = _load_starts(session)
        if racecourse_code:
            all_starts = [s for s in all_starts if s.racecourse_code == racecourse_code]

        rows_written = 0
        now = datetime.now(timezone.utc)

        def build_scope(scope: str, season: SeasonCluster | None) -> int:
            nonlocal rows_written
            season_key = season.season_key if season else "*"
            scoped = _filter_scope(all_starts, season=season)
            if not scoped:
                return 0

            breeds = sorted({s.breed for s in scoped if s.breed}) or ["*"]
            # Always also compute breed="*" (all breeds combined)
            breed_keys = ["*"] + [b for b in breeds if b != "*"]

            local_metrics: list[AnlHorseMetrics] = []
            for breed in breed_keys:
                subset = _filter_scope(scoped, season=None, breed=None if breed == "*" else breed)
                # season already applied in scoped
                if breed != "*":
                    subset = [s for s in scoped if s.breed == breed]
                by_horse: dict[int, list[StartRec]] = defaultdict(list)
                for s in subset:
                    by_horse[s.horse_id].append(s)
                max_earn = max(
                    (sum(x.prize for x in lst) for lst in by_horse.values()),
                    default=0.0,
                )
                for hid, lst in by_horse.items():
                    m = _compute_horse_metrics(
                        hid,
                        lst,
                        scope=scope,
                        season_key=season_key,
                        breed=breed,
                        max_earnings=max_earn or 1.0,
                    )
                    if m is None:
                        continue
                    m.build_run_id = run.id
                    m.computed_at = now
                    local_metrics.append(m)
                    session.add(m)
                    rows_written += 1
            session.flush()

            # Assign rankings within breed=*
            all_breed = [m for m in local_metrics if m.breed == "*"]
            all_breed.sort(key=_rank_key_performance)
            for i, m in enumerate(all_breed, 1):
                if scope == "season":
                    m.season_ranking = i
                else:
                    m.career_ranking = i
            for breed in breeds:
                bred = [m for m in local_metrics if m.breed == breed]
                bred.sort(key=_rank_key_performance)
                for i, m in enumerate(bred, 1):
                    m.breed_ranking = i
            session.flush()

            # Leaderboards
            rows_written += _add_ranking_rows(
                session,
                category="best_season" if scope == "season" else "best_career",
                scope=scope,
                season_key=season_key,
                segment="*",
                metrics=all_breed,
                key_fn=_rank_key_performance,
                build_run_id=run.id,
                limit=top_n,
            )
            rows_written += _add_ranking_rows(
                session,
                category="most_successful",
                scope=scope,
                season_key=season_key,
                segment="*",
                metrics=all_breed,
                key_fn=_rank_key_success,
                build_run_id=run.id,
                limit=top_n,
                metric_primary="wins",
            )
            rows_written += _add_ranking_rows(
                session,
                category="most_consistent",
                scope=scope,
                season_key=season_key,
                segment="*",
                metrics=[m for m in all_breed if (m.starts or 0) >= 2],
                key_fn=_rank_key_consistent,
                build_run_id=run.id,
                limit=top_n,
                metric_primary="consistency_score",
                min_starts=2,
            )
            improving = [m for m in all_breed if m.is_improving]
            declining = [m for m in all_breed if m.is_declining]
            rows_written += _add_ranking_rows(
                session,
                category="improving",
                scope=scope,
                season_key=season_key,
                segment="*",
                metrics=improving,
                key_fn=lambda m: (-(m.improvement_trend or 0), -(m.form_score_5 or 0)),
                build_run_id=run.id,
                limit=top_n,
                metric_primary="improvement_trend",
            )
            rows_written += _add_ranking_rows(
                session,
                category="declining",
                scope=scope,
                season_key=season_key,
                segment="*",
                metrics=declining,
                key_fn=lambda m: (-(m.decline_trend or 0), (m.form_score_5 or 0)),
                build_run_id=run.id,
                limit=top_n,
                metric_primary="decline_trend",
            )

            rows_written += _entity_rankings_from_starts(
                session,
                starts=scoped,
                scope=scope,
                season_key=season_key,
                build_run_id=run.id,
                limit=top_n,
            )
            rows_written += _segment_rankings(
                session,
                metrics=local_metrics,
                starts=scoped,
                scope=scope,
                season_key=season_key,
                build_run_id=run.id,
            )
            return len(all_breed)

        # Career scope
        build_scope("career", None)

        # Each completed season + latest incomplete if only one cluster
        target_seasons = [s for s in seasons if s.is_latest_completed]
        if not target_seasons:
            # fall back to latest cluster per course
            latest_by_course: dict[str | None, SeasonCluster] = {}
            for s in seasons:
                prev = latest_by_course.get(s.racecourse_code)
                if prev is None or s.end_date > prev.end_date:
                    latest_by_course[s.racecourse_code] = s
            target_seasons = list(latest_by_course.values())
        for season in target_seasons:
            build_scope("season", season)

        create_analytics_views(session)

        run.status = "success"
        run.rows_written = rows_written
        run.finished_at = datetime.now(timezone.utc)
        session.flush()
        stats = {
            "status": "success",
            "rows_written": rows_written,
            "seasons": len(seasons),
            "season_targets": len(target_seasons),
            "build_run_id": run.id,
        }
        logger.info("Analytics build {}", stats)
        return stats
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)[:1000]
        run.finished_at = datetime.now(timezone.utc)
        session.flush()
        logger.exception("Analytics build failed: {}", exc)
        raise
