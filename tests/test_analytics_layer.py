"""Analytics layer unit + integration tests."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from src.analytics.build import build_analytics
from src.analytics.metrics import (
    consistency_score,
    form_score,
    parse_race_class,
    performance_rating,
    trend_slope,
)
from src.analytics.models import AnlHorseMetrics, AnlRanking, AnlSeason
from src.database.base import Base
from src.warehouse.models import (
    WhHorse,
    WhJockey,
    WhOwner,
    WhRace,
    WhRaceResult,
    WhTrainer,
)


def test_metric_helpers() -> None:
    assert parse_race_class("گروه 1") == "group1"
    assert parse_race_class("کلاس2(110-96)") == "class2"
    assert parse_race_class("مبتدی/نبرده") == "maiden"
    assert form_score([1, 2, 3], 3) is not None
    assert consistency_score([2, 2, 2]) == 100.0
    assert consistency_score([1, 8, 2, 9]) < consistency_score([2, 2, 3, 2])
    slope_up = trend_slope([1, 2, 4, 5, 6], window=5)  # newest first improving
    assert slope_up is not None and slope_up > 0
    pr = performance_rating(
        starts=5,
        wins=2,
        seconds=1,
        thirds=1,
        win_rate=0.5,
        place_rate=0.7,
        avg_finish=2.0,
        consistency=80.0,
        speed_index=105.0,
        earnings_index=0.8,
        difficulty_index=60.0,
        form_score=70.0,
    )
    assert pr is not None and 0 < pr <= 100


@pytest.fixture()
def mem_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    import src.analytics.models  # noqa: F401
    import src.crawler.models  # noqa: F401
    import src.crawler.stats  # noqa: F401
    import src.database.features  # noqa: F401
    import src.database.raw  # noqa: F401
    import src.features.models  # noqa: F401
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


def _seed(session: Session) -> None:
    j1 = WhJockey(name="Jockey A")
    j2 = WhJockey(name="Jockey B")
    t1 = WhTrainer(name="Trainer A")
    o1 = WhOwner(name="Owner A")
    session.add_all([j1, j2, t1, o1])
    session.flush()

    h1 = WhHorse(source="test", source_horse_id="h1", name="Alpha", birthdate=date(2022, 1, 1))
    h2 = WhHorse(source="test", source_horse_id="h2", name="Beta", birthdate=date(2021, 6, 1))
    h3 = WhHorse(source="test", source_horse_id="h3", name="Gamma", birthdate=date(2020, 3, 1))
    session.add_all([h1, h2, h3])
    session.flush()

    # Two season clusters for gonbad
    days = [date(2026, 2, 14), date(2026, 8, 1)]
    race_ids = []
    for i, d in enumerate(days):
        for breed, rnum in (("ترکمن", 1), ("دوخون", 2), ("تروبرد", 3)):
            race = WhRace(
                source="test",
                source_race_id=f"r-{d}-{rnum}",
                name="کلاس1(140-96)" if rnum == 3 else "کلاس4(85-71)",
                race_date=d,
                track="گنبدکاووس",
                racecourse_code="gonbad-kavous",
                distance=1600 if rnum != 1 else 1200,
                surface=breed,
                race_number=rnum,
                prize_json={
                    "prizes": [
                        {"rank": 1, "prize": 200000000},
                        {"rank": 2, "prize": 100000000},
                        {"rank": 3, "prize": 50000000},
                    ]
                },
            )
            session.add(race)
            session.flush()
            race_ids.append(race.id)
            # Field of 3
            finishers = [
                (h1, 1, "1:40.000", 90),
                (h2, 2, "1:41.000", 80),
                (h3, 3, "1:42.000", 70),
            ]
            # Make Alpha improve on second day in thoroughbred
            if d == days[1] and breed == "تروبرد":
                finishers = [
                    (h3, 1, "1:39.500", 85),
                    (h1, 2, "1:40.200", 90),
                    (h2, 3, "1:41.500", 80),
                ]
            for horse, pos, tm, rating in finishers:
                session.add(
                    WhRaceResult(
                        race_id=race.id,
                        horse_id=horse.id,
                        jockey_id=j1.id if pos == 1 else j2.id,
                        trainer_id=t1.id,
                        owner_id=o1.id,
                        number=pos,
                        finish_position=pos,
                        time_raw=tm,
                        source_rating=rating,
                    )
                )
    session.flush()


def test_analytics_build_and_views(mem_session: Session) -> None:
    _seed(mem_session)
    # Default min_starts=5 → Season Best must be INSUFFICIENT DATA on tiny fixture
    stats = build_analytics(
        mem_session, racecourse_code="gonbad-kavous", top_n=10, minimum_starts=5
    )
    assert stats["status"] == "success"
    assert stats["rows_written"] > 0

    seasons = mem_session.scalars(select(AnlSeason)).all()
    assert seasons
    assert any(s.is_latest_completed or not s.is_completed for s in seasons)

    metrics = mem_session.scalars(select(AnlHorseMetrics)).all()
    assert metrics
    sample = metrics[0]
    assert sample.performance_rating is not None
    assert sample.explain_text
    assert sample.win_rate is not None
    assert sample.explain_json and sample.explain_json.get("sample")

    status = mem_session.scalars(
        select(AnlRanking).where(
            AnlRanking.category == "best_season",
            AnlRanking.entity_type == "status",
        )
    ).all()
    assert status
    assert "INSUFFICIENT DATA" in (status[0].entity_name or "")

    # Earnings board still works with min_starts=1
    earn = mem_session.scalars(
        select(AnlRanking).where(
            AnlRanking.category == "highest_earnings",
            AnlRanking.entity_type == "horse",
        )
    ).all()
    assert earn
    assert earn[0].why_json and earn[0].why_json.get("qualification_status") == "qualified"

    breed_rows = mem_session.execute(
        text("SELECT COUNT(*) FROM anl_v_best_by_breed")
    ).scalar()
    # May be 0 when no horse reaches min_starts=5 in segments
    assert breed_rows is not None

    # Rebuild with lower gate to verify Season Best can populate
    stats2 = build_analytics(
        mem_session, racecourse_code="gonbad-kavous", top_n=10, minimum_starts=1
    )
    assert stats2["status"] == "success"
    best = mem_session.scalars(
        select(AnlRanking).where(
            AnlRanking.category == "best_season",
            AnlRanking.entity_type == "horse",
        )
    ).all()
    # Still may be insufficient if max_starts<=1 (Rule 5)
    max_starts = max(int(m.starts or 0) for m in metrics)
    if max_starts <= 1:
        assert any(r.entity_type == "status" for r in mem_session.scalars(
            select(AnlRanking).where(AnlRanking.category == "best_season")
        ).all())
    else:
        assert best
        assert best[0].why_json.get("starts") is not None
        assert best[0].why_json.get("confidence") is not None
