"""Interactive executive analytics dashboards (HTML + Chart.js)."""

from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from analytics.filters import AnalyticsFilter
from analytics.service import AnalyticsService
from api.auth import require_api_token, token_from_request
from api.deps import get_db
from api.errors import APIError
from core.db import Database

router = APIRouter(prefix="/analytics/ui", tags=["analytics-ui"], dependencies=[Depends(require_api_token)])


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _token_q(request: Request) -> str:
    tok = token_from_request(request) or ""
    return urlencode({"api_token": tok}) if tok else ""


_CSS = """
:root {
  --bg0: #0b1220;
  --bg1: #121a2b;
  --panel: #172033;
  --line: #2a3a55;
  --text: #e8eef8;
  --muted: #93a4bd;
  --accent: #3d9cf0;
  --good: #3ecf8e;
  --warn: #f0b429;
  --bad: #f07178;
  --serif: "Fraunces", "Iowan Old Style", Georgia, serif;
  --sans: "IBM Plex Sans", "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: var(--sans);
  color: var(--text);
  background:
    radial-gradient(900px 500px at 10% -10%, #1c3358 0%, transparent 55%),
    radial-gradient(700px 400px at 90% 0%, #243018 0%, transparent 50%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  min-height: 100vh;
}
a { color: var(--accent); text-decoration: none; }
header {
  padding: 22px 28px 8px;
  display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap;
  align-items: end;
}
.brand {
  font-family: var(--serif);
  font-size: clamp(1.8rem, 3vw, 2.6rem);
  letter-spacing: -0.02em;
  margin: 0;
}
.sub { color: var(--muted); margin-top: 4px; }
nav a { margin-right: 14px; color: var(--muted); }
nav a:hover { color: var(--text); }
main { padding: 8px 28px 40px; }
.filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  background: rgba(23,32,51,.85);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px;
  margin: 12px 0 18px;
}
.filters label { display:block; font-size:.72rem; color:var(--muted); margin-bottom:4px; }
.filters input, .filters select, .filters button {
  width: 100%; padding: 8px 10px; border-radius: 8px;
  border: 1px solid var(--line); background: #0f1728; color: var(--text);
}
.filters button {
  background: linear-gradient(180deg, #3d9cf0, #2a78c4);
  border: 0; font-weight: 600; cursor: pointer; margin-top: 18px;
}
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.kpi {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px 16px;
  transform: translateY(6px);
  opacity: 0;
  animation: rise .5s ease forwards;
}
.kpi:nth-child(2){animation-delay:.05s}
.kpi:nth-child(3){animation-delay:.1s}
.kpi:nth-child(4){animation-delay:.15s}
.kpi:nth-child(5){animation-delay:.2s}
.kpi .label { color: var(--muted); font-size: .78rem; }
.kpi .value {
  font-family: var(--serif);
  font-size: 1.8rem;
  margin-top: 6px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 14px;
}
.panel {
  grid-column: span 6;
  background: rgba(23,32,51,.9);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px 16px 18px;
}
.panel.wide { grid-column: span 12; }
.panel h2 {
  margin: 0 0 10px;
  font-size: 1rem;
  color: var(--accent);
  font-weight: 600;
}
.chart-box { position: relative; height: 260px; }
table { width: 100%; border-collapse: collapse; font-size: .85rem; }
th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; }
.pill {
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  background: #24324a; margin: 2px; font-size: .78rem;
}
.pill.good { background: rgba(62,207,142,.15); color: var(--good); }
.pill.bad { background: rgba(240,113,120,.15); color: var(--bad); }
.exports a {
  display: inline-block; margin: 0 8px 8px 0; padding: 8px 12px;
  border: 1px solid var(--line); border-radius: 8px; color: var(--text);
  background: #10192b;
}
.summary {
  line-height: 1.5; color: #d5deec;
}
@media (max-width: 900px) {
  .panel, .panel.wide { grid-column: span 12; }
  main, header { padding-left: 16px; padding-right: 16px; }
}
@keyframes rise {
  to { opacity: 1; transform: translateY(0); }
}
"""


def _filter_form(action: str, filt: AnalyticsFilter, token_q: str) -> str:
    f = filt.to_dict()

    def val(key: str) -> str:
        v = f.get(key)
        return _esc(v if v is not None else "")

    def options(
        values: tuple[str, ...],
        selected: str | None,
        *,
        include_any: bool = True,
    ) -> str:
        parts = ['<option value="">Any</option>'] if include_any else []
        for item in values:
            sel = " selected" if selected == item else ""
            parts.append(f'<option value="{_esc(item)}"{sel}>{_esc(item)}</option>')
        return "".join(parts)

    tok_hidden = ""
    if token_q:
        tok = token_q.split("=", 1)[-1]
        tok_hidden = f'<input type="hidden" name="api_token" value="{_esc(tok)}" />'
    sentiment_opts = options(("Positive", "Neutral", "Negative"), f.get("sentiment"))
    grain_opts = options(
        ("daily", "weekly", "monthly"),
        f.get("trend_grain") or "weekly",
        include_any=False,
    )
    return f"""
    <form class="filters" method="get" action="{_esc(action)}">
      {tok_hidden}
      <div><label>Date from</label><input name="date_from" value="{val('date_from')}" placeholder="YYYY-MM-DD"/></div>
      <div><label>Date to</label><input name="date_to" value="{val('date_to')}" placeholder="YYYY-MM-DD"/></div>
      <div><label>Province</label><input name="province" value="{val('province')}"/></div>
      <div><label>City</label><input name="city" value="{val('city')}"/></div>
      <div><label>Branch id</label><input name="branch_id" value="{val('branch_id')}"/></div>
      <div><label>Rating min</label><input name="rating_min" value="{val('rating_min')}"/></div>
      <div><label>Rating max</label><input name="rating_max" value="{val('rating_max')}"/></div>
      <div><label>Sentiment</label><select name="sentiment">{sentiment_opts}</select></div>
      <div><label>Complaint</label><input name="complaint_category" value="{val('complaint_category')}"/></div>
      <div><label>Positive</label><input name="positive_category" value="{val('positive_category')}"/></div>
      <div><label>Min reviews</label><input name="min_review_count" value="{val('min_review_count')}"/></div>
      <div><label>Trend grain</label><select name="trend_grain">{grain_opts}</select></div>
      <div><button type="submit">Apply filters</button></div>
    </form>
    """


def _kpi(label: str, value: Any) -> str:
    return f'<div class="kpi"><div class="label">{_esc(label)}</div><div class="value">{_esc(value)}</div></div>'


def _chart_panel(title: str, canvas_id: str, wide: bool = False) -> str:
    cls = "panel wide" if wide else "panel"
    return f"""
    <section class="{cls}">
      <h2>{_esc(title)}</h2>
      <div class="chart-box"><canvas id="{_esc(canvas_id)}"></canvas></div>
    </section>
    """


def _table(title: str, rows: list[dict], columns: list[tuple[str, str]], wide: bool = False) -> str:
    cls = "panel wide" if wide else "panel"
    head = "".join(f"<th>{_esc(label)}</th>" for _, label in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{_esc(row.get(key, ''))}</td>" for key, _ in columns)
        body.append(f"<tr>{cells}</tr>")
    body_html = "".join(body) or f"<tr><td colspan='{len(columns)}'>No data</td></tr>"
    return f"""
    <section class="{cls}">
      <h2>{_esc(title)}</h2>
      <table><thead><tr>{head}</tr></thead><tbody>{body_html}</tbody></table>
    </section>
    """


def _pills(items: list[Any], kind: str = "") -> str:
    if not items:
        return '<span class="sub">None</span>'
    out = []
    for item in items:
        text = item if isinstance(item, str) else item.get("name", str(item))
        out.append(f'<span class="pill {kind}">{_esc(text)}</span>')
    return "".join(out)


def _page(title: str, body: str, charts_json: str, token_q: str) -> str:
    q = f"?{token_q}" if token_q else ""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title)} · BrandMonitor Analytics</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>{_CSS}</style>
</head><body>
<header>
  <div>
    <p class="brand">BrandMonitor</p>
    <p class="sub">{_esc(title)}</p>
  </div>
  <nav>
    <a href="/analytics/ui{q}">Analytics home</a>
    <a href="/demo">Product demo</a>
    <a href="/docs">API</a>
  </nav>
</header>
<main>
{body}
</main>
<script>
const CHARTS = {charts_json};
const palette = ["#3d9cf0","#3ecf8e","#f0b429","#f07178","#a78bfa","#22d3ee","#fb7185","#94a3b8"];
function makeChart(id, conf) {{
  if (!conf) return;
  const el = document.getElementById(id);
  if (!el) return;
  const type = conf.type === "pie" ? "pie" : (conf.type === "radar" ? "radar" : (conf.type === "line" ? "line" : "bar"));
  new Chart(el, {{
    type,
    data: {{
      labels: conf.labels || (conf.cells||[]).map(c => c.label) || (conf.points||[]).map(p => p.date),
      datasets: [{{
        label: id,
        data: conf.values || (conf.cells||[]).map(c => c.value) || (conf.points||[]).map(p => p.rating),
        backgroundColor: type === "line" ? "rgba(61,156,240,.2)" : palette,
        borderColor: "#3d9cf0",
        fill: type === "line",
        tension: 0.25
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ labels: {{ color: "#c9d6ea" }} }} }},
      scales: type === "pie" || type === "radar" ? {{}} : {{
        x: {{ ticks: {{ color: "#93a4bd" }}, grid: {{ color: "rgba(42,58,85,.5)" }} }},
        y: {{ ticks: {{ color: "#93a4bd" }}, grid: {{ color: "rgba(42,58,85,.5)" }} }}
      }}
    }}
  }});
}}
Object.entries(CHARTS || {{}}).forEach(([key, conf]) => makeChart("c_" + key, conf));
</script>
</body></html>"""


@router.get("", response_class=HTMLResponse)
async def analytics_home(request: Request, db: Database = Depends(get_db)) -> HTMLResponse:
    token_q = _token_q(request)
    companies = await db.list_companies(limit=100)
    rows = []
    for c in companies:
        q = token_q
        href = f"/analytics/ui/companies/{c['id']}" + (f"?{q}" if q else "")
        geo = f"/analytics/ui/geo/{c['id']}" + (f"?{q}" if q else "")
        rows.append(
            f"<tr><td><a href='{href}'>{_esc(c['name'])}</a></td>"
            f"<td><a href='{geo}'>Geo map</a></td>"
            f"<td>{_esc(c.get('latest_score'))}</td>"
            f"<td>{_esc(c.get('branch_count'))}</td>"
            f"<td>{_esc(c.get('review_count'))}</td></tr>"
        )
    body = f"""
    <p class="sub">Executive analytics over precomputed snapshots. Select a company.</p>
    <section class="panel wide">
      <h2>Companies</h2>
      <table>
        <thead><tr><th>Company</th><th>Geo</th><th>Score</th><th>Branches</th><th>Reviews</th></tr></thead>
        <tbody>{''.join(rows) or '<tr><td colspan="5">No companies — run seed_analytics_demo.py</td></tr>'}</tbody>
      </table>
    </section>
    """
    return HTMLResponse(_page("Executive Analytics", body, "{}", token_q))


@router.get("/companies/{company_id}", response_class=HTMLResponse)
async def company_dashboard_ui(
    company_id: int,
    request: Request,
    db: Database = Depends(get_db),
) -> HTMLResponse:
    filt = AnalyticsFilter.from_params(dict(request.query_params))
    token_q = _token_q(request)
    try:
        data = await AnalyticsService(db).company_dashboard(company_id, filt)
    except KeyError as exc:
        raise APIError(404, "company_not_found", str(exc)) from exc

    export_base = f"/analytics/companies/{company_id}/export"
    q = ("&" + token_q) if token_q else ""
    exports = "".join(
        f'<a href="{export_base}?format={fmt}{q}">{fmt.upper()}</a>'
        for fmt in ("json", "csv", "excel", "pdf", "png")
    )
    compare_href = (
        f"/analytics/ui/compare?mode=company&ids={company_id}&{token_q}"
        if token_q
        else f"/analytics/ui/compare?mode=company&ids={company_id}"
    )

    ranking_rows = []
    for b in data.get("branch_ranking") or []:
        href = f"/analytics/ui/branches/{b['branch_id']}" + (f"?{token_q}" if token_q else "")
        ranking_rows.append(
            {
                "name": b.get("name"),
                "score": b.get("score"),
                "google_rating": b.get("google_rating"),
                "review_count": b.get("review_count"),
                "city": b.get("city"),
                "province": b.get("province"),
                "link": href,
            }
        )

    ranking_html_rows = "".join(
        f"<tr><td><a href='{_esc(r['link'])}'>{_esc(r['name'])}</a></td>"
        f"<td>{_esc(r['score'])}</td><td>{_esc(r['google_rating'])}</td>"
        f"<td>{_esc(r['review_count'])}</td><td>{_esc(r['city'])}</td>"
        f"<td>{_esc(r['province'])}</td></tr>"
        for r in ranking_rows
    )

    body = f"""
    {_filter_form(f"/analytics/ui/companies/{company_id}", filt, token_q)}
    <div class="kpis">
      {_kpi("Overall Score", data.get("overall_score"))}
      {_kpi("Total Reviews", data.get("total_reviews"))}
      {_kpi("Branches", data.get("total_branches"))}
      {_kpi("Avg Rating", data.get("average_rating"))}
      {_kpi("CSI", data.get("customer_satisfaction_index"))}
      {_kpi("Confidence", data.get("confidence_score"))}
    </div>
    <div class="grid">
      <section class="panel wide">
        <h2>AI Executive Summary</h2>
        <p class="summary">{_esc(data.get("ai_executive_summary"))}</p>
        <p><strong>Strengths:</strong> {_pills(data.get("biggest_strengths") or [], "good")}</p>
        <p><strong>Improvements needed:</strong> {_pills(data.get("biggest_improvements_needed") or [], "bad")}</p>
      </section>
      {_chart_panel("Sentiment Distribution", "c_sentiment_pie")}
      {_chart_panel("Review Trend", "c_review_trend_line")}
      {_chart_panel("Rating Trend", "c_rating_trend_line")}
      {_chart_panel("Score Trend", "c_score_trend_line")}
      {_chart_panel("Complaint Categories", "c_complaints_bar")}
      {_chart_panel("Positive Categories", "c_positives_bar")}
      {_chart_panel("Province Distribution", "c_province_bar")}
      {_chart_panel("City Heatmap", "c_city_heatmap")}
      {_chart_panel("Branch Score Radar", "c_branch_radar")}
      {_chart_panel("Top Branches", "c_branch_score_bar")}
      <section class="panel wide">
        <h2>Branch Ranking</h2>
        <table>
          <thead><tr><th>Branch</th><th>Score</th><th>Google</th><th>Reviews</th><th>City</th><th>Province</th></tr></thead>
          <tbody>{ranking_html_rows or "<tr><td colspan='6'>No branches</td></tr>"}</tbody>
        </table>
      </section>
      {_table("Top Performing Branches", data.get("top_performing_branches") or [], [("name","Branch"),("score","Score"),("review_count","Reviews"),("city","City")])}
      {_table("Lowest Performing Branches", data.get("lowest_performing_branches") or [], [("name","Branch"),("score","Score"),("review_count","Reviews"),("city","City")])}
      <section class="panel wide">
        <h2>Export</h2>
        <div class="exports">{exports}<a href="{_esc(compare_href)}">Compare</a></div>
        <p class="sub">Cache: {_esc((data.get("cache") or {}).get("hit"))} · build {_esc((data.get("performance") or {}).get("build_ms"))} ms</p>
      </section>
    </div>
    """
    return HTMLResponse(
        _page(
            f"Company · {data.get('company_name')}",
            body,
            json.dumps(data.get("charts") or {}, ensure_ascii=False),
            token_q,
        )
    )


@router.get("/branches/{branch_id}", response_class=HTMLResponse)
async def branch_dashboard_ui(
    branch_id: int,
    request: Request,
    db: Database = Depends(get_db),
) -> HTMLResponse:
    filt = AnalyticsFilter.from_params(dict(request.query_params))
    token_q = _token_q(request)
    try:
        data = await AnalyticsService(db).branch_dashboard(branch_id, filt)
    except KeyError as exc:
        raise APIError(404, "branch_not_found", str(exc)) from exc

    export_base = f"/analytics/branches/{branch_id}/export"
    q = ("&" + token_q) if token_q else ""
    exports = "".join(
        f'<a href="{export_base}?format={fmt}{q}">{fmt.upper()}</a>'
        for fmt in ("json", "csv", "excel", "pdf", "png")
    )
    timeline_rows = "".join(
        f"<tr><td>{_esc(t.get('date'))}</td><td>{_esc(t.get('author'))}</td>"
        f"<td>{_esc(t.get('rating'))}</td><td>{_esc(t.get('sentiment'))}</td>"
        f"<td>{_esc(t.get('text'))}</td></tr>"
        for t in (data.get("review_timeline") or [])[-30:]
    )
    body = f"""
    {_filter_form(f"/analytics/ui/branches/{branch_id}", filt, token_q)}
    <div class="kpis">
      {_kpi("Branch Score", data.get("branch_score"))}
      {_kpi("Google Rating", data.get("google_rating"))}
      {_kpi("AI Rating", data.get("ai_rating"))}
      {_kpi("Reviews", data.get("review_count"))}
      {_kpi("CSI", data.get("customer_satisfaction_index"))}
      {_kpi("Confidence", data.get("confidence_score"))}
    </div>
    <div class="grid">
      <section class="panel wide">
        <h2>AI Branch Summary</h2>
        <p class="summary">{_esc(data.get("ai_branch_summary"))}</p>
        <p><strong>Improvement suggestions:</strong> {_pills(data.get("improvement_suggestions") or [], "bad")}</p>
        <p class="sub">{_esc(data.get("city"))} · {_esc(data.get("province"))} · {_esc(data.get("company_name"))}</p>
      </section>
      {_chart_panel("Rating Trend", "c_rating_trend_line")}
      {_chart_panel("Score Trend", "c_score_trend_line")}
      {_chart_panel("Monthly Review Volume", "c_monthly_volume_bar")}
      {_chart_panel("Complaint Breakdown", "c_complaints_bar")}
      {_chart_panel("Positive Breakdown", "c_positives_bar")}
      {_chart_panel("Sentiment", "c_sentiment_pie")}
      {_chart_panel("Delivery Speed", "c_delivery_stacked")}
      {_chart_panel("Dimensions Radar", "c_dimensions_radar")}
      {_chart_panel("Review Timeline", "c_timeline", wide=True)}
      {_table("Staff Mentions", data.get("staff_mentions") or [], [("name","Staff"),("count","Mentions"),("share","Share")])}
      {_table("Customer Service", data.get("customer_service_analysis") or [], [("name","Level"),("count","Count")])}
      {_table("Package Damage", data.get("package_damage_analysis") or [], [("name","Status"),("count","Count")])}
      {_table("Tracking Quality", data.get("tracking_quality") or [], [("name","Level"),("count","Count")])}
      {_table("Pricing", data.get("pricing_analysis") or [], [("name","Level"),("count","Count")])}
      {_table("Professionalism", data.get("professionalism_analysis") or [], [("name","Level"),("count","Count")])}
      {_table("Historical Score Changes", data.get("historical_changes") or [], [("date","Date"),("score","Score")], wide=True)}
      <section class="panel wide">
        <h2>Review Timeline (detail)</h2>
        <table>
          <thead><tr><th>Date</th><th>Author</th><th>Rating</th><th>Sentiment</th><th>Text</th></tr></thead>
          <tbody>{timeline_rows or "<tr><td colspan='5'>No reviews</td></tr>"}</tbody>
        </table>
      </section>
      <section class="panel wide">
        <h2>Export</h2>
        <div class="exports">{exports}</div>
      </section>
    </div>
    """
    return HTMLResponse(
        _page(
            f"Branch · {data.get('branch_name')}",
            body,
            json.dumps(data.get("charts") or {}, ensure_ascii=False),
            token_q,
        )
    )


@router.get("/compare", response_class=HTMLResponse)
async def compare_ui(
    request: Request,
    db: Database = Depends(get_db),
) -> HTMLResponse:
    token_q = _token_q(request)
    mode = request.query_params.get("mode") or "company"
    ids = [int(x) for x in (request.query_params.get("ids") or "").split(",") if x.strip().isdigit()]
    names = [x.strip() for x in (request.query_params.get("names") or "").split(",") if x.strip()]
    filt = AnalyticsFilter.from_params(dict(request.query_params))
    try:
        data = await AnalyticsService(db).compare(
            mode=mode, ids=ids or None, names=names or None, filt=filt
        )
    except (KeyError, ValueError) as exc:
        raise APIError(400, "compare_error", str(exc)) from exc

    rows = "".join(
        f"<tr><td>{_esc(r.get('label'))}</td><td>{_esc(r.get('overall_score'))}</td>"
        f"<td>{_esc(r.get('average_rating'))}</td><td>{_esc(r.get('total_reviews'))}</td>"
        f"<td>{_esc(r.get('csi'))}</td></tr>"
        for r in data.get("comparison") or []
    )
    body = f"""
    <p class="sub">Comparison mode: {_esc(mode)}</p>
    <div class="grid">
      {_chart_panel("Score comparison", "c_score_bar")}
      {_chart_panel("CSI comparison", "c_csi_bar")}
      {_chart_panel("Review volume", "c_reviews_bar")}
      <section class="panel wide">
        <h2>Comparison table</h2>
        <table>
          <thead><tr><th>Entity</th><th>Score</th><th>Avg rating</th><th>Reviews</th><th>CSI</th></tr></thead>
          <tbody>{rows or "<tr><td colspan='5'>No entities</td></tr>"}</tbody>
        </table>
      </section>
    </div>
    """
    return HTMLResponse(
        _page(
            f"Compare · {mode}",
            body,
            json.dumps(data.get("charts") or {}, ensure_ascii=False),
            token_q,
        )
    )
