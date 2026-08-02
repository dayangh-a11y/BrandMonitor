from __future__ import annotations

import asyncio
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from api.deps import close_db, init_db
from api.main import app
from models.branch import Branch


def test_api_token_required(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRANDMONITOR_ENV", "development")
    monkeypatch.setenv("API_TOKEN", "secret-api")
    monkeypatch.setenv("ADMIN_TOKEN", "dev-admin-token")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "auth.db"))

    async def run() -> None:
        db = await init_db(str(tmp_path / "auth.db"))
        await db.upsert_company("AuthCo")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            denied = await ac.get("/companies")
            assert denied.status_code == 401
            assert denied.json()["error"]["code"] == "unauthorized"

            ok = await ac.get("/companies", headers={"X-API-Token": "secret-api"})
            assert ok.status_code == 200
            assert ok.json()[0]["name"] == "AuthCo"

            bearer = await ac.get(
                "/companies", headers={"Authorization": "Bearer secret-api"}
            )
            assert bearer.status_code == 200

            query = await ac.get("/companies", params={"api_token": "secret-api"})
            assert query.status_code == 200

            # Public health stays open.
            health = await ac.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

        await close_db()

    asyncio.run(run())


def test_production_requires_api_token(monkeypatch):
    monkeypatch.setenv("BRANDMONITOR_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "admin")
    monkeypatch.delenv("API_TOKEN", raising=False)
    from core.config import load_settings

    try:
        load_settings()
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "API_TOKEN" in str(exc)


def test_browser_manager_proxy_and_storage_env(tmp_path: Path, monkeypatch):
    state = tmp_path / "state.json"
    monkeypatch.setenv("BROWSER_PROXY", "http://127.0.0.1:8888")
    monkeypatch.setenv("BROWSER_STORAGE_STATE", str(state))
    monkeypatch.setenv("BROWSER_LOCALE", "fa-IR")
    from core.browser import BrowserManager

    mgr = BrowserManager(headless=True)
    assert mgr.proxy == "http://127.0.0.1:8888"
    assert mgr.storage_state_path == str(state)
    assert mgr.locale == "fa-IR"


def test_metric_samples_persist(tmp_path: Path):
    async def run() -> None:
        from core.db import Database
        from core.metrics import METRICS, flush_metrics_to_db

        METRICS.reset()
        db = Database(str(tmp_path / "metrics.db"))
        await db.connect()
        METRICS.incr("reviews_new", 3)
        METRICS.set_gauge("crawl_speed_reviews_per_sec", 1.5)
        written = await flush_metrics_to_db(db)
        assert written >= 2
        rows = await db.list_recent_metric_samples(limit=10)
        names = {r["name"] for r in rows}
        assert "reviews_new" in names
        assert "crawl_speed_reviews_per_sec" in names
        # Drain emptied buffer — second flush writes 0.
        assert await flush_metrics_to_db(db) == 0
        await db.close()

    asyncio.run(run())


def test_evaluate_ai_language_filter(tmp_path: Path):
    from scripts.evaluate_ai import load_dataset

    rows = load_dataset(Path("data/eval/reviews_200.jsonl"))
    fa = [r for r in rows if r.get("language") == "fa"]
    en = [r for r in rows if r.get("language") == "en"]
    assert len(fa) >= 50
    assert len(en) >= 50
