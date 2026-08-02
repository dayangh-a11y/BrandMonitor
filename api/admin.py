from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.deps import get_db
from api.errors import APIError
from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger
from core.metrics import METRICS

router = APIRouter(prefix="/admin", tags=["admin"])
log = get_logger("api")


def _token_from_request(request: Request) -> str | None:
    return request.headers.get("X-Admin-Token") or request.query_params.get("token")


async def _admin_gate(request: Request) -> None:
    settings = load_settings()
    expected = settings.admin_token or "dev-admin-token"
    provided = _token_from_request(request) or ""
    if provided != expected:
        raise APIError(401, "unauthorized", "Admin token required (header X-Admin-Token or ?token=)")


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _rows_table(title: str, rows: list[dict], columns: list[str]) -> str:
    head = "".join(f"<th>{_esc(c)}</th>" for c in columns)
    body_parts = []
    for row in rows:
        cells = "".join(f"<td>{_esc(row.get(c, ''))}</td>" for c in columns)
        body_parts.append(f"<tr>{cells}</tr>")
    body = "".join(body_parts) or f"<tr><td colspan='{len(columns)}'>None</td></tr>"
    return f"""
    <section>
      <h2>{_esc(title)}</h2>
      <table>
        <thead><tr>{head}</tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>
    """


_PAGE_CSS = """
:root {
  --bg: #0f1419;
  --panel: #1a2332;
  --text: #e7ecf3;
  --muted: #9aa8bc;
  --accent: #3d9cf0;
  --ok: #3ecf8e;
  --warn: #f0b429;
  --bad: #f07178;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
  background: radial-gradient(1200px 600px at 10% -10%, #1b2a40, var(--bg));
  color: var(--text); padding: 24px;
}
h1 { font-size: 1.6rem; margin: 0 0 8px; }
h2 { font-size: 1.05rem; margin: 24px 0 10px; color: var(--accent); }
.sub { color: var(--muted); margin-bottom: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.card {
  background: var(--panel); border: 1px solid #2a3a52; border-radius: 10px;
  padding: 14px 16px;
}
.card .label { color: var(--muted); font-size: 0.8rem; }
.card .value { font-size: 1.4rem; font-weight: 600; margin-top: 6px; }
table { width: 100%; border-collapse: collapse; background: var(--panel); border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #2a3a52; font-size: 0.85rem; }
th { color: var(--muted); font-weight: 600; }
a { color: var(--accent); }
.ok { color: var(--ok); } .warn { color: var(--warn); } .bad { color: var(--bad); }
nav a { margin-right: 14px; }
"""


@router.get("/monitoring", response_class=HTMLResponse)
async def monitoring_dashboard(
    request: Request,
    db: Database = Depends(get_db),
) -> HTMLResponse:
    await _admin_gate(request)
    dash = await db.get_ops_dashboard()
    metrics = METRICS.snapshot()
    log.info("admin_monitoring_viewed")

    cards = [
        ("Running crawls", len(dash["running_crawls"])),
        ("Completed crawls", len(dash["completed_crawls"])),
        ("Failed crawls", len(dash["failed_crawls"])),
        ("Reviews today", dash["reviews_collected_today"]),
        ("Pending AI analysis", dash["reviews_pending_ai_analysis"]),
        ("AI queue length", dash["ai_queue_length"]),
        ("Branches processed", dash["branches_processed_recent"]),
        (
            "Avg crawl duration (s)",
            dash["crawl_duration"].get("avg_duration_seconds") or "—",
        ),
        ("Avg reviews / branch", dash["average_reviews_per_branch"]),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="label">{_esc(label)}</div>'
        f'<div class="value">{_esc(value)}</div></div>'
        for label, value in cards
    )

    run_cols = ["id", "company_name", "mode", "status", "started_at", "finished_at", "error"]
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>BrandMonitor Admin — Monitoring</title>
<style>{_PAGE_CSS}</style></head><body>
<nav>
  <a href="/admin/monitoring?token={_esc(_token_from_request(request) or '')}">Monitoring</a>
  <a href="/admin/health?token={_esc(_token_from_request(request) or '')}">System Health</a>
  <a href="/admin/metrics.json?token={_esc(_token_from_request(request) or '')}">Metrics JSON</a>
</nav>
<h1>Crawl Monitoring</h1>
<p class="sub">Admin-only operations dashboard (not the product UI).</p>
<div class="grid">{cards_html}</div>
{_rows_table("Running crawls", dash["running_crawls"], run_cols)}
{_rows_table("Completed crawls", dash["completed_crawls"], run_cols)}
{_rows_table("Failed crawls", dash["failed_crawls"], run_cols)}
<section><h2>In-process metrics snapshot</h2>
<pre>{_esc(metrics)}</pre></section>
</body></html>"""
    return HTMLResponse(page)


@router.get("/health", response_class=HTMLResponse)
async def system_health_page(
    request: Request,
    db: Database = Depends(get_db),
) -> HTMLResponse:
    await _admin_gate(request)
    health = await db.get_system_health()
    log.info("admin_health_viewed status=%s", health["status"])

    status_class = {"ok": "ok", "busy": "warn", "attention": "bad"}.get(health["status"], "warn")
    q = health["queue_health"]
    failed = health["failed_jobs"]
    last = health["last_successful_crawl"] or {}
    ai = health["ai_processing_status"]

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>BrandMonitor Admin — System Health</title>
<style>{_PAGE_CSS}</style></head><body>
<nav>
  <a href="/admin/monitoring?token={_esc(_token_from_request(request) or '')}">Monitoring</a>
  <a href="/admin/health?token={_esc(_token_from_request(request) or '')}">System Health</a>
</nav>
<h1>System Health</h1>
<p class="sub">Status: <span class="{status_class}">{_esc(health['status'])}</span></p>
<div class="grid">
  <div class="card"><div class="label">Database size</div>
    <div class="value">{_esc(health['database_size_mb'])} MB</div></div>
  <div class="card"><div class="label">AI queue length</div>
    <div class="value">{_esc(q['ai_queue_length'])}</div></div>
  <div class="card"><div class="label">Failed crawl runs</div>
    <div class="value">{_esc(failed['failed_crawl_runs'])}</div></div>
  <div class="card"><div class="label">Failed analysis jobs</div>
    <div class="value">{_esc(failed['failed_analysis_jobs'])}</div></div>
  <div class="card"><div class="label">Last successful crawl</div>
    <div class="value" style="font-size:1rem">{_esc(last.get('company_name') or '—')}
    <div class="label">{_esc(last.get('finished_at') or last.get('created_at') or '')}</div></div></div>
  <div class="card"><div class="label">Reviews pending AI</div>
    <div class="value">{_esc(ai['pending_reviews'])}</div></div>
</div>
<section><h2>Queue health</h2><pre>{_esc(q)}</pre></section>
<section><h2>AI processing status</h2><pre>{_esc(ai)}</pre></section>
<section><h2>Failed jobs</h2><pre>{_esc(failed)}</pre></section>
</body></html>"""
    return HTMLResponse(page)


@router.get("/metrics.json")
async def metrics_json(request: Request, db: Database = Depends(get_db)) -> JSONResponse:
    await _admin_gate(request)
    health = await db.get_system_health()
    return JSONResponse(
        {
            "metrics": METRICS.snapshot(),
            "health": health,
        }
    )


@router.get("/dashboard.json")
async def dashboard_json(request: Request, db: Database = Depends(get_db)) -> JSONResponse:
    await _admin_gate(request)
    return JSONResponse(await db.get_ops_dashboard())
