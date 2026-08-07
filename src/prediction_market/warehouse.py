"""Normalize Raw prediction snapshots → warehouse tables."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.prediction_market.metrics import (
    implied_probs_from_odds,
    pick_survey_counts,
    pick_win_odds_map,
    probs_from_counts,
    rank_by_score,
)
from src.prediction_market.models import (
    RawPredictionSnapshot,
    WhPredictionEntry,
    WhPredictionEvent,
    WhPredictionReward,
    WhPredictionStatistic,
    WhPredictionWinner,
)
from src.warehouse.models import WhHorse, WhRace


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "" or value == "0001-01-01T00:00:00Z":
        return None
    if isinstance(value, datetime):
        return value
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    dt = _parse_dt(value)
    return dt.date() if dt else None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_snapshots(session: Session, kind: str) -> dict[str, RawPredictionSnapshot]:
    rows = session.scalars(
        select(RawPredictionSnapshot)
        .where(RawPredictionSnapshot.snapshot_kind == kind)
        .order_by(RawPredictionSnapshot.captured_at.desc())
    ).all()
    out: dict[str, RawPredictionSnapshot] = {}
    for row in rows:
        if row.source_key not in out:
            out[row.source_key] = row
    return out


def _link_wh_race(
    session: Session,
    *,
    day_external_id: str | None,
    race_number: int | None,
    race_date: date | None,
    track_name: str | None,
) -> int | None:
    if day_external_id and race_number is not None:
        # source_url / week embeds external week id
        q = (
            select(WhRace)
            .where(WhRace.race_number == race_number)
            .where(
                (WhRace.source_url.contains(day_external_id))
                | (WhRace.source_race_id.contains(day_external_id[:8]))
            )
        )
        if race_date:
            q = q.where(WhRace.race_date == race_date)
        row = session.scalars(q.limit(1)).first()
        if row:
            return row.id
    if race_date and race_number is not None and track_name:
        row = session.scalars(
            select(WhRace)
            .where(
                WhRace.race_date == race_date,
                WhRace.race_number == race_number,
                WhRace.track.contains(track_name[:4]),
            )
            .limit(1)
        ).first()
        if row:
            return row.id
    return None


def _link_horse(session: Session, source_horse_id: str | None, name: str | None) -> int | None:
    """Resolve to warehouse horse via Identity Engine (never exact name alone)."""
    from src.identity import HorseQuery, resolve_horse
    from src.identity.resolve import warehouse_ids_for_horse

    hits = resolve_horse(
        session,
        HorseQuery(name=name, source_horse_id=source_horse_id),
        limit=1,
    )
    if hits:
        if hits[0].warehouse_horse_id:
            return hits[0].warehouse_horse_id
        wh_ids = warehouse_ids_for_horse(session, hits[0].horse_id)
        if wh_ids:
            return wh_ids[0]

    if source_horse_id:
        row = session.scalar(
            select(WhHorse).where(WhHorse.source_horse_id == source_horse_id).limit(1)
        )
        if row:
            return row.id
    return None


def build_prediction_warehouse(session: Session) -> dict[str, Any]:
    """Rebuild warehouse prediction tables from latest Raw snapshots."""
    session.execute(delete(WhPredictionWinner))
    session.execute(delete(WhPredictionEntry))
    session.execute(delete(WhPredictionStatistic))
    session.execute(delete(WhPredictionReward))
    session.execute(delete(WhPredictionEvent))
    session.flush()

    cards = _latest_snapshots(session, "racecard")
    odds_map = _latest_snapshots(session, "odds")
    survey_map = _latest_snapshots(session, "survey")

    events: dict[str, WhPredictionEvent] = {}
    stats = {"events": 0, "entries": 0, "statistics": 0, "rewards": 0, "winners": 0}

    for day_key, snap in cards.items():
        payload = snap.payload_json or {}
        data = payload.get("data") if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            continue
        day = data.get("day") if isinstance(data.get("day"), dict) else {}
        track = day.get("track") if isinstance(day.get("track"), dict) else {}
        race_date = _parse_date(day.get("date"))
        track_name = track.get("name") or None
        track_code = str(track.get("code") or day.get("track_id") or "") or None
        day_external_id = day.get("external_id")
        source_day_id = str(day.get("id") or day_key)

        races = data.get("races") if isinstance(data.get("races"), list) else []
        for race in races:
            if not isinstance(race, dict) or race.get("id") is None:
                continue
            sid = str(race["id"])
            race_number = race.get("number")
            try:
                race_number_i = int(race_number) if race_number is not None else None
            except (TypeError, ValueError):
                race_number_i = None
            horses = race.get("race_horses") if isinstance(race.get("race_horses"), list) else []
            active = [
                h
                for h in horses
                if isinstance(h, dict) and not bool(h.get("scratched"))
            ]
            ev = WhPredictionEvent(
                source="mosharekat",
                source_event_id=sid,
                source_day_id=source_day_id,
                day_external_id=str(day_external_id) if day_external_id else None,
                race_number=race_number_i,
                race_date=race_date,
                track_name=track_name,
                track_code=track_code,
                status=str(race.get("status") or "") or None,
                closed_at=_parse_dt(race.get("closed_at")),
                start_at=_parse_dt(race.get("start_at")),
                field_size=len(active) or len(horses),
                wh_race_id=_link_wh_race(
                    session,
                    day_external_id=str(day_external_id) if day_external_id else None,
                    race_number=race_number_i,
                    race_date=race_date,
                    track_name=track_name,
                ),
                meta_json={"raw_race_keys": sorted(race.keys()), "day_name": day.get("name")},
                updated_at=datetime.now(timezone.utc),
            )
            session.add(ev)
            session.flush()
            events[sid] = ev
            stats["events"] += 1

            # Horse lookup for winners / entries
            horse_by_cloth: dict[int, dict[str, Any]] = {}
            for h in horses:
                if not isinstance(h, dict):
                    continue
                try:
                    cloth = int(h.get("number"))
                except (TypeError, ValueError):
                    continue
                horse_by_cloth[cloth] = h
                # Official finish winners from rank
                rank = h.get("rank")
                if rank is not None:
                    try:
                        place = int(rank)
                    except (TypeError, ValueError):
                        place = None
                    if place is not None and place > 0:
                        session.add(
                            WhPredictionWinner(
                                event_id=ev.id,
                                pool_type="OFFICIAL_FINISH",
                                cloth_number=cloth,
                                horse_name=h.get("horse_name"),
                                place=place,
                                wh_horse_id=_link_horse(
                                    session, h.get("external_id"), h.get("horse_name")
                                ),
                                raw_json=h,
                            )
                        )
                        stats["winners"] += 1

            # Odds + survey → entries
            win_odds: dict[int, float] = {}
            survey_counts: dict[int, int] = {}
            odds_snap = odds_map.get(sid)
            survey_snap = survey_map.get(sid)
            if odds_snap:
                win_odds = pick_win_odds_map(odds_snap.payload_json)
            if survey_snap:
                survey_counts = pick_survey_counts(survey_snap.payload_json)

            survey_probs = probs_from_counts(survey_counts) if survey_counts else {}
            odds_probs = implied_probs_from_odds(win_odds) if win_odds else {}
            primary_probs = survey_probs or odds_probs
            crowd_ranks = rank_by_score(primary_probs, descending=True) if primary_probs else {}

            cloths = set(horse_by_cloth) | set(win_odds) | set(survey_counts)
            for cloth in cloths:
                h = horse_by_cloth.get(cloth, {})
                actual = h.get("rank")
                try:
                    actual_i = int(actual) if actual is not None else None
                except (TypeError, ValueError):
                    actual_i = None
                odd = win_odds.get(cloth)
                sc = survey_counts.get(cloth)
                # Store win-market entry
                session.add(
                    WhPredictionEntry(
                        event_id=ev.id,
                        cloth_number=cloth,
                        horse_name=h.get("horse_name"),
                        source_horse_id=h.get("external_id"),
                        jockey_name=h.get("jockey_name") or None,
                        scratched=bool(h.get("scratched")),
                        actual_rank=actual_i,
                        market_type="WIN_MARKET",
                        odd=odd,
                        survey_count=sc,
                        implied_probability=primary_probs.get(cloth),
                        crowd_rank=crowd_ranks.get(cloth),
                        wh_horse_id=_link_horse(session, h.get("external_id"), h.get("horse_name")),
                        snapshot_at=(odds_snap or survey_snap or snap).captured_at,
                        is_pre_race_snapshot=bool(
                            (odds_snap and odds_snap.is_pre_race)
                            or (survey_snap and survey_snap.is_pre_race)
                            or snap.is_pre_race
                        ),
                        raw_json={
                            "horse": h or None,
                            "odd": odd,
                            "survey_count": sc,
                        },
                    )
                )
                stats["entries"] += 1

            # Statistics row
            fav_cloth = next(iter(crowd_ranks), None)
            # favorite = crowd_rank 1
            for c, rnk in crowd_ranks.items():
                if rnk == 1:
                    fav_cloth = c
                    break
            fav_name = (horse_by_cloth.get(fav_cloth) or {}).get("horse_name") if fav_cloth else None
            from src.prediction_market.metrics import entropy, normalized_confidence
            from statistics import pstdev

            ent = entropy(primary_probs.values()) if primary_probs else None
            var = pstdev(primary_probs.values()) if len(primary_probs) >= 2 else 0.0
            session.add(
                WhPredictionStatistic(
                    event_id=ev.id,
                    stat_type="crowd",
                    total_participants=int(sum(survey_counts.values())) if survey_counts else None,
                    favorite_cloth=fav_cloth,
                    favorite_name=fav_name,
                    favorite_probability=primary_probs.get(fav_cloth) if fav_cloth else None,
                    entropy=ent,
                    variance=var,
                    distribution_json={
                        "probs": {str(k): v for k, v in primary_probs.items()},
                        "survey_counts": {str(k): v for k, v in survey_counts.items()},
                        "win_odds": {str(k): v for k, v in win_odds.items()},
                        "source": "survey" if survey_probs else ("win_odds" if odds_probs else "none"),
                        "confidence": normalized_confidence(primary_probs),
                    },
                    snapshot_at=(survey_snap or odds_snap or snap).captured_at,
                    is_pre_race_snapshot=bool(snap.is_pre_race),
                    raw_json={
                        "survey": survey_snap.payload_json if survey_snap else None,
                        "odds_keys": list((odds_snap.payload_json or {}).keys()) if odds_snap else None,
                    },
                )
            )
            stats["statistics"] += 1

        # Rewards (pools)
        pools = data.get("pools") if isinstance(data.get("pools"), list) else []
        for pool in pools:
            if not isinstance(pool, dict) or pool.get("id") is None:
                continue
            race_id = pool.get("race_id")
            ev = events.get(str(race_id)) if race_id is not None else None
            reward = WhPredictionReward(
                source="mosharekat",
                source_pool_id=str(pool["id"]),
                event_id=ev.id if ev else None,
                source_day_id=source_day_id,
                pool_type=str(pool.get("type") or "") or None,
                status=str(pool.get("status") or "") or None,
                prize_status=str(pool.get("prize_status") or "") or None,
                ticket_price=_num(pool.get("price")),
                total_price=_num(pool.get("total_price")),
                total_prize=_num(pool.get("total_prize")),
                total_return=_num(pool.get("total_return")),
                share=_num(pool.get("share")),
                first_race_num=int(pool["first_race_num"])
                if pool.get("first_race_num") is not None
                else None,
                last_race_num=int(pool["last_race_num"])
                if pool.get("last_race_num") is not None
                else None,
                raw_json=pool,
                updated_at=datetime.now(timezone.utc),
            )
            session.add(reward)
            session.flush()
            stats["rewards"] += 1

            extra = pool.get("extra") if isinstance(pool.get("extra"), dict) else {}
            details = extra.get("odd_details") if isinstance(extra, dict) else None
            if isinstance(details, list) and ev is not None:
                for detail in details:
                    if not isinstance(detail, dict):
                        continue
                    nums = detail.get("horse_numbers") or detail.get("horses") or []
                    if not isinstance(nums, list):
                        nums = [nums]
                    for n in nums:
                        try:
                            cloth = int(n)
                        except (TypeError, ValueError):
                            continue
                        session.add(
                            WhPredictionWinner(
                                event_id=ev.id,
                                reward_id=reward.id,
                                pool_type=reward.pool_type,
                                cloth_number=cloth,
                                place=1,
                                odd_asli=_num(detail.get("odd_asli")),
                                odd_pardakhti=_num(detail.get("odd_pardakhti")),
                                prize_amount=reward.total_prize,
                                raw_json=detail,
                            )
                        )
                        stats["winners"] += 1

    session.flush()
    logger.info("prediction warehouse {}", stats)
    return stats
