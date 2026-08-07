"""Phase 11 — Geographic analytics dashboard (Plotly, visualization only)."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse

from analytics.filters import AnalyticsFilter
from analytics.service import AnalyticsService
from api.auth import require_api_token, token_from_request
from api.deps import get_db
from api.errors import APIError
from core.db import Database

router = APIRouter(
    prefix="/analytics/ui",
    tags=["analytics-ui-geo"],
    dependencies=[Depends(require_api_token)],
)

GEOJSON_PATH = Path(__file__).resolve().parents[1] / "static" / "geo" / "iran_provinces.geojson"


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _token_q(request: Request) -> str:
    tok = token_from_request(request) or ""
    return urlencode({"api_token": tok}) if tok else ""


_CSS = """
:root {
  --bg0: #071018;
  --bg1: #0d1a24;
  --panel: rgba(14, 28, 40, 0.92);
  --line: #243746;
  --text: #e7f0f6;
  --muted: #8aa0b2;
  --accent: #3db8a0;
  --serif: "Fraunces", "Iowan Old Style", Georgia, serif;
  --sans: "IBM Plex Sans", "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: var(--sans);
  color: var(--text);
  background:
    radial-gradient(1000px 520px at 8% -8%, #16364a 0%, transparent 55%),
    radial-gradient(800px 420px at 92% 0%, #1d3a2a 0%, transparent 50%),
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
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px;
  margin: 12px 0 18px;
}
.filters label { display:block; font-size:.72rem; color:var(--muted); margin-bottom:4px; }
.filters input, .filters button {
  width: 100%; padding: 8px 10px; border-radius: 8px;
  border: 1px solid var(--line); background: #0a1520; color: var(--text);
}
.filters button {
  background: linear-gradient(180deg, #3db8a0, #2a8f7b);
  border: 0; font-weight: 600; cursor: pointer; margin-top: 18px;
}
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.kpi {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px 16px;
  opacity: 0;
  transform: translateY(8px);
  animation: rise .45s ease forwards;
}
.kpi:nth-child(2){animation-delay:.04s}
.kpi:nth-child(3){animation-delay:.08s}
.kpi:nth-child(4){animation-delay:.12s}
.kpi:nth-child(5){animation-delay:.16s}
.kpi:nth-child(6){animation-delay:.2s}
.kpi:nth-child(7){animation-delay:.24s}
.kpi .label { color: var(--muted); font-size: .75rem; }
.kpi .value {
  font-family: var(--serif);
  font-size: 1.65rem;
  margin-top: 6px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 14px;
}
.panel {
  grid-column: span 6;
  background: var(--panel);
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
.chart { width: 100%; min-height: 320px; }
.chart.map { min-height: 540px; }
.chart.heat { min-height: 480px; }
.toolbar {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin-bottom: 10px;
}
.toolbar input {
  flex: 1; min-width: 180px; padding: 8px 10px; border-radius: 8px;
  border: 1px solid var(--line); background: #0a1520; color: var(--text);
}
.exports a, .toolbar a, .toolbar button {
  display: inline-block; margin: 0; padding: 8px 12px;
  border: 1px solid var(--line); border-radius: 8px; color: var(--text);
  background: #101c28; cursor: pointer; font: inherit;
}
table { width: 100%; border-collapse: collapse; font-size: .85rem; }
th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; cursor: pointer; user-select: none; }
th:hover { color: var(--text); }
.legend {
  display: flex; flex-wrap: wrap; gap: 10px; color: var(--muted); font-size: .78rem;
  margin-top: 8px;
}
.swatch { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:4px; vertical-align:middle; }
@media (max-width: 900px) {
  .panel, .panel.wide { grid-column: span 12; }
  main, header { padding-left: 16px; padding-right: 16px; }
  .chart.map, .chart.heat { min-height: 360px; }
}
@keyframes rise { to { opacity: 1; transform: translateY(0); } }
"""


def _kpi(label: str, value: Any) -> str:
    return (
        f'<div class="kpi"><div class="label">{_esc(label)}</div>'
        f'<div class="value">{_esc(value)}</div></div>'
    )


def _filter_form(action: str, filt: AnalyticsFilter, token_q: str) -> str:
    f = filt.to_dict()

    def val(key: str) -> str:
        v = f.get(key)
        return _esc(v if v is not None else "")

    tok_hidden = ""
    if token_q:
        tok = token_q.split("=", 1)[-1]
        tok_hidden = f'<input type="hidden" name="api_token" value="{_esc(tok)}" />'
    return f"""
    <form class="filters" method="get" action="{_esc(action)}">
      {tok_hidden}
      <div><label>Province</label><input name="province" value="{val('province')}"/></div>
      <div><label>City</label><input name="city" value="{val('city')}"/></div>
      <div><label>Min reviews</label><input name="min_review_count" value="{val('min_review_count')}"/></div>
      <div><label>Date from</label><input name="date_from" value="{val('date_from')}" placeholder="YYYY-MM-DD"/></div>
      <div><label>Date to</label><input name="date_to" value="{val('date_to')}" placeholder="YYYY-MM-DD"/></div>
      <div><button type="submit">Apply filters</button></div>
    </form>
    """


@router.get("/geo/iran.geojson")
async def iran_provinces_geojson() -> FileResponse:
    if not GEOJSON_PATH.exists():
        raise APIError(404, "geojson_missing", "Iran provinces GeoJSON not found")
    return FileResponse(GEOJSON_PATH, media_type="application/geo+json")


@router.get("/geo/{company_id}", response_class=HTMLResponse)
async def geo_dashboard_ui(
    company_id: int,
    request: Request,
    db: Database = Depends(get_db),
) -> HTMLResponse:
    filt = AnalyticsFilter.from_params(dict(request.query_params))
    token_q = _token_q(request)
    try:
        data = await AnalyticsService(db).geo_dashboard(company_id, filt)
    except KeyError as exc:
        raise APIError(404, "company_not_found", str(exc)) from exc

    kpis = data.get("kpis") or {}
    q = ("&" + token_q) if token_q else ""
    export_base = f"/analytics/companies/{company_id}/geo/export"
    exports = "".join(
        f'<a href="{export_base}?format={fmt}{q}" id="export-{fmt}">{fmt.upper()}</a>'
        for fmt in ("csv", "excel", "pdf", "png", "json")
    )
    exec_href = (
        f"/analytics/ui/companies/{company_id}" + (f"?{token_q}" if token_q else "")
    )
    home_q = f"?{token_q}" if token_q else ""

    kpi_html = "".join(
        [
            _kpi("Total branches", kpis.get("total_branches")),
            _kpi("Total reviews", kpis.get("total_reviews")),
            _kpi("Average score", kpis.get("average_score")),
            _kpi("Highest score", kpis.get("highest_score")),
            _kpi("Lowest score", kpis.get("lowest_score")),
            _kpi("Avg Google rating", kpis.get("average_google_rating")),
            _kpi("Coverage %", kpis.get("coverage_pct")),
        ]
    )

    payload_json = json.dumps(data, ensure_ascii=False)
    action = f"/analytics/ui/geo/{company_id}"

    body = f"""
    <p class="sub">Geographic analytics for <strong>{_esc(data.get('company_name'))}</strong>
      · <a href="{_esc(exec_href)}">Executive dashboard</a></p>
    {_filter_form(action, filt, token_q)}
    <div class="kpis">{kpi_html}</div>
    <div class="exports" style="margin-bottom:14px">{exports}
      <button type="button" id="btn-png-map">PNG (map)</button>
      <button type="button" id="btn-pdf-page">PDF (page)</button>
    </div>
    <div class="grid">
      <section class="panel wide">
        <h2>Iran map — Tipax branches</h2>
        <div id="map" class="chart map"></div>
        <div class="legend">
          <span><i class="swatch" style="background:#15803d"></i>Score ≥80</span>
          <span><i class="swatch" style="background:#4ade80"></i>65–79</span>
          <span><i class="swatch" style="background:#eab308"></i>50–64</span>
          <span><i class="swatch" style="background:#f97316"></i>35–49</span>
          <span><i class="swatch" style="background:#dc2626"></i>&lt;35</span>
          <span>Marker size ∝ review count</span>
        </div>
      </section>
      <section class="panel">
        <h2>Top 10 best branches</h2>
        <div id="topBest" class="chart"></div>
      </section>
      <section class="panel">
        <h2>Top 10 worst branches</h2>
        <div id="topWorst" class="chart"></div>
      </section>
      <section class="panel wide">
        <h2>Province heatmap (average score)</h2>
        <div id="heat" class="chart heat"></div>
      </section>
      <section class="panel">
        <h2>Review distribution</h2>
        <div id="reviewHist" class="chart"></div>
      </section>
      <section class="panel">
        <h2>Score distribution</h2>
        <div id="scoreHist" class="chart"></div>
      </section>
      <section class="panel wide">
        <h2>Branch leaderboard</h2>
        <div class="toolbar">
          <input id="tableSearch" type="search" placeholder="Search branch, province, city…"/>
        </div>
        <div style="overflow:auto; max-height:480px">
          <table id="leaderboard">
            <thead>
              <tr>
                <th data-key="rank">Rank</th>
                <th data-key="branch">Branch</th>
                <th data-key="province">Province</th>
                <th data-key="city">City</th>
                <th data-key="reviews">Reviews</th>
                <th data-key="google_rating">Google Rating</th>
                <th data-key="ai_score">AI Score</th>
                <th data-key="csi">CSI</th>
                <th data-key="confidence">Confidence</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>
    </div>
    """

    page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Geo Analytics · {_esc(data.get('company_name'))} · BrandMonitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/plotly.js@2.35.2/dist/plotly.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jspdf@2.5.2/dist/jspdf.umd.min.js"></script>
<style>{_CSS}</style>
</head><body>
<header>
  <div>
    <p class="brand">BrandMonitor</p>
    <p class="sub">Phase 11 · Geographic Analytics</p>
  </div>
  <nav>
    <a href="/analytics/ui{home_q}">Analytics home</a>
    <a href="{_esc(exec_href)}">Executive</a>
    <a href="/docs">API</a>
  </nav>
</header>
<main>{body}</main>
<script>
const DATA = {payload_json};
const GEO_URL = "/analytics/ui/geo/iran.geojson";
const layoutDark = {{
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: {{ color: "#c9d6ea", family: "IBM Plex Sans, sans-serif" }},
  margin: {{ t: 24, r: 16, b: 40, l: 16 }},
}};

function hBar(divId, rows, title) {{
  const labels = rows.map(r => r.branch).reverse();
  const scores = rows.map(r => r.score).reverse();
  const provinces = rows.map(r => r.province).reverse();
  const reviews = rows.map(r => r.review_count).reverse();
  Plotly.newPlot(divId, [{{
    type: "bar",
    orientation: "h",
    y: labels,
    x: scores,
    text: scores.map((s,i) => `${{s}} · ${{reviews[i]}} reviews · ${{provinces[i]}}`),
    textposition: "auto",
    marker: {{ color: scores.map(s => s >= 80 ? "#15803d" : s >= 65 ? "#4ade80" : s >= 50 ? "#eab308" : s >= 35 ? "#f97316" : "#dc2626") }},
    hovertemplate: "%{{y}}<br>Score: %{{x}}<br>%{{text}}<extra></extra>"
  }}], {{
    ...layoutDark,
    title: {{ text: title, font: {{ size: 13 }} }},
    margin: {{ t: 36, r: 20, b: 40, l: 140 }},
    xaxis: {{ title: "Score", gridcolor: "rgba(42,58,85,.45)", range: [0, 100] }},
    yaxis: {{ automargin: true }},
  }}, {{responsive: true, displayModeBar: false}});
}}

function hist(divId, dist, title, color) {{
  Plotly.newPlot(divId, [{{
    type: "bar",
    x: dist.labels,
    y: dist.values,
    marker: {{ color }},
    hovertemplate: "Bucket %{{x}}<br>Branches: %{{y}}<extra></extra>"
  }}], {{
    ...layoutDark,
    title: {{ text: title, font: {{ size: 13 }} }},
    xaxis: {{ title: "", gridcolor: "rgba(42,58,85,.35)" }},
    yaxis: {{ title: "Branches", gridcolor: "rgba(42,58,85,.35)" }},
  }}, {{responsive: true, displayModeBar: false}});
}}

async function renderMap() {{
  const geo = await fetch(GEO_URL).then(r => r.json());
  const heat = DATA.province_heatmap || [];
  const z = heat.map(p => p.average_score);
  const locs = heat.map(p => p.province);
  const text = heat.map(p => `${{p.province}}<br>Branches: ${{p.branches}}<br>Reviews: ${{p.reviews}}<br>Avg score: ${{p.average_score ?? "n/a"}}`);

  const choropleth = {{
    type: "choropleth",
    locationmode: "geojson-id",
    locations: locs,
    z: z,
    geojson: geo,
    featureidkey: "properties.name",
    text,
    hovertemplate: "%{{text}}<extra></extra>",
    colorscale: [
      [0, "#dc2626"], [0.35, "#f97316"], [0.5, "#eab308"],
      [0.65, "#4ade80"], [0.8, "#15803d"], [1, "#166534"]
    ],
    zmin: 0, zmax: 100,
    colorbar: {{ title: "Avg score", bgcolor: "rgba(0,0,0,0)", tickfont: {{ color: "#c9d6ea" }} }},
    marker: {{ line: {{ color: "#1f3344", width: 0.6 }} }},
  }};

  const pins = DATA.map_pins || [];
  const sizes = pins.map(p => Math.max(8, Math.min(28, 6 + Math.sqrt(p.review_count || 0) * 3)));
  const scatter = {{
    type: "scattergeo",
    lon: pins.map(p => p.longitude),
    lat: pins.map(p => p.latitude),
    text: pins.map(p => p.name),
    customdata: pins,
    mode: "markers",
    marker: {{
      size: sizes,
      color: pins.map(p => p.marker_color),
      line: {{ width: 0.8, color: "#0b1220" }},
      opacity: 0.92,
    }},
    hovertemplate: "<b>%{{customdata.name}}</b><br>%{{customdata.province}} / %{{customdata.city}}<br>Score: %{{customdata.score}}<br>Reviews: %{{customdata.review_count}}<br>Google: %{{customdata.google_rating}}<extra></extra>",
  }};

  await Plotly.newPlot("map", [choropleth, scatter], {{
    ...layoutDark,
    margin: {{ t: 10, r: 10, b: 10, l: 10 }},
    geo: {{
      scope: "asia",
      resolution: 50,
      showland: true,
      landcolor: "#0f1c28",
      showocean: true,
      oceancolor: "#071018",
      showlakes: false,
      showcountries: false,
      showframe: false,
      bgcolor: "rgba(0,0,0,0)",
      projection: {{ type: "mercator" }},
      center: {{ lon: 53.5, lat: 32.5 }},
      lonaxis: {{ range: [43.5, 64.0] }},
      lataxis: {{ range: [24.5, 40.5] }},
    }},
  }}, {{responsive: true}});

  document.getElementById("map").on("plotly_click", (ev) => {{
    const pt = ev.points && ev.points[0];
    if (!pt || !pt.customdata) return;
    const b = pt.customdata;
    const html = [
      `<b>${{b.name}}</b>`,
      `Province: ${{b.province}}`,
      `City: ${{b.city || "—"}}`,
      `Reviews: ${{b.review_count}}`,
      `Score: ${{b.score ?? "n/a"}}`,
      `Google rating: ${{b.google_rating}}`,
      `AI summary: ${{b.ai_summary || "—"}}`,
      `Top complaints: ${{(b.top_complaints || []).join(", ") || "—"}}`,
      `Top positives: ${{(b.top_positives || []).join(", ") || "—"}}`,
    ].join("<br>");
    Plotly.Fx.hover("map", [{{ curveNumber: pt.curveNumber, pointNumber: pt.pointNumber }}]);
    const existing = document.getElementById("pin-pop");
    if (existing) existing.remove();
    const div = document.createElement("div");
    div.id = "pin-pop";
    div.style.cssText = "position:fixed;right:24px;bottom:24px;max-width:360px;z-index:30;background:#102030;border:1px solid #2a3f52;border-radius:12px;padding:14px 16px;box-shadow:0 12px 40px rgba(0,0,0,.45);line-height:1.45;font-size:.9rem";
    div.innerHTML = html + '<div style="margin-top:10px"><button id="pin-close" style="padding:6px 10px;border-radius:8px;border:1px solid #2a3f52;background:#0a1520;color:#e7f0f6;cursor:pointer">Close</button></div>';
    document.body.appendChild(div);
    document.getElementById("pin-close").onclick = () => div.remove();
  }});
}}

async function renderHeatOnly() {{
  const geo = await fetch(GEO_URL).then(r => r.json());
  const heat = DATA.province_heatmap || [];
  Plotly.newPlot("heat", [{{
    type: "choropleth",
    locationmode: "geojson-id",
    locations: heat.map(p => p.province),
    z: heat.map(p => p.average_score),
    geojson: geo,
    featureidkey: "properties.name",
    text: heat.map(p => `${{p.province}}<br>Branches: ${{p.branches}}<br>Reviews: ${{p.reviews}}<br>Avg score: ${{p.average_score ?? "n/a"}}`),
    hovertemplate: "%{{text}}<extra></extra>",
    colorscale: [
      [0, "#dc2626"], [0.35, "#f97316"], [0.5, "#eab308"],
      [0.65, "#4ade80"], [0.8, "#15803d"], [1, "#166534"]
    ],
    zmin: 0, zmax: 100,
    colorbar: {{ title: "Avg", bgcolor: "rgba(0,0,0,0)" }},
    marker: {{ line: {{ color: "#1f3344", width: 0.5 }} }},
  }}], {{
    ...layoutDark,
    margin: {{ t: 10, r: 10, b: 10, l: 10 }},
    geo: {{
      scope: "asia",
      resolution: 50,
      showland: true,
      landcolor: "#0f1c28",
      showocean: true,
      oceancolor: "#071018",
      showframe: false,
      bgcolor: "rgba(0,0,0,0)",
      projection: {{ type: "mercator" }},
      center: {{ lon: 53.5, lat: 32.5 }},
      lonaxis: {{ range: [43.5, 64.0] }},
      lataxis: {{ range: [24.5, 40.5] }},
    }},
  }}, {{responsive: true, displayModeBar: false}});
}}

function renderTable() {{
  const rows = [...(DATA.leaderboard || [])];
  let sortKey = "rank";
  let asc = true;
  const tbody = document.querySelector("#leaderboard tbody");
  const search = document.getElementById("tableSearch");

  function draw() {{
    const q = (search.value || "").trim().toLowerCase();
    let view = rows.filter(r => !q || [r.branch, r.province, r.city].join(" ").toLowerCase().includes(q));
    view.sort((a,b) => {{
      const av = a[sortKey], bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return asc ? av - bv : bv - av;
      return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    }});
    tbody.innerHTML = view.map(r => `<tr>
      <td>${{r.rank}}</td><td>${{r.branch}}</td><td>${{r.province}}</td><td>${{r.city || ""}}</td>
      <td>${{r.reviews}}</td><td>${{r.google_rating}}</td><td>${{r.ai_score ?? ""}}</td>
      <td>${{r.csi}}</td><td>${{r.confidence}}</td>
    </tr>`).join("") || `<tr><td colspan="9">No rows</td></tr>`;
  }}

  document.querySelectorAll("#leaderboard th").forEach(th => {{
    th.addEventListener("click", () => {{
      const key = th.getAttribute("data-key");
      if (sortKey === key) asc = !asc; else {{ sortKey = key; asc = true; }}
      draw();
    }});
  }});
  search.addEventListener("input", draw);
  draw();
}}

hBar("topBest", DATA.top10_best || [], "");
hBar("topWorst", DATA.top10_worst || [], "");
hist("reviewHist", DATA.review_distribution || {{labels:[], values:[]}}, "Branches by review-count bucket", "#3db8a0");
hist("scoreHist", DATA.score_distribution || {{labels:[], values:[]}}, "Branches by AI score bucket", "#3d9cf0");
renderTable();
renderMap();
renderHeatOnly();

document.getElementById("btn-png-map").addEventListener("click", async () => {{
  const url = await Plotly.toImage("map", {{format: "png", width: 1400, height: 900}});
  const a = document.createElement("a");
  a.href = url; a.download = "tipax_geo_map.png"; a.click();
}});

document.getElementById("btn-pdf-page").addEventListener("click", async () => {{
  const canvas = await html2canvas(document.querySelector("main"), {{backgroundColor: "#0d1a24", scale: 1}});
  const img = canvas.toDataURL("image/png");
  const {{ jsPDF }} = window.jspdf;
  const pdf = new jsPDF({{ orientation: "landscape", unit: "pt", format: "a4" }});
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const ratio = Math.min(pageW / canvas.width, pageH / canvas.height);
  pdf.addImage(img, "PNG", 10, 10, canvas.width * ratio, canvas.height * ratio);
  pdf.save("tipax_geo_dashboard.pdf");
}});
</script>
</body></html>"""
    return HTMLResponse(page)
