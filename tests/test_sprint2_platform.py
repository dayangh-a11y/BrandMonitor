"""Sprint 2 — append-only Raw, warehouse ETL, quality, crawler, entity resolution."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.crawler import CrawlerManager
from src.database import (
    finish_ingest_run,
    ingest_race,
    init_db,
    reset_engine,
    session_scope,
    start_ingest_run,
)
from src.database.base import Base
from src.database.raw import RawRace, RawRaceEntry
from src.features import FeatHorseFeatures, recalculate_all_features
from src.models import HorseEntry, Race
from src.quality import format_quality_report, run_quality_checks
from src.warehouse import WhHorse, WhRace, build_warehouse, run_entity_resolution
from src.warehouse.fuzzy import find_duplicate_pairs, similarity


@pytest.fixture()
def db_url(tmp_path) -> str:
    reset_engine()
    url = f"sqlite:///{tmp_path / 'sprint2.db'}"
    init_db(url=url)
    yield url
    reset_engine()


def _sample_race(*, source_id: str = "race-s2", name: str = "Maiden") -> Race:
    return Race(
        race=name,
        date="2019-04-19T00:00:00.000Z",
        track="گنبدکاووس",
        racecourse_code="gonbad-kavous",
        province="گنبدکاووس",
        distance=1000,
        surface="ترکمن",
        raceNumber=1,
        sourceId=source_id,
        sourceUrl="https://example.com/r/1",
        horses=[
            HorseEntry(
                name="اسب الف",
                number=1,
                sex="نر",
                weight=53.5,
                jockey="چابک یک",
                trainer="مربی یک",
                owner="مالک یک",
                rating=10,
                finishPosition=1,
                time="1:12.424",
                margin=0.0,
                horseId="h-s2-1",
                horseProfileUrl="https://example.com/h/h-s2-1",
            ),
            HorseEntry(
                name="اسب ب",
                number=2,
                jockey="چابک دو",
                trainer="مربی یک",
                owner="مالک دو",
                finishPosition=2,
                horseId="h-s2-2",
                horseProfileUrl="https://example.com/h/h-s2-2",
            ),
        ],
    )


def test_platform_table_layers_registered(db_url: str) -> None:
    tables = set(Base.metadata.tables)
    assert any(t.startswith("raw_") for t in tables)
    assert any(t.startswith("wh_") for t in tables)
    assert "feat_horse_features" in tables
    assert "feat_race_features" in tables
    assert "quality_check_runs" in tables
    assert "crawl_jobs" in tables


def test_raw_append_only_preserves_history(db_url: str) -> None:
    race = _sample_race()
    with session_scope(url=db_url) as session:
        run = start_ingest_run(session, source="asbdavani", input_url=race.source_url)
        first = ingest_race(session, race, source="asbdavani", ingest_run=run)
        finish_ingest_run(session, run, status="success")
        assert first is not None
        assert first.version == 1
        assert first.is_current is True
        assert first.source_hash
        assert first.parser_version

    # unchanged payload → no new version
    with session_scope(url=db_url) as session:
        second = ingest_race(session, race, source="asbdavani")
        assert second is not None
        assert second.version == 1
        total = session.scalar(select(func.count()).select_from(RawRace))
        assert total == 1

    # changed payload → append version 2, keep v1
    changed = _sample_race(name="Maiden Updated")
    with session_scope(url=db_url) as session:
        third = ingest_race(session, changed, source="asbdavani")
        assert third is not None
        assert third.version == 2
        assert third.is_current is True
        versions = list(session.scalars(select(RawRace).order_by(RawRace.version)))
        assert len(versions) == 2
        assert versions[0].is_current is False
        assert versions[0].name == "Maiden"
        assert versions[1].name == "Maiden Updated"
        # old entries still attached to v1
        v1_entries = list(
            session.scalars(select(RawRaceEntry).where(RawRaceEntry.race_id == versions[0].id))
        )
        assert len(v1_entries) == 2


def test_warehouse_etl_and_empty_features(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        ingest_race(session, _sample_race(), source="asbdavani")

    with session_scope(url=db_url) as session:
        stats = build_warehouse(session)
        assert stats["races"] == 1
        assert stats["horses"] >= 2
        assert stats["results"] == 2
        assert session.scalar(select(func.count()).select_from(WhRace)) == 1
        assert session.scalar(select(func.count()).select_from(WhHorse)) >= 2

        run = recalculate_all_features(session)
        assert run.status == "success"
        assert run.rows_touched >= 2
        assert session.scalar(select(func.count()).select_from(FeatHorseFeatures)) >= 2


def test_entity_resolution_fuzzy() -> None:
    assert similarity("رضا کریمی", "رضا کریمی") == 1.0
    pairs = find_duplicate_pairs(["رضا کریمی", "رضا  کریمی", "علی"], threshold=0.9)
    assert any(p[2] >= 0.9 for p in pairs)


def test_quality_report(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        ingest_race(session, _sample_race(), source="asbdavani")
        build_warehouse(session)
        run_entity_resolution(session)
        summary = run_quality_checks(session)

    text = format_quality_report(summary)
    assert "Number of races:" in text
    assert "Broken URLs:" in text
    assert summary["races"] >= 1
    assert "processing_speed_seconds" in summary


def test_crawler_manager_queue(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        mgr = CrawlerManager(session)
        j1 = mgr.enqueue(job_type="race", url="https://example.com/a?round=1")
        j2 = mgr.enqueue(job_type="race", url="https://example.com/a?round=1")
        assert j1.id == j2.id

        claimed = mgr.claim_next()
        assert claimed is not None
        assert claimed.status == "running"
        mgr.mark_failed(claimed, "boom")
        # attempts=1 < max → pending retry
        assert claimed.status == "pending"

        claimed2 = mgr.claim_next()
        assert claimed2 is not None
        mgr.mark_success(claimed2, {"ok": True})
        progress = mgr.progress()
        assert progress.get("success", 0) == 1
