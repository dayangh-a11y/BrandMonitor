"""Prediction market unit tests (offline)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from src.database.base import Base
from src.prediction_market.build import build_prediction_analytics
from src.prediction_market.metrics import (
    implied_probs_from_odds,
    pick_survey_counts,
    pick_win_odds_map,
    spearman_accuracy,
)
from src.prediction_market.models import (
    AnlPredictionEntityMetrics,
    AnlPredictionRaceMetrics,
    RawPredictionSnapshot,
    WhPredictionEvent,
)
from src.prediction_market.warehouse import build_prediction_warehouse


def test_odds_and_survey_parsers_are_schema_agnostic() -> None:
    odds = {
        "success": True,
        "data": {
            "odds": {
                "pishbar": {
                    "1": {"runnerId": 1, "odd": 2.0},
                    "2": {"runnerId": 2, "odd": 4.0},
                },
                "miyanbar": {"1": {"runnerId": 1, "odd": 1.2}},
            }
        },
    }
    win = pick_win_odds_map(odds)
    assert win[1] == 2.0 and win[2] == 4.0
    probs = implied_probs_from_odds(win)
    assert abs(probs[1] - 2 / 3) < 1e-9
    survey = {
        "data": {
            "race_id": 1,
            "statistics": [
                {"horse_num": 1, "count": 80},
                {"horse_num": 2, "count": 20},
            ],
        }
    }
    counts = pick_survey_counts(survey)
    assert counts == {1: 80, 2: 20}
    assert spearman_accuracy({1: 1, 2: 2}, {1: 1, 2: 2}) == 100.0


@pytest.fixture()
def mem_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    import src.analytics.models  # noqa: F401
    import src.crawler.models  # noqa: F401
    import src.crawler.stats  # noqa: F401
    import src.database.features  # noqa: F401
    import src.database.raw  # noqa: F401
    import src.features.models  # noqa: F401
    import src.prediction_market.models  # noqa: F401
    import src.quality.models  # noqa: F401
    import src.warehouse.models  # noqa: F401

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        engine.dispose()


def _seed_raw(session: Session) -> None:
    now = datetime.now(timezone.utc)
    card = {
        "success": True,
        "data": {
            "day": {
                "id": 109,
                "name": "test day",
                "date": "2026-08-01T00:00:00Z",
                "external_id": "week-test",
                "track": {"code": "1", "name": "گنبدکاووس"},
            },
            "races": [
                {
                    "id": 434,
                    "number": 1,
                    "status": "CLOSE",
                    "day_id": 109,
                    "closed_at": "2026-08-01T12:00:00Z",
                    "race_horses": [
                        {
                            "id": 1,
                            "number": 7,
                            "horse_name": "خورشید وحدانی",
                            "external_id": "h7",
                            "jockey_name": "J1",
                            "scratched": False,
                            "rank": 1,
                        },
                        {
                            "id": 2,
                            "number": 1,
                            "horse_name": "حاکم عمارت",
                            "external_id": "h1",
                            "jockey_name": "J2",
                            "scratched": False,
                            "rank": 2,
                        },
                        {
                            "id": 3,
                            "number": 2,
                            "horse_name": "آریشاه",
                            "external_id": "h2",
                            "jockey_name": "J3",
                            "scratched": False,
                            "rank": 3,
                        },
                    ],
                }
            ],
            "pools": [
                {
                    "id": 1996,
                    "type": "WIN_1ST",
                    "status": "CLOSE",
                    "prize_status": "PAIED",
                    "price": "5000",
                    "total_price": "1000000",
                    "total_prize": "200000",
                    "total_return": "10000",
                    "share": 10,
                    "race_id": 434,
                    "day_id": 109,
                    "first_race_num": 1,
                    "last_race_num": 1,
                    "extra": {
                        "odd_details": [
                            {"odd_asli": 1.9, "odd_pardakhti": 1.9, "horse_numbers": [7]}
                        ]
                    },
                }
            ],
        },
    }
    odds = {
        "success": True,
        "data": {
            "odds": {
                "pishbar": {
                    "7": {"runnerId": 7, "odd": 1.9},
                    "1": {"runnerId": 1, "odd": 4.1},
                    "2": {"runnerId": 2, "odd": 6.3},
                },
                "updated_at": now.isoformat(),
            }
        },
    }
    survey = {
        "success": True,
        "data": {
            "race_id": 434,
            "statistics": [
                {"horse_num": 7, "count": 400},
                {"horse_num": 1, "count": 100},
                {"horse_num": 2, "count": 50},
            ],
        },
    }
    session.add_all(
        [
            RawPredictionSnapshot(
                snapshot_kind="racecard",
                source_key="109",
                endpoint="/races/racecard",
                payload_json=card,
                payload_hash="a",
                captured_at=now,
                is_pre_race=False,
                race_status="CLOSE",
            ),
            RawPredictionSnapshot(
                snapshot_kind="odds",
                source_key="434",
                endpoint="/pools/race/434/odds",
                payload_json=odds,
                payload_hash="b",
                captured_at=now,
            ),
            RawPredictionSnapshot(
                snapshot_kind="survey",
                source_key="434",
                endpoint="/races/434/survey-statistics",
                payload_json=survey,
                payload_hash="c",
                captured_at=now,
            ),
        ]
    )
    session.flush()


def test_warehouse_and_analytics_pipeline(mem_session: Session) -> None:
    _seed_raw(mem_session)
    wh = build_prediction_warehouse(mem_session)
    assert wh["events"] == 1
    assert wh["entries"] >= 3
    assert wh["rewards"] == 1
    assert wh["winners"] >= 1

    ev = mem_session.scalar(select(WhPredictionEvent))
    assert ev is not None
    assert ev.track_name == "گنبدکاووس"
    assert ev.race_date == date(2026, 8, 1)

    anl = build_prediction_analytics(mem_session)
    assert anl["status"] == "success"
    race_row = mem_session.scalar(select(AnlPredictionRaceMetrics))
    assert race_row is not None
    assert race_row.crowd_favorite_name == "خورشید وحدانی"
    assert race_row.crowd_confidence is not None
    assert race_row.features_json and "crowd_probability" in race_row.features_json
    assert race_row.favorite_failed == 0

    horses = mem_session.scalars(
        select(AnlPredictionEntityMetrics).where(
            AnlPredictionEntityMetrics.entity_type == "horse"
        )
    ).all()
    assert horses

    n = mem_session.execute(text("SELECT COUNT(*) FROM anl_v_pred_race_shock")).scalar()
    assert n and n >= 1
