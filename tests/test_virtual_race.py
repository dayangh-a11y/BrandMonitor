"""Virtual Race Engine tests — no race_id required."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from src.analytics.models import AnlHorseMetrics
from src.database import init_db, reset_engine, session_scope
from src.virtual_race import (
    VirtualHorseEntry,
    VirtualRaceScenario,
    build_virtual_race_report,
    scenario_from_dict,
)
from src.virtual_race.models import AnlVirtualRaceReport
from src.warehouse.models import WhHorse


@pytest.fixture()
def db_url(tmp_path) -> str:
    reset_engine()
    url = f"sqlite:///{tmp_path / 'virtual.db'}"
    init_db(url=url)
    yield url
    reset_engine()


def _seed_horses(session) -> list[WhHorse]:
    horses = [
        WhHorse(source="test", source_horse_id="v1", name="اسب الف", sex="نر"),
        WhHorse(source="test", source_horse_id="v2", name="اسب ب", sex="نر"),
        WhHorse(source="test", source_horse_id="v3", name="اسب ج", sex="ماده"),
    ]
    session.add_all(horses)
    session.flush()
    for i, h in enumerate(horses, start=1):
        session.add(
            AnlHorseMetrics(
                horse_id=h.id,
                horse_name=h.name,
                scope="career",
                season_key="*",
                breed="*",
                starts=8 + i,
                wins=2 + i,
                seconds=1,
                thirds=1,
                places=4,
                win_rate=0.2 + i * 0.05,
                place_rate=0.4,
                avg_finish=3.0,
                performance_rating=50 + i * 10,
                sex_adjusted_performance_rating=50 + i * 10,
                form_score_5=40 + i * 15,
                consistency_score=60,
                distance_preference_score=0.55,
                track_preference_score=0.5,
                weather_preference_score=0.5,
                trainer_combination_score=0.4,
                jockey_combination_score=0.4,
                fatigue_score=20.0,
                improvement_trend=1.0,
                is_improving=False,
                is_declining=False,
            )
        )
    session.flush()
    return horses


def test_scenario_from_dict_parses_card_fields() -> None:
    sc = scenario_from_dict(
        {
            "distance": 1000,
            "class": "کلاس6",
            "racecourse": "گنبدکاووس",
            "date": "2026-08-07",
            "track_condition": "dry",
            "weather": {"air_temperature_c": 34, "humidity_pct": 28},
            "horses": [
                {
                    "name": "تریموف",
                    "weight": 59,
                    "draw": 1,
                    "jockey": "بهمن اونق",
                    "trainer": "بهمن اونق",
                    "rating": 60,
                }
            ],
        }
    )
    assert sc.distance == 1000
    assert sc.race_class == "کلاس6"
    assert sc.horses[0].weight == 59
    assert sc.horses[0].jockey == "بهمن اونق"
    assert sc.weather_dict()["air_temperature_c"] == 34


def test_virtual_race_no_race_id_and_no_persist_by_default(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        horses = _seed_horses(session)
        scenario = VirtualRaceScenario(
            horses=[
                VirtualHorseEntry(
                    horse_id=horses[0].id,
                    cloth=1,
                    weight=58,
                    jockey="J1",
                    trainer="T1",
                    rating=70,
                    odds=2.5,
                ),
                VirtualHorseEntry(
                    horse_id=horses[1].id,
                    cloth=2,
                    weight=56,
                    jockey="J2",
                    trainer="T2",
                    rating=60,
                    odds=4.0,
                ),
                VirtualHorseEntry(
                    horse_id=horses[2].id,
                    cloth=3,
                    weight=55,
                    jockey="J3",
                    trainer="T3",
                    rating=50,
                    odds=8.0,
                ),
            ],
            distance=1000,
            race_class="class6",
            racecourse_code="gonbad-kavous",
            track_condition="dry",
            weather={"rainfall_mm": 0, "air_temperature_c": 32},
            date="2026-08-07",
            race_name="Virtual Class 6",
        )
        payload = build_virtual_race_report(session, scenario, persist=False)
        assert payload["race_id"] is None
        assert payload["virtual"] is True
        assert payload["publishable"] is True
        assert abs(sum(h["winning_probability"] for h in payload["horses"]) - 1.0) < 1e-6
        assert all("top3_probability" in h for h in payload["horses"])
        assert payload["pairwise"]
        assert payload["reports"].get("best_win_candidate")
        assert "dark_horse" in payload["reports"] or payload.get("dark_horse") is not None
        assert payload["risk"]["field_risk_score"] is not None or payload["risk"]["per_horse"]
        assert payload["confidence"]["field_confidence"]
        assert "VIRTUAL RACE" in (payload.get("report_text") or "")

        saved = session.scalar(select(func.count()).select_from(AnlVirtualRaceReport))
        assert int(saved or 0) == 0


def test_virtual_race_persist_only_when_requested(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        horses = _seed_horses(session)
        scenario = VirtualRaceScenario(
            horses=[
                VirtualHorseEntry(horse_id=horses[0].id, rating=80, odds=2.0),
                VirtualHorseEntry(horse_id=horses[1].id, rating=55, odds=5.0),
            ],
            distance=1200,
            racecourse_code="gonbad-kavous",
        )
        payload = build_virtual_race_report(
            session, scenario, persist=True, scenario_key="test-vr-1"
        )
        assert payload["scenario_key"] == "test-vr-1"
        n = session.scalar(select(func.count()).select_from(AnlVirtualRaceReport))
        assert int(n or 0) == 1


def test_empty_unresolved_field_does_not_fabricate(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        payload = build_virtual_race_report(
            session,
            {
                "distance": 1000,
                "horses": [{"name": "اسب ناموجود کاملاً خیالی"}],
            },
            persist=False,
        )
        assert payload["publishable"] is False
        assert payload["horses"] == []
        assert "INSUFFICIENT DATA" in payload["report_text"]
