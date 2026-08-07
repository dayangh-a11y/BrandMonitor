"""Build prediction-market analytics + entity metrics from warehouse."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.prediction_market.metrics import (
    crowd_bias,
    entity_scores_from_starts,
    favorite_failure_score,
    normalized_confidence,
    prediction_difficulty,
    shock_score,
    spearman_accuracy,
    surprise_index,
    upset_score,
)
from src.prediction_market.models import (
    AnlPredictionBuildRun,
    AnlPredictionEntityMetrics,
    AnlPredictionRaceMetrics,
    WhPredictionEntry,
    WhPredictionEvent,
    WhPredictionReward,
    WhPredictionStatistic,
    WhPredictionWinner,
)
from src.prediction_market.views import create_prediction_views
from src.warehouse.models import WhHorsePedigree, WhOwner, WhRaceResult, WhTrainer

BUILDER_VERSION = "1.0.0"


def build_prediction_analytics(session: Session) -> dict[str, Any]:
    run = AnlPredictionBuildRun(
        status="running",
        builder_version=BUILDER_VERSION,
        params_json={},
    )
    session.add(run)
    session.flush()

    try:
        session.execute(delete(AnlPredictionRaceMetrics))
        session.execute(delete(AnlPredictionEntityMetrics))
        session.flush()

        events = session.scalars(select(WhPredictionEvent)).all()
        entries = session.scalars(select(WhPredictionEntry)).all()
        stats_rows = session.scalars(select(WhPredictionStatistic)).all()
        rewards = session.scalars(select(WhPredictionReward)).all()
        winners = session.scalars(select(WhPredictionWinner)).all()

        entries_by_event: dict[int, list[WhPredictionEntry]] = defaultdict(list)
        for e in entries:
            if e.market_type == "WIN_MARKET":
                entries_by_event[e.event_id].append(e)
        stats_by_event = {s.event_id: s for s in stats_rows if s.stat_type == "crowd"}
        rewards_by_event: dict[int, list[WhPredictionReward]] = defaultdict(list)
        for r in rewards:
            if r.event_id is not None:
                rewards_by_event[r.event_id].append(r)
        winners_by_event: dict[int, list[WhPredictionWinner]] = defaultdict(list)
        for w in winners:
            winners_by_event[w.event_id].append(w)

        horse_starts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        jockey_starts: dict[str, list[dict[str, Any]]] = defaultdict(list)

        # Optional joins for trainer/owner/sire via warehouse race results
        trainer_by_horse_race: dict[tuple[int, int], str] = {}
        owner_by_horse_race: dict[tuple[int, int], str] = {}
        trainers = {t.id: t.name for t in session.scalars(select(WhTrainer)).all()}
        owners = {o.id: o.name for o in session.scalars(select(WhOwner)).all()}
        sires = {
            p.horse_id: p.sire_name
            for p in session.scalars(select(WhHorsePedigree)).all()
            if p.sire_name
        }
        for res in session.scalars(select(WhRaceResult)).all():
            if res.horse_id is None:
                continue
            if res.trainer_id and res.trainer_id in trainers:
                trainer_by_horse_race[(res.race_id, res.horse_id)] = trainers[res.trainer_id]
            if res.owner_id and res.owner_id in owners:
                owner_by_horse_race[(res.race_id, res.horse_id)] = owners[res.owner_id]

        trainer_starts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        owner_starts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        sire_starts: dict[str, list[dict[str, Any]]] = defaultdict(list)

        rows_written = 0
        for ev in events:
            ents = entries_by_event.get(ev.id, [])
            st = stats_by_event.get(ev.id)
            dist = (st.distribution_json or {}) if st else {}
            probs = {
                int(k): float(v)
                for k, v in (dist.get("probs") or {}).items()
                if str(k).isdigit()
            }
            if not probs:
                probs = {
                    e.cloth_number: float(e.implied_probability)
                    for e in ents
                    if e.implied_probability is not None and not e.scratched
                }

            actual = {
                e.cloth_number: int(e.actual_rank)
                for e in ents
                if e.actual_rank is not None and e.actual_rank > 0
            }
            crowd_ranks = {
                e.cloth_number: int(e.crowd_rank)
                for e in ents
                if e.crowd_rank is not None
            }
            if not crowd_ranks and probs:
                from src.prediction_market.metrics import rank_by_score

                crowd_ranks = rank_by_score(probs)

            field_size = ev.field_size or len(probs) or len(actual)
            fav_cloth = st.favorite_cloth if st else None
            if fav_cloth is None and crowd_ranks:
                fav_cloth = min(crowd_ranks, key=crowd_ranks.get)
            fav_name = st.favorite_name if st else None
            if fav_name is None and fav_cloth is not None:
                fav_name = next(
                    (e.horse_name for e in ents if e.cloth_number == fav_cloth), None
                )

            fav_prob = probs.get(fav_cloth) if fav_cloth is not None else None
            conf = normalized_confidence(probs) if probs else 0.0
            winner_cloth = next((c for c, r in actual.items() if r == 1), None)
            winner_crowd_rank = crowd_ranks.get(winner_cloth) if winner_cloth else None
            fav_actual = actual.get(fav_cloth) if fav_cloth is not None else None

            surp = (
                surprise_index(winner_crowd_rank, 1, field_size)
                if winner_crowd_rank is not None
                else 0.0
            )
            # Also mean absolute residual across field
            if crowd_ranks and actual:
                residuals = [
                    surprise_index(crowd_ranks.get(c), actual.get(c), field_size)
                    for c in actual
                    if c in crowd_ranks
                ]
                if residuals:
                    surp = mean(residuals)

            upset = upset_score(winner_crowd_rank, field_size)
            fav_fail = favorite_failure_score(fav_actual, field_size)
            diff = prediction_difficulty(probs)
            accuracy = spearman_accuracy(crowd_ranks, actual) if crowd_ranks and actual else 0.0
            bias = crowd_bias(probs, actual)
            shock = shock_score(
                favorite_failure=fav_fail, upset=upset, crowd_accuracy_pct=accuracy
            )

            ev_rewards = rewards_by_event.get(ev.id, [])
            total_prize = sum(r.total_prize or 0.0 for r in ev_rewards)
            prize_vals = [r.total_prize for r in ev_rewards if r.total_prize is not None]
            avg_prize = mean(prize_vals) if prize_vals else None
            participants = st.total_participants if st else None
            win_rows = [w for w in winners_by_event.get(ev.id, []) if w.place == 1]
            winners_count = len({(w.pool_type, w.cloth_number) for w in win_rows})
            # Winning prediction % ≈ favorite win share of survey if available
            winning_pct = None
            if winner_cloth is not None and probs:
                winning_pct = probs.get(winner_cloth, 0.0) * 100.0

            pred_gap = None
            if fav_cloth is not None and fav_actual is not None:
                pred_gap = float(1 - fav_actual)  # negative if favorite finished worse

            features = {
                "crowd_confidence": round(conf, 6),
                "crowd_probability": round(fav_prob, 6) if fav_prob is not None else None,
                "prediction_gap": pred_gap,
                "surprise_index": round(surp, 6),
                "public_bias": round(bias, 6),
                "favorite_rank": crowd_ranks.get(fav_cloth) if fav_cloth is not None else None,
                "favorite_failed": 1 if fav_actual is not None and fav_actual != 1 else 0,
                "upset_score": round(upset, 6),
                "prediction_entropy": round(st.entropy, 6) if st and st.entropy is not None else None,
                "prediction_variance": round(st.variance, 6)
                if st and st.variance is not None
                else None,
            }

            session.add(
                AnlPredictionRaceMetrics(
                    event_id=ev.id,
                    race_date=ev.race_date,
                    track_name=ev.track_name,
                    field_size=field_size,
                    crowd_favorite_cloth=fav_cloth,
                    crowd_favorite_name=fav_name,
                    crowd_confidence=round(conf * 100, 3),
                    crowd_win_probability=round(fav_prob * 100, 3) if fav_prob is not None else None,
                    prediction_distribution_json={str(k): v for k, v in probs.items()},
                    surprise_index=round(surp, 3),
                    upset_score=round(upset, 3),
                    favorite_failure_score=round(fav_fail, 3),
                    prediction_difficulty=round(diff, 3),
                    crowd_accuracy=round(accuracy, 3),
                    crowd_bias=round(bias, 6),
                    shock_score=shock,
                    difficulty_score=round(diff, 3),
                    prediction_accuracy=round(accuracy, 3),
                    participants=participants,
                    winners_count=winners_count,
                    total_prize_pool=total_prize,
                    average_prize=avg_prize,
                    winning_prediction_pct=round(winning_pct, 3) if winning_pct is not None else None,
                    crowd_probability=features["crowd_probability"],
                    prediction_gap=pred_gap,
                    public_bias=features["public_bias"],
                    favorite_rank=features["favorite_rank"],
                    favorite_failed=features["favorite_failed"],
                    prediction_entropy=features["prediction_entropy"],
                    prediction_variance=features["prediction_variance"],
                    features_json=features,
                    explain_json={
                        "winner_cloth": winner_cloth,
                        "winner_crowd_rank": winner_crowd_rank,
                        "favorite_actual_rank": fav_actual,
                        "distribution_source": dist.get("source"),
                    },
                    computed_at=datetime.now(timezone.utc),
                )
            )
            rows_written += 1

            # Entity start records
            for e in ents:
                if e.scratched or e.actual_rank is None:
                    continue
                rec = {
                    "crowd_rank": e.crowd_rank,
                    "actual_rank": e.actual_rank,
                    "crowd_prob": e.implied_probability,
                    "was_favorite": bool(fav_cloth is not None and e.cloth_number == fav_cloth),
                    "won": e.actual_rank == 1,
                    "field_size": field_size,
                    "surprise": abs((e.crowd_rank or e.actual_rank) - e.actual_rank),
                }
                key = e.source_horse_id or e.horse_name or str(e.cloth_number)
                horse_starts[str(key)].append({**rec, "name": e.horse_name, "id": e.wh_horse_id})
                if e.jockey_name:
                    jockey_starts[e.jockey_name].append({**rec, "name": e.jockey_name})
                if e.wh_horse_id and ev.wh_race_id:
                    tname = trainer_by_horse_race.get((ev.wh_race_id, e.wh_horse_id))
                    oname = owner_by_horse_race.get((ev.wh_race_id, e.wh_horse_id))
                    if tname:
                        trainer_starts[tname].append({**rec, "name": tname})
                    if oname:
                        owner_starts[oname].append({**rec, "name": oname})
                    sire = sires.get(e.wh_horse_id)
                    if sire:
                        sire_starts[sire].append({**rec, "name": sire})

        def persist_entities(etype: str, bucket: dict[str, list[dict[str, Any]]]) -> int:
            n = 0
            for key, starts in bucket.items():
                scores = entity_scores_from_starts(starts)
                name = next((s.get("name") for s in starts if s.get("name")), key)
                eid = next((s.get("id") for s in starts if s.get("id")), None)
                session.add(
                    AnlPredictionEntityMetrics(
                        entity_type=etype,
                        entity_key=key,
                        entity_id=eid if isinstance(eid, int) else None,
                        entity_name=name,
                        scope="career",
                        season_key="*",
                        starts=len(starts),
                        public_popularity_score=scores.get("public_popularity_score"),
                        public_trust_score=scores.get("public_trust_score"),
                        overrated_score=scores.get("overrated_score"),
                        underrated_score=scores.get("underrated_score"),
                        unpredictability_score=scores.get("unpredictability_score"),
                        surprise_frequency=scores.get("surprise_frequency"),
                        favorite_failure_frequency=scores.get("favorite_failure_frequency"),
                        upset_victory_frequency=scores.get("upset_victory_frequency"),
                        avg_prediction_rank=scores.get("avg_prediction_rank"),
                        avg_actual_rank=scores.get("avg_actual_rank"),
                        prediction_gap=scores.get("prediction_gap"),
                        metrics_json=scores,
                        computed_at=datetime.now(timezone.utc),
                    )
                )
                n += 1
            return n

        rows_written += persist_entities("horse", horse_starts)
        rows_written += persist_entities("jockey", jockey_starts)
        rows_written += persist_entities("trainer", trainer_starts)
        rows_written += persist_entities("owner", owner_starts)
        rows_written += persist_entities("sire", sire_starts)

        create_prediction_views(session)

        run.status = "success"
        run.rows_written = rows_written
        run.finished_at = datetime.now(timezone.utc)
        session.flush()
        out = {
            "status": "success",
            "rows_written": rows_written,
            "events": len(events),
            "build_run_id": run.id,
        }
        logger.info("prediction analytics {}", out)
        return out
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)[:1000]
        run.finished_at = datetime.now(timezone.utc)
        session.flush()
        logger.exception("prediction analytics failed")
        raise
