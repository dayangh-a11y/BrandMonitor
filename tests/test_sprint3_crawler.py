"""Sprint 3 — mass crawler discovery, queue, metrics tests."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from src.crawler.discovery import discover_race_urls_from_week_html, discover_week_ids
from src.crawler.manager import CrawlerManager
from src.crawler.metrics import collect_dashboard_metrics, format_dashboard
from src.crawler.reports import generate_daily_report
from src.crawler.stats import CrawlDailyReport, CrawlRun
from src.database import init_db, reset_engine, session_scope
from src.database.base import Base


@pytest.fixture()
def db_url(tmp_path) -> str:
    reset_engine()
    url = f"sqlite:///{tmp_path / 'crawl.db'}"
    init_db(url=url)
    yield url
    reset_engine()


def _escaped(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("\\", "\\\\").replace('"', r"\"")


def test_discover_week_ids_from_leagues_and_hrefs() -> None:
    leagues = [
        {
            "id": "L1",
            "location": {"name": "مشهد"},
            "weeks": [{"id": "weekhist1"}, {"id": "weekhist2"}],
        }
    ]
    html = (
        '<a href="/racecards/weekhref1"></a>'
        f'"leagues":{json.dumps(leagues, ensure_ascii=False)}'
    )
    ids = discover_week_ids(html)
    assert "weekhref1" in ids
    assert "weekhist1" in ids
    assert "weekhist2" in ids


def test_discover_race_urls_from_week() -> None:
    week = {
        "id": "weekabc",
        "name": "هفته 1",
        "races": [
            {"id": "r1", "round": 2, "name": "A", "raceHorses": []},
            {"id": "r2", "round": 1, "name": "B", "raceHorses": []},
            {"id": "r3", "round": 3, "name": "C", "raceHorses": []},
        ],
    }
    html = (
        '<script>self.__next_f.push([1,"'
        + r'$L18",null,{"_weekInfo\":'
        + _escaped(week)
        + r'}'
        + '"])</script>'
    )
    urls = discover_race_urls_from_week_html(html, "https://asbdavani.app/racecards/weekabc")
    assert urls == [
        "https://asbdavani.app/racecards/weekabc?round=1",
        "https://asbdavani.app/racecards/weekabc?round=2",
        "https://asbdavani.app/racecards/weekabc?round=3",
    ]


def test_enqueue_skip_and_force_refresh(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        mgr = CrawlerManager(session)
        j1 = mgr.enqueue(job_type="race", url="https://example.com/r?round=1")
        mgr.mark_success(j1, {"ok": True})
        j2 = mgr.enqueue(job_type="race", url="https://example.com/r?round=1")
        assert j2.id == j1.id
        assert j2.status == "success"
        j3 = mgr.enqueue(job_type="race", url="https://example.com/r?round=1", force=True)
        assert j3.id == j1.id
        assert j3.status == "pending"


def test_multi_worker_claim_unique(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        mgr = CrawlerManager(session)
        mgr.enqueue(job_type="race", url="https://example.com/a")
        mgr.enqueue(job_type="race", url="https://example.com/b")
        a = mgr.claim_next(worker_id="w1")
        b = mgr.claim_next(worker_id="w2")
        assert a is not None and b is not None
        assert a.id != b.id
        assert a.status == "running" and b.status == "running"
        c = mgr.claim_next(worker_id="w3")
        assert c is None


def test_dashboard_and_daily_report(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        assert "crawl_runs" in Base.metadata.tables
        assert "crawl_daily_reports" in Base.metadata.tables
        session.add(
            CrawlRun(
                status="success",
                workers=2,
                jobs_success=10,
                jobs_failed=1,
                duration_seconds=5.0,
            )
        )
        mgr = CrawlerManager(session)
        job = mgr.enqueue(job_type="race", url="https://example.com/x")
        job.attempts = job.max_attempts
        mgr.mark_failed(job, "boom")
        assert job.status == "failed"

        metrics = collect_dashboard_metrics(session)
        text = format_dashboard(metrics)
        assert "Total races:" in text
        assert "Failed pages:" in text
        assert metrics["failed_pages"] >= 1

        report, report_text = generate_daily_report(session)
        assert "Daily Crawl Report" in report_text
        assert session.scalar(select(func.count()).select_from(CrawlDailyReport)) == 1
