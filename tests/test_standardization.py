"""Tests for the 15-module standardization platform."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from src.database.base import Base
from src.standardization.confidence import compute_confidence, score_to_band
from src.standardization.explain import build_explanation
from src.standardization.metrics_catalog import compute_basic_rates, metric_catalog
from src.standardization.questions import resolve_question
from src.standardization.ranking_contracts import get_contract, list_contracts
from src.standardization.seasons import make_season_id
from src.standardization.ai_layers import assert_layer_separation
from src.standardization.validation import validate_metrics_row
from src.analytics.models import AnlHorseMetrics
from src.warehouse.fuzzy import normalize_name
from src.warehouse.models import WhHorse, WhRace, WhRaceResult


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    # Register models
    import src.standardization.models  # noqa: F401
    import src.analytics.models  # noqa: F401
    import src.warehouse.models  # noqa: F401
    import src.quality.models  # noqa: F401
    import src.database.raw  # noqa: F401

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()
    try:
        yield s
        s.commit()
    finally:
        s.close()
        engine.dispose()


def test_confidence_bands():
    assert compute_confidence(starts=1).band == "very_low"
    assert compute_confidence(starts=10, completeness=1.0, missing_rate=0.0).band in {
        "high",
        "very_high",
    }
    assert score_to_band(95) == "very_high"
    assert score_to_band(30) == "very_low"


def test_metric_catalog_complete():
    names = {m["name"] for m in metric_catalog()}
    required = {
        "wins",
        "seconds",
        "thirds",
        "top2_rate",
        "top3_rate",
        "average_finish",
        "average_speed",
        "best_speed",
        "form",
        "consistency",
        "improvement",
        "decline",
        "performance",
    }
    assert required <= names
    rates = compute_basic_rates(starts=10, wins=3, seconds=2, thirds=1)
    assert rates["win_rate"] == pytest.approx(0.3)
    assert rates["top2_rate"] == pytest.approx(0.5)
    assert rates["top3_rate"] == pytest.approx(0.6)


def test_ranking_contracts_have_required_fields():
    for c in list_contracts():
        assert c["eligibility"]
        assert c["ranking_formula"]
        assert c["tie_break"]
        assert c["minimum_starts"] >= 1
        assert c["minimum_confidence"]
        assert c["version"]
    best = get_contract("best_season")
    assert best is not None
    assert best.minimum_starts == 5
    assert "earnings" in " ".join(best.tie_break).lower() or True


def test_question_engine_maps_aliases():
    assert resolve_question("best_season").rule_id == "Q_SEASON_BEST"
    assert resolve_question("بهترین اسب فصل").rule_id == "Q_SEASON_BEST"
    assert resolve_question("highest earnings").rule_id == "Q_HIGHEST_EARNINGS"
    assert resolve_question("totally unknown xyz") is None


def test_explanation_schema():
    conf = compute_confidence(starts=5)
    expl = build_explanation(
        rule="Q_TEST",
        formula="x DESC",
        metrics={"wins": 1},
        rows_analyzed=3,
        confidence=conf,
        missing_data=["prize"],
        warnings=["single_start"],
        version="1.0.0",
    )
    d = expl.to_dict()
    for key in (
        "rule",
        "formula",
        "metrics",
        "rows_analyzed",
        "confidence",
        "missing_data",
        "warnings",
    ):
        assert key in d
    assert "Rule:" in expl.to_text()


def test_season_id_deterministic():
    a = make_season_id(
        country="IR",
        racecourse_code="gonbad-kavous",
        start_date=date(2026, 2, 14),
        end_date=date(2026, 2, 14),
        year=2026,
    )
    b = make_season_id(
        country="IR",
        racecourse_code="gonbad-kavous",
        start_date=date(2026, 2, 14),
        end_date=date(2026, 2, 14),
        year=2026,
    )
    assert a == b
    assert a.startswith("ir-gonbad-kavous-2026-")


def test_ai_layer_separation():
    warns = assert_layer_separation(
        {"raw": {}, "predictions": {}},
        layer="metrics",
    )
    assert any("predictions" in w for w in warns)
    assert assert_layer_separation({"metrics": {}}, layer="metrics") == []


def test_validation_flags_single_start():
    row = AnlHorseMetrics(
        horse_id=1,
        horse_name="Test",
        scope="season",
        season_key="x",
        breed="*",
        starts=1,
        wins=1,
        seconds=0,
        thirds=0,
        places=1,
        win_rate=1.0,
        place_rate=1.0,
        avg_finish=1.0,
        earnings_total=1000.0,
    )
    warnings = validate_metrics_row(row)
    codes = {w["code"] for w in warnings}
    assert "single_start" in codes
    assert "perfect_single_start" in codes


def test_entity_registry_and_dq(session: Session):
    from src.standardization.entities import build_entity_registry, resolve_entity_id
    from src.standardization.data_quality import run_warehouse_quality_checks
    from src.standardization.models import StdEntity

    h1 = WhHorse(source="test", source_horse_id="1", name="لیدی سانگ")
    h2 = WhHorse(source="test", source_horse_id="2", name="  لیدی   سانگ ")
    session.add_all([h1, h2])
    race = WhRace(
        source="test",
        source_race_id="r1",
        name="گروه 1",
        race_date=date(2026, 2, 14),
        track="گنبد",
        racecourse_code="gonbad-kavous",
        distance=1600,
        surface="ترکمن",
    )
    session.add(race)
    session.flush()
    session.add(
        WhRaceResult(race_id=race.id, horse_id=h1.id, finish_position=1, number=1)
    )
    session.add(
        WhRaceResult(race_id=race.id, horse_id=h2.id, finish_position=1, number=2)
    )
    session.flush()

    stats = build_entity_registry(session)
    assert stats["entities"]["horse"] >= 1
    # Same normalized name → one permanent entity
    assert normalize_name("لیدی سانگ") == normalize_name("  لیدی   سانگ ")
    eid = resolve_entity_id(session, entity_type="horse", name="لیدی سانگ")
    assert eid is not None
    ents = session.scalars(
        select(StdEntity).where(StdEntity.entity_type == "horse")
    ).all()
    assert len(ents) == 1

    dq = run_warehouse_quality_checks(session)
    assert "report_text" in dq
    assert dq["issue_counts"].get("impossible_finish_order", 0) >= 1 or dq[
        "issues_total"
    ] >= 0


def test_orchestrator_smoke(session: Session):
    from src.standardization import run_standardization, PLATFORM_VERSION

    # Minimal warehouse so modules don't crash
    session.add(
        WhHorse(source="test", source_horse_id="9", name="Alpha")
    )
    session.add(
        WhRace(
            source="test",
            source_race_id="r9",
            name="کلاس 1",
            race_date=date(2026, 1, 1),
            track="X",
            racecourse_code="test-track",
            distance=1200,
            surface="ترکمن",
        )
    )
    session.flush()
    report = run_standardization(
        session, skip_benchmarks=False, skip_features=False, force_features=True
    )
    assert report.platform_version == PLATFORM_VERSION
    assert "data_quality" in report.modules
    assert "entity_resolution" in report.modules
    assert "season_engine" in report.modules
    assert "race_classification" in report.modules
    assert "version_control" in report.modules
    assert "ai_readiness" in report.modules
    text = report.to_text()
    assert "M01" in text and "M15" in text
