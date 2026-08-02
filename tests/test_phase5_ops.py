from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from collectors.crawl_models import CrawlConfig
from collectors.dedupe import review_fingerprint
from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.incremental import filter_incremental_reviews
from collectors.monitoring import CrawlMonitor
from collectors.scheduler import CrawlScheduler, ScheduleSpec
from core.config import load_settings, resolve_environment
from core.db import Database
from core.logging_setup import COMPONENT_LOGGERS, get_logger, setup_logging
from core.metrics import METRICS
from models.branch import Branch
from models.review import Review
from scripts.backup_export import export_csv, export_json, export_sqlite


class FlakySource:
    def __init__(self):
        self.branches = [
            Branch(name="HQ", address="Tehran", place_id="p1", company_name="OpsCo"),
            Branch(name="Saadat", address="Tehran", place_id="p2", company_name="OpsCo"),
        ]
        self.reviews = {
            "p1": [Review(author="A", text="ok", rating=4, external_id="e1")],
            "p2": [Review(author="B", text="delay", rating=1, external_id="e2")],
        }
        self.fail_place: str | None = "p2"
        self.calls = 0

    async def discover_branches(self, company_name: str) -> list[Branch]:
        return list(self.branches)

    async def collect_reviews(self, branch: Branch) -> list[Review]:
        self.calls += 1
        if branch.place_id == self.fail_place:
            # Fail permanently for interrupt simulation on first crawler instance.
            raise RuntimeError("hard failure")
        return list(self.reviews.get(branch.place_id, []))

    async def close(self) -> None:
        return None


def test_config_environments(monkeypatch):
    for name in ("development", "staging", "production"):
        monkeypatch.setenv("BRANDMONITOR_ENV", name)
        if name == "production":
            monkeypatch.setenv("ADMIN_TOKEN", "prod-secret")
        settings = load_settings()
        assert settings.environment == resolve_environment(name)
        assert settings.db_path
    monkeypatch.setenv("BRANDMONITOR_ENV", "development")


def test_structured_loggers_and_metrics():
    setup_logging(load_settings())
    for name in COMPONENT_LOGGERS:
        get_logger(name).info("heartbeat component=%s", name)
    METRICS.reset()
    METRICS.record_crawl(
        reviews_found=100,
        reviews_new=80,
        reviews_updated=20,
        duration_seconds=10,
        failed_branches=1,
        branches=10,
    )
    METRICS.record_ai_job(latency_ms=25.0, success=True)
    snap = METRICS.snapshot()
    assert snap["gauges"]["crawl_speed_reviews_per_sec"] == 10.0
    assert snap["gauges"]["duplicate_rate"] == 0.2
    assert "ai_processing_latency_ms" in snap["timing_avg_ms"]


def test_interrupt_and_retry_failed(tmp_path: Path):
    async def run() -> None:
        db = Database(str(tmp_path / "ops.db"))
        await db.connect()
        source = FlakySource()
        crawler = ProductionCrawler(db, source, monitor=CrawlMonitor())
        report = await crawler.run(
            CrawlConfig(company_name="OpsCo", mode="full", max_attempts=1)
        )
        # One branch succeeds, one fails -> run failed or succeeded with failures
        tasks = await db.list_crawl_branch_tasks(report.run_id)
        failed = [t for t in tasks if t["status"] == "failed"]
        assert failed, "expected a failed branch task for interrupt/retry drill"
        assert report.branches_failed >= 1

        # Simulate recovery: clear hard failure and retry failed tasks.
        source2 = FlakySource()
        source2.fail_place = None
        scheduler = CrawlScheduler()

        async def resume(run_id: int):
            crawler2 = ProductionCrawler(db, source2, monitor=CrawlMonitor())
            return await crawler2.run(
                CrawlConfig(company_name="OpsCo", mode="full", max_attempts=2),
                run_id=run_id,
            )

        out = await scheduler.retry_failed(db=db, run_id=report.run_id, runner=resume)
        assert out["reset_tasks"] >= 1
        final_tasks = await db.list_crawl_branch_tasks(report.run_id)
        assert all(t["status"] == "succeeded" for t in final_tasks)
        await db.close()

    asyncio.run(run())


def test_duplicate_imports(tmp_path: Path):
    async def run() -> None:
        db = Database(str(tmp_path / "dup.db"))
        await db.connect()
        company_id = await db.upsert_company("DupCo")
        branch_id = await db.upsert_branch(
            company_id,
            Branch(name="B1", address="A", company_name="DupCo", place_id="d1"),
        )
        reviews = [
            Review(author="A", text="same", rating=3, external_id="dup-1"),
            Review(author="B", text="other", rating=4, external_id="dup-2"),
        ]
        await db.upsert_reviews_batch(branch_id, reviews)
        await db.upsert_reviews_batch(branch_id, reviews)
        stats = await db.stats()
        assert stats["reviews"] == 2

        known_ext, known_fp, *_ = await db.get_branch_known_review_keys(branch_id)
        new_reviews, existing = filter_incremental_reviews(
            reviews,
            known_external_ids=known_ext,
            known_fingerprints=known_fp,
            fingerprint_fn=review_fingerprint,
            branch_key=str(branch_id),
        )
        assert new_reviews == []
        assert len(existing) == 2
        await db.close()

    asyncio.run(run())


def test_backup_export_tools(tmp_path: Path):
    async def run() -> None:
        db_path = tmp_path / "backup.db"
        db = Database(str(db_path))
        await db.connect()
        cid = await db.upsert_company("BackupCo")
        bid = await db.upsert_branch(
            cid,
            Branch(name="HQ", address="X", company_name="BackupCo", place_id="b1"),
        )
        await db.upsert_review(
            bid,
            Review(author="A", text="hello", rating=5, external_id="r1"),
        )
        out = tmp_path / "exports"
        sqlite_path = export_sqlite(db_path, out / "copy.db")
        assert sqlite_path.exists()
        csv_paths = await export_csv(db, out / "csv")
        assert Path(csv_paths["reviews_csv"]).exists()
        json_path = await export_json(db, out / "data.json")
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["companies"][0]["name"] == "BackupCo"
        await db.close()

    asyncio.run(run())


def test_admin_monitoring_and_health(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRANDMONITOR_ENV", "development")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "admin.db"))
    monkeypatch.setenv("ADMIN_TOKEN", "dev-admin-token")

    # Import after env is set so lifespan uses test DB.
    from api.main import app

    async def seed() -> None:
        db = Database(str(tmp_path / "admin.db"))
        await db.connect()
        cid = await db.upsert_company("AdminCo")
        bid = await db.upsert_branch(
            cid,
            Branch(name="HQ", address="Y", company_name="AdminCo", place_id="a1"),
        )
        await db.upsert_review(
            bid,
            Review(author="A", text="x", rating=4, external_id="ar1"),
        )
        run_id = await db.create_crawl_run(company_name="AdminCo", mode="incremental")
        await db.update_crawl_run_status(run_id, "succeeded", started=True, finished=True)
        await db.close()

    asyncio.run(seed())

    with TestClient(app) as client:
        denied = client.get("/admin/monitoring")
        assert denied.status_code == 401
        ok = client.get("/admin/monitoring?token=dev-admin-token")
        assert ok.status_code == 200
        assert "Crawl Monitoring" in ok.text
        assert "Reviews today" in ok.text
        health = client.get("/admin/health?token=dev-admin-token")
        assert health.status_code == 200
        assert "System Health" in health.text
        assert "Database size" in health.text
        metrics = client.get("/admin/metrics.json?token=dev-admin-token")
        assert metrics.status_code == 200
        body = metrics.json()
        assert "health" in body
        # Public health contract unchanged
        pub = client.get("/health")
        assert pub.status_code == 200
        assert pub.json()["status"] == "ok"


def test_scheduler_manual_and_schedule():
    async def run() -> None:
        scheduler = CrawlScheduler()
        calls: list[str] = []

        async def runner(spec: ScheduleSpec):
            calls.append(spec.company_name)
            return {"ok": True}

        await scheduler.run_manual(runner, ScheduleSpec(company_name="ManualCo"))
        scheduler.add_job(ScheduleSpec(company_name="SchedCo", interval_seconds=1))
        await scheduler.run_forever(runner, tick_seconds=0, max_ticks=1)
        assert "ManualCo" in calls
        assert "SchedCo" in calls

    asyncio.run(run())
