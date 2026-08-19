"""Race Intelligence unit + integration tests."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from src.analytics.build import build_analytics
from src.analytics.models import AnlRaceIntelligence
from src.analytics.race_intel import (
    compute_race_intelligence,
    spearman_accuracy,
)
from src.analytics.race_intel_build import build_race_intelligence
from src.database.base import Base
from src.warehouse.models import WhHorse, WhRace, WhRaceResult


def test_spearman_perfect_and_inverted() -> None:
    assert spearman_accuracy([1, 2, 3], [1, 2, 3]) == 100.0
    assert spearman_accuracy([1, 2, 3], [3, 2, 1]) == 0.0


def test_compute_race_intelligence_card() -> None:
    """
    Favorite (rating 85) finishes 2nd; lower-rated winner (83) is surprise.
    Matches Gonbad Turkmen-style upset pattern.
    """
    runners = [
        {"horse_id": 1, "horse_name": "کارتال ترکان", "finish": 2, "rating": 85},
        {"horse_id": 2, "horse_name": "یاد آی تکه", "finish": 1, "rating": 83},
        {"horse_id": 3, "horse_name": "اسب سوم", "finish": 3, "rating": 78},
        {"horse_id": 4, "horse_name": "اسب چهارم", "finish": 4, "rating": 70},
        {"horse_id": 5, "horse_name": "اسب پنجم", "finish": 5, "rating": 65},
    ]
    intel = compute_race_intelligence(race_id=99, runners=runners, race_class="class4")
    assert intel is not None
    assert intel.favorite_name == "کارتال ترکان"
    assert intel.favorite_finish == 2
    assert intel.winner_name == "یاد آی تکه"
    assert intel.winner_expected_rank == 2
    assert intel.biggest_surprise_horse == "یاد آی تکه"
    assert intel.field_size == 5
    assert 0 <= intel.crowd_accuracy_pct <= 100
    assert 0 <= intel.shock_score <= 100
    assert intel.prediction_confidence in {"High", "Medium", "Low"}
    assert intel.expectation_source == "rating"
    report = intel.as_report()
    assert "Race Intelligence" in report
    assert "Difficulty:" in report
    assert "Crowd Accuracy:" in report
    assert "Biggest Surprise:" in report
    assert "یاد آی تکه" in report
    assert "Shock Score:" in report
    assert "Prediction Confidence:" in report


def test_compute_skips_tiny_fields() -> None:
    assert (
        compute_race_intelligence(
            race_id=1,
            runners=[{"horse_id": 1, "horse_name": "Solo", "finish": 1, "rating": 90}],
        )
        is None
    )


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


def _seed_upset(session: Session) -> int:
    horses = [
        WhHorse(source="test", source_horse_id="k", name="کارتال ترکان"),
        WhHorse(source="test", source_horse_id="y", name="یاد آی تکه"),
        WhHorse(source="test", source_horse_id="c", name="اسب سوم"),
        WhHorse(source="test", source_horse_id="d", name="اسب چهارم"),
    ]
    session.add_all(horses)
    session.flush()
    race = WhRace(
        source="test",
        source_race_id="turkmen-upset",
        name="کلاس4(85-71)",
        race_date=date(2026, 2, 14),
        track="گنبدکاووس",
        racecourse_code="gonbad-kavous",
        surface="ترکمن",
        race_number=1,
        distance=1200,
    )
    session.add(race)
    session.flush()
    finishes = [
        (horses[0], 2, 85),
        (horses[1], 1, 83),
        (horses[2], 3, 78),
        (horses[3], 4, 70),
    ]
    for horse, pos, rating in finishes:
        session.add(
            WhRaceResult(
                race_id=race.id,
                horse_id=horse.id,
                number=pos,
                finish_position=pos,
                source_rating=rating,
            )
        )
    session.flush()
    return race.id


def test_build_race_intelligence_persists(mem_session: Session) -> None:
    race_id = _seed_upset(mem_session)
    stats = build_race_intelligence(mem_session, racecourse_code="gonbad-kavous")
    assert stats["written"] == 1
    row = mem_session.scalar(
        select(AnlRaceIntelligence).where(AnlRaceIntelligence.race_id == race_id)
    )
    assert row is not None
    assert row.biggest_surprise_horse == "یاد آی تکه"
    assert row.report_text and "Race Intelligence" in row.report_text
    assert row.explain_json and row.explain_json.get("expectation_source") == "rating"


def test_analytics_build_includes_race_intel(mem_session: Session) -> None:
    _seed_upset(mem_session)
    # Need a later day so season discovery marks Feb cluster completed
    later = WhRace(
        source="test",
        source_race_id="later-day",
        name="کلاس4(85-71)",
        race_date=date(2026, 8, 1),
        track="گنبدکاووس",
        racecourse_code="gonbad-kavous",
        surface="ترکمن",
        race_number=1,
        distance=1200,
    )
    mem_session.add(later)
    mem_session.flush()
    h = mem_session.scalar(select(WhHorse).limit(1))
    assert h is not None
    mem_session.add(
        WhRaceResult(
            race_id=later.id,
            horse_id=h.id,
            number=1,
            finish_position=1,
            source_rating=80,
        )
    )
    # Second finisher so intel can build for later race too
    h2 = mem_session.scalars(select(WhHorse)).all()[1]
    mem_session.add(
        WhRaceResult(
            race_id=later.id,
            horse_id=h2.id,
            number=2,
            finish_position=2,
            source_rating=75,
        )
    )
    mem_session.flush()

    stats = build_analytics(mem_session, racecourse_code="gonbad-kavous", top_n=5)
    assert stats["status"] == "success"
    assert stats["race_intelligence"]["written"] >= 1

    count = mem_session.execute(text("SELECT COUNT(*) FROM anl_v_race_intelligence")).scalar()
    assert count and count >= 1
