"""Warehouse Raw/Features separation + pipeline rebuild tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.database import (
    finish_ingest_run,
    ingest_horse_history,
    ingest_race,
    init_db,
    reset_engine,
    session_scope,
    start_ingest_run,
)
from src.database.base import Base
from src.database.features import FeatHorseCareer, FeatHorseForm
from src.database.raw import RawHorse, RawRace, RawRaceEntry
from src.models import HorseEntry, HorseHistory, HorseHistoryEntry, HorseProfile, Race
from src.pipelines.runner import build_features


@pytest.fixture()
def db_url(tmp_path) -> str:
    reset_engine()
    url = f"sqlite:///{tmp_path / 'warehouse.db'}"
    init_db(url=url)
    yield url
    reset_engine()


def test_raw_and_feat_table_prefixes(db_url: str) -> None:
    tables = set(Base.metadata.tables)
    raw = {t for t in tables if t.startswith("raw_")}
    feat = {t for t in tables if t.startswith("feat_")}
    assert raw
    assert feat
    assert raw.isdisjoint(feat)
    assert "raw_races" in raw
    assert "feat_horse_career" in feat


def test_ingest_race_writes_raw_only(db_url: str) -> None:
    race = Race(
        race="Maiden",
        date="2019-04-19T00:00:00.000Z",
        track="گنبدکاووس",
        province="گنبدکاووس",
        distance=1000,
        surface="ترکمن",
        raceNumber=1,
        sourceId="race-1",
        sourceUrl="https://example.com/r/1",
        horses=[
            HorseEntry(
                name="اسب الف",
                number=1,
                age=3,  # derived — must not become a Raw column
                sex="نر",
                weight=53.5,
                jockey="چابک ۱",
                trainer="مربی ۱",
                owner="مالک ۱",
                rating=10,
                finishPosition=1,
                time="1:12.424",
                margin=0.0,
                horseId="h1",
                horseProfileUrl="https://example.com/h/h1",
            )
        ],
    )

    with session_scope(url=db_url) as session:
        run = start_ingest_run(session, source="asbdavani", input_url=race.source_url)
        ingest_race(session, race, source="asbdavani", ingest_run=run)
        finish_ingest_run(session, run, status="success")

        raw_race = session.scalar(select(RawRace).where(RawRace.source_race_id == "race-1"))
        assert raw_race is not None
        assert raw_race.distance == 1000
        assert len(raw_race.entries) == 1
        entry = raw_race.entries[0]
        assert entry.source_rating == 10
        assert entry.finish_position == 1
        assert entry.payload_json is not None
        assert entry.payload_json.get("age") == 3
        # Features empty after raw ingest
        assert session.scalar(select(FeatHorseCareer)) is None


def test_feature_pipeline_builds_from_raw(db_url: str) -> None:
    race = Race(
        race="Maiden",
        date="2019-04-19",
        track="گنبدکاووس",
        distance=1000,
        raceNumber=1,
        sourceId="race-2",
        horses=[
            HorseEntry(
                name="اسب ب",
                number=2,
                jockey="ج ۱",
                trainer="م ۱",
                finishPosition=1,
                horseId="h2",
                horseProfileUrl="https://example.com/h/h2",
            ),
            HorseEntry(
                name="اسب ج",
                number=3,
                jockey="ج ۲",
                trainer="م ۱",
                finishPosition=2,
                horseId="h3",
                horseProfileUrl="https://example.com/h/h3",
            ),
        ],
    )
    history = HorseHistory(
        horse=HorseProfile(
            horseId="h2",
            name="اسب ب",
            sex="نر",
            birthdate="2016-03-20",
            profileUrl="https://example.com/h/h2",
            sire="پدر",
            dam="مادر",
        ),
        history=[
            HorseHistoryEntry(
                raceName="قبلی",
                raceDate="2019-01-01",
                track="گنبدکاووس",
                raceNumber=3,
                distance=1000,
                finishPosition=3,
                jockey="ج ۱",
                trainer="م ۱",
            )
        ],
    )

    with session_scope(url=db_url) as session:
        ingest_race(session, race, source="asbdavani")
        ingest_horse_history(session, history, source="asbdavani")

    with session_scope(url=db_url) as session:
        runs = build_features(
            session,
            pipeline_names=["horse_career", "horse_form", "jockey_stats", "trainer_stats"],
        )
        assert all(r.status == "success" for r in runs)

        horse = session.scalar(select(RawHorse).where(RawHorse.source_horse_id == "h2"))
        assert horse is not None
        career = session.get(FeatHorseCareer, horse.id)
        assert career is not None
        assert career.starts >= 1
        assert career.wins >= 1
        assert career.pipeline_run_id is not None

        form = session.scalar(
            select(FeatHorseForm).where(FeatHorseForm.horse_id == horse.id)
        )
        assert form is not None
        assert form.form_string is not None


def test_raw_tables_have_no_feature_columns() -> None:
    """Guardrail: RawRaceEntry must not grow engineered feature fields."""
    forbidden = {
        "win_rate",
        "place_rate",
        "avg_finish",
        "form_string",
        "days_since_last_race",
        "recent_avg_finish",
    }
    cols = {c.name for c in RawRaceEntry.__table__.columns}
    assert forbidden.isdisjoint(cols)
    # age is collector-derived → not a first-class raw column
    assert "age" not in cols
