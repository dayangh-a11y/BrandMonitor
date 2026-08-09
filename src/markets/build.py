"""Build & query market analytics for races / matchups."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.markets.answer import MarketAnswer, format_market_answer
from src.markets.context import load_field_for_race, load_runner_by_horse_id
from src.markets.h2h import analyze_h2h_market, build_pairwise_matrix
from src.markets.matchup import (
    analyze_matchup,
    parse_matchup_query,
    resolve_horse_by_name,
)
from src.markets.models import AnlMarketMatchup, AnlMarketPairwise, AnlMarketRace
from src.markets.place import analyze_place_market
from src.markets.risk import analyze_risk_market
from src.markets.surprise import analyze_surprise_market
from src.markets.value import analyze_value_market
from src.markets.win import analyze_win_market
from src.markets.without_favorite import analyze_without_favorite
from src.warehouse.models import WhRace


MARKET_ANALYZERS = {
    "win": analyze_win_market,
    "place": analyze_place_market,
    "without_favorite": analyze_without_favorite,
    "value": analyze_value_market,
    "risk": analyze_risk_market,
    "surprise": analyze_surprise_market,
}


def analyze_race_markets(
    session: Session,
    race_id: int,
    *,
    persist: bool = True,
    include_h2h: bool = True,
) -> dict[str, MarketAnswer]:
    race, field = load_field_for_race(session, race_id)
    if race is None or not field:
        empty = MarketAnswer(
            market="ALL",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Race not found or empty field"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="n/a",
        )
        return {"error": empty}

    answers: dict[str, MarketAnswer] = {}
    for key, fn in MARKET_ANALYZERS.items():
        answers[key] = fn(field)

    if include_h2h:
        answers["head_to_head"] = analyze_h2h_market(
            field,
            session=session,
            race_distance=race.distance,
            race_track=race.racecourse_code,
        )

    if persist:
        _persist_race(session, race_id, answers, field, race)
    return answers


def _persist_race(
    session: Session,
    race_id: int,
    answers: dict[str, MarketAnswer],
    field,
    race: WhRace,
) -> None:
    session.execute(delete(AnlMarketPairwise).where(AnlMarketPairwise.race_id == race_id))
    session.execute(delete(AnlMarketRace).where(AnlMarketRace.race_id == race_id))

    h2h = answers.get("head_to_head")
    pairs = 0
    if h2h and isinstance(h2h.prediction, dict):
        matrix = h2h.prediction.get("matrix") or []
        pairs = len(matrix)
        for row in matrix:
            session.add(
                AnlMarketPairwise(
                    race_id=race_id,
                    horse_a_id=row["horse_a_id"],
                    horse_a_name=row["horse_a"],
                    horse_b_id=row["horse_b_id"],
                    horse_b_name=row["horse_b"],
                    a_ahead_prob=row["a_finishes_ahead_of_b"],
                    b_ahead_prob=row["b_finishes_ahead_of_a"],
                    expected_finish_gap=row.get("expected_finishing_gap"),
                    expected_margin=row.get("expected_margin"),
                    confidence=row.get("confidence"),
                    sample_size=row.get("sample_size") or 0,
                    payload_json=row,
                )
            )

    session.add(
        AnlMarketRace(
            race_id=race_id,
            win_json=answers["win"].to_dict() if "win" in answers else None,
            place_json=answers["place"].to_dict() if "place" in answers else None,
            without_favorite_json=(
                answers["without_favorite"].to_dict()
                if "without_favorite" in answers
                else None
            ),
            value_json=answers["value"].to_dict() if "value" in answers else None,
            risk_json=answers["risk"].to_dict() if "risk" in answers else None,
            surprise_json=answers["surprise"].to_dict() if "surprise" in answers else None,
            h2h_pairs=pairs,
            meta_json={
                "field_size": len(field),
                "distance": race.distance,
                "track": race.racecourse_code,
            },
        )
    )
    session.flush()
    logger.info("Market analytics persisted race_id={} pairs={}", race_id, pairs)


def build_markets_for_course(
    session: Session,
    *,
    racecourse_code: str | None = None,
    limit: int | None = 50,
    include_h2h: bool = True,
) -> dict[str, Any]:
    q = select(WhRace.id).order_by(WhRace.race_date.desc())
    if racecourse_code:
        q = q.where(WhRace.racecourse_code == racecourse_code)
    if limit:
        q = q.limit(limit)
    ids = list(session.scalars(q).all())
    ok = 0
    for rid in ids:
        analyze_race_markets(session, rid, persist=True, include_h2h=include_h2h)
        ok += 1
    return {"races": ok, "include_h2h": include_h2h}


def run_matchup_query(
    session: Session,
    query: str,
    *,
    persist: bool = True,
) -> MarketAnswer:
    parsed = parse_matchup_query(query)
    if not parsed:
        return MarketAnswer(
            market="MATCHUP",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=[f"Could not parse matchup from: {query!r}"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="Direct Matchup",
            warnings=["Expected format: «A یا B» or «A vs B»"],
        )
    name_a, name_b = parsed
    ha = resolve_horse_by_name(session, name_a)
    hb = resolve_horse_by_name(session, name_b)
    if ha is None or hb is None:
        return MarketAnswer(
            market="MATCHUP",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=[
                f"Unresolved names: a={name_a!r}→{ha}, b={name_b!r}→{hb}",
            ],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="Direct Matchup",
            warnings=["Horse name resolution failed"],
        )
    ra = load_runner_by_horse_id(session, ha.id)
    rb = load_runner_by_horse_id(session, hb.id)
    if ra is None or rb is None:
        return MarketAnswer(
            market="MATCHUP",
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Could not load runner metrics"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market="Direct Matchup",
        )
    answer = analyze_matchup(ra, rb, session=session)
    if persist:
        session.add(
            AnlMarketMatchup(
                horse_a_id=ha.id,
                horse_a_name=ha.name,
                horse_b_id=hb.id,
                horse_b_name=hb.name,
                query_text=query,
                p_a_ahead=float(answer.prediction["probability_a_finishes_ahead"]),
                p_b_ahead=float(answer.prediction["probability_b_finishes_ahead"]),
                confidence=answer.confidence,
                answer_json=answer.to_dict(),
            )
        )
        session.flush()
    return answer


def analyze_single_market(
    session: Session,
    race_id: int,
    market: str,
) -> MarketAnswer:
    key = market.lower().strip().replace("-", "_").replace(" ", "_")
    aliases = {
        "h2h": "head_to_head",
        "headtohead": "head_to_head",
        "withoutfavorite": "without_favorite",
        "wo_favorite": "without_favorite",
    }
    key = aliases.get(key, key)
    race, field = load_field_for_race(session, race_id)
    if race is None or not field:
        return MarketAnswer(
            market=key.upper(),
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=["Race not found or empty"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market=key,
        )
    if key == "head_to_head":
        return analyze_h2h_market(
            field,
            session=session,
            race_distance=race.distance,
            race_track=race.racecourse_code,
        )
    fn = MARKET_ANALYZERS.get(key)
    if not fn:
        return MarketAnswer(
            market=key.upper(),
            prediction=None,
            confidence="Very Low",
            confidence_score=0.0,
            reasons=[f"Unknown market: {market}"],
            metrics_used=[],
            sample_size=0,
            data_quality="insufficient",
            applicable_market=market,
            warnings=[
                "Choose from: "
                + ", ".join(sorted(set(MARKET_ANALYZERS) | {"head_to_head"}))
            ],
        )
    return fn(field)
