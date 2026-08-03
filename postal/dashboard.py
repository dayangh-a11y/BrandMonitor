"""Generate Postal Intelligence HTML dashboards (Chart.js + Leaflet)."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from postal.db import PostalIntelligenceDB


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


_CSS = """
:root {
  --bg: #0f1a17;
  --panel: #16241f;
  --line: #2a433a;
  --text: #e7f2ec;
  --muted: #9bb5a8;
  --accent: #2f9e7a;
  --good: #3ecf8e;
  --warn: #e0b44e;
  --bad: #e07171;
  --serif: "Fraunces", Georgia, serif;
  --sans: "IBM Plex Sans", "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0; color: var(--text); font-family: var(--sans);
  background:
    radial-gradient(800px 420px at 0% 0%, #1d3b32 0%, transparent 55%),
    radial-gradient(700px 380px at 100% 0%, #243018 0%, transparent 50%),
    linear-gradient(180deg, #0c1412, var(--bg));
  min-height: 100vh;
}
a { color: #7dd3b0; text-decoration: none; }
header { padding: 24px 28px 8px; }
.brand { font-family: var(--serif); font-size: clamp(1.8rem, 3vw, 2.5rem); margin: 0; letter-spacing: -0.02em; }
.sub { color: var(--muted); margin-top: 4px; }
nav { padding: 0 28px 12px; display: flex; flex-wrap: wrap; gap: 12px; }
nav a { color: var(--muted); }
nav a:hover, nav a.active { color: var(--text); }
main { padding: 8px 28px 40px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 14px 0 18px; }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 14px; }
.kpi .label { color: var(--muted); font-size: .75rem; }
.kpi .value { font-family: var(--serif); font-size: 1.6rem; margin-top: 4px; }
.grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
.card { background: rgba(22,36,31,.92); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; }
.card h2 { margin: 0 0 10px; font-size: 1rem; font-weight: 600; }
.span-12 { grid-column: span 12; }
.span-8 { grid-column: span 8; }
.span-6 { grid-column: span 6; }
.span-4 { grid-column: span 4; }
@media (max-width: 900px) {
  .span-8, .span-6, .span-4 { grid-column: span 12; }
}
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
th, td { padding: 8px 6px; border-bottom: 1px solid var(--line); text-align: left; }
th { color: var(--muted); font-weight: 500; }
.bar {
  height: 8px; border-radius: 99px; background: #24352e; overflow: hidden;
}
.bar > span { display:block; height:100%; background: linear-gradient(90deg, #2f9e7a, #7dd3b0); }
#map { height: 420px; border-radius: 12px; border: 1px solid var(--line); }
.muted { color: var(--muted); font-size: .85rem; }
"""


def _shell(title: str, active: str, body: str, extra_head: str = "") -> str:
    nav = [
        ("index.html", "Overview"),
        ("company_ranking.html", "Company Ranking"),
        ("branch_ranking.html", "Branch Ranking"),
        ("province_ranking.html", "Province Ranking"),
        ("complaints.html", "Complaints"),
        ("sentiment.html", "Sentiment"),
        ("trends.html", "Trends"),
        ("map.html", "Interactive Map"),
        ("comparison.html", "Comparison"),
    ]
    links = " ".join(
        f'<a class="{"active" if href==active else ""}" href="{href}">{label}</a>'
        for href, label in nav
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title)} · BrandMonitor Postal Intelligence</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
{extra_head}
<style>{_CSS}</style>
</head>
<body>
<header>
  <p class="brand">BrandMonitor</p>
  <p class="sub">Postal Intelligence Platform — {_esc(title)}</p>
</header>
<nav>{links}</nav>
<main>
{body}
</main>
</body>
</html>
"""


def render_overview(pi: PostalIntelligenceDB) -> str:
    scores = pi.latest_company_scores()
    branches = pi.list_branch_intelligence(limit=100000)
    n_reviews = pi.conn.execute("SELECT COUNT(*) n FROM pi_reviews").fetchone()["n"]
    n_companies = len(scores)
    top = scores[0] if scores else None
    labels = [s["name"] for s in scores]
    values = [s["score"] for s in scores]
    body = f"""
<section class="kpis">
  <div class="kpi"><div class="label">Companies</div><div class="value">{n_companies}</div></div>
  <div class="kpi"><div class="label">Branches scored</div><div class="value">{len(branches)}</div></div>
  <div class="kpi"><div class="label">Reviews</div><div class="value">{n_reviews}</div></div>
  <div class="kpi"><div class="label">Top score</div><div class="value">{_esc(top['score'] if top else '—')}</div></div>
</section>
<section class="grid">
  <div class="card span-8">
    <h2>Company Ranking (Postal Score 0–100)</h2>
    <canvas id="rankChart" height="120"></canvas>
  </div>
  <div class="card span-4">
    <h2>Leaders</h2>
    <table>
      <tr><th>#</th><th>Company</th><th>Score</th></tr>
      {''.join(f"<tr><td>{i+1}</td><td>{_esc(s['name'])}</td><td>{s['score']}</td></tr>" for i,s in enumerate(scores[:6]))}
    </table>
    <p class="muted">Weights are configurable in config/scoring_weights.yaml. See SCORING_METHODOLOGY.md.</p>
  </div>
</section>
<script>
const ctx = document.getElementById('rankChart');
new Chart(ctx, {{
  type: 'bar',
  data: {{
    labels: {json.dumps(labels)},
    datasets: [{{ label: 'Postal Score', data: {json.dumps(values)}, backgroundColor: '#2f9e7a' }}]
  }},
  options: {{
    indexAxis: 'y',
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ min: 0, max: 100, ticks: {{ color: '#9bb5a8' }}, grid: {{ color: '#2a433a' }} }},
      y: {{ ticks: {{ color: '#e7f2ec' }}, grid: {{ display: false }} }}
    }}
  }}
}});
</script>
"""
    return _shell("Overview", "index.html", body)


def render_company_ranking(pi: PostalIntelligenceDB) -> str:
    scores = pi.latest_company_scores()
    rows = []
    for i, s in enumerate(scores, 1):
        dims = s.get("dimensions") or {}
        cells = "".join(
            f"<td title=\"{_esc((dims.get(k) or {}).get('explanation',''))}\">{(dims.get(k) or {}).get('score','')}</td>"
            for k in [
                "customer_satisfaction", "delivery_speed", "service_coverage", "pricing",
                "service_variety", "transparency", "complaint_rate", "branch_quality",
            ]
        )
        rows.append(
            f"<tr><td>{i}</td><td>{_esc(s['name'])}</td><td><strong>{s['score']}</strong></td>{cells}</tr>"
        )
    body = f"""
<section class="card span-12">
  <h2>Company Ranking — dimension breakdown</h2>
  <p class="muted">Hover dimension cells for formula explanations. Score = Σ weight × dimension.</p>
  <div style="overflow:auto">
  <table>
    <tr>
      <th>#</th><th>Company</th><th>Score</th>
      <th>Sat</th><th>Speed</th><th>Coverage</th><th>Price</th>
      <th>Variety</th><th>Transparency</th><th>Complaints</th><th>Branches</th>
    </tr>
    {''.join(rows)}
  </table>
  </div>
</section>
"""
    return _shell("Company Ranking", "company_ranking.html", body)


def render_branch_ranking(pi: PostalIntelligenceDB) -> str:
    branches = pi.list_branch_intelligence(limit=100)
    rows = []
    for i, b in enumerate(branches, 1):
        rows.append(
            f"<tr><td>{i}</td><td>{_esc(b['company_name'])}</td><td>{_esc(b['branch_name'])}</td>"
            f"<td>{_esc(b.get('city'))}</td><td>{_esc(b.get('province'))}</td>"
            f"<td>{b['branch_score']}</td><td>{b['overall_rating']}</td><td>{b['review_count']}</td>"
            f"<td>{_esc(b.get('last_activity') or '')[:10]}</td></tr>"
        )
    body = f"""
<section class="card">
  <h2>Branch Ranking (top 100)</h2>
  <table>
    <tr><th>#</th><th>Company</th><th>Branch</th><th>City</th><th>Province</th>
    <th>Score</th><th>Rating</th><th>Reviews</th><th>Last activity</th></tr>
    {''.join(rows)}
  </table>
</section>
"""
    return _shell("Branch Ranking", "branch_ranking.html", body)


def render_province_ranking(pi: PostalIntelligenceDB) -> str:
    geo = [g for g in pi.list_geo_rankings("province") if g["rank"] == 1]
    geo.sort(key=lambda g: float(g["score"]), reverse=True)
    rows = "".join(
        f"<tr><td>{_esc(g['geo_name'])}</td><td>{_esc(g['company_name'])}</td>"
        f"<td>{g['score']}</td><td>{g['review_count']}</td><td>{g['branch_count']}</td></tr>"
        for g in geo[:40]
    )
    body = f"""
<section class="card">
  <h2>Province leaders (rank #1 per province)</h2>
  <table>
    <tr><th>Province</th><th>Leading company</th><th>Score</th><th>Reviews</th><th>Branches</th></tr>
    {rows}
  </table>
</section>
"""
    return _shell("Province Ranking", "province_ranking.html", body)


def render_complaints(pi: PostalIntelligenceDB) -> str:
    labels = []
    datasets_map: dict[str, list[int]] = {}
    companies = pi.list_companies()
    all_cats: set[str] = set()
    per = {}
    for c in companies:
        stats = pi.company_review_stats(int(c["id"]))
        per[c["name"]] = stats.get("complaints") or {}
        all_cats.update(per[c["name"]].keys())
    cats = sorted(all_cats) or ["other"]
    labels = [c["name"] for c in companies]
    colors = ["#2f9e7a", "#e0b44e", "#e07171", "#5b8def", "#c084fc", "#f472b6"]
    datasets = []
    for i, cat in enumerate(cats):
        datasets.append(
            {
                "label": cat,
                "data": [int(per[name].get(cat, 0)) for name in labels],
                "backgroundColor": colors[i % len(colors)],
            }
        )
    body = f"""
<section class="card">
  <h2>Complaint Dashboard</h2>
  <canvas id="cChart" height="120"></canvas>
</section>
<script>
new Chart(document.getElementById('cChart'), {{
  type: 'bar',
  data: {{ labels: {json.dumps(labels)}, datasets: {json.dumps(datasets)} }},
  options: {{
    responsive: true,
    scales: {{
      x: {{ stacked: true, ticks: {{ color: '#e7f2ec' }}, grid: {{ color: '#2a433a' }} }},
      y: {{ stacked: true, ticks: {{ color: '#9bb5a8' }}, grid: {{ color: '#2a433a' }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#e7f2ec' }} }} }}
  }}
}});
</script>
"""
    return _shell("Complaints", "complaints.html", body)


def render_sentiment(pi: PostalIntelligenceDB) -> str:
    labels = []
    pos, neu, neg = [], [], []
    for c in pi.list_companies():
        stats = pi.company_review_stats(int(c["id"]))
        s = stats.get("sentiments") or {}
        labels.append(c["name"])
        pos.append(int(s.get("Positive", 0)))
        neu.append(int(s.get("Neutral", 0)))
        neg.append(int(s.get("Negative", 0)))
    body = f"""
<section class="card">
  <h2>Sentiment Dashboard</h2>
  <canvas id="sChart" height="120"></canvas>
</section>
<script>
new Chart(document.getElementById('sChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(labels)},
    datasets: [
      {{ label: 'Positive', data: {json.dumps(pos)}, backgroundColor: '#3ecf8e' }},
      {{ label: 'Neutral', data: {json.dumps(neu)}, backgroundColor: '#e0b44e' }},
      {{ label: 'Negative', data: {json.dumps(neg)}, backgroundColor: '#e07171' }}
    ]
  }},
  options: {{
    scales: {{
      x: {{ stacked: true, ticks: {{ color: '#e7f2ec' }}, grid: {{ color: '#2a433a' }} }},
      y: {{ stacked: true, ticks: {{ color: '#9bb5a8' }}, grid: {{ color: '#2a433a' }} }}
    }},
    plugins: {{ legend: {{ labels: {{ color: '#e7f2ec' }} }} }}
  }}
}});
</script>
"""
    return _shell("Sentiment", "sentiment.html", body)


def render_trends(pi: PostalIntelligenceDB) -> str:
    # Aggregate review trend across all branches by month
    from collections import Counter

    trend: Counter[str] = Counter()
    for b in pi.list_branch_intelligence(limit=100000):
        for point in b.get("review_trend") or []:
            month = point.get("month") or "unknown"
            if month == "unknown":
                continue
            trend[month] += int(point.get("count") or 0)
    months = sorted(trend.keys())
    counts = [trend[m] for m in months]
    body = f"""
<section class="card">
  <h2>Trend Dashboard — reviews over time</h2>
  <canvas id="tChart" height="110"></canvas>
</section>
<script>
new Chart(document.getElementById('tChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(months)},
    datasets: [{{
      label: 'Reviews',
      data: {json.dumps(counts)},
      borderColor: '#7dd3b0',
      backgroundColor: 'rgba(47,158,122,.25)',
      fill: true,
      tension: .25
    }}]
  }},
  options: {{
    plugins: {{ legend: {{ labels: {{ color: '#e7f2ec' }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#9bb5a8' }}, grid: {{ color: '#2a433a' }} }},
      y: {{ ticks: {{ color: '#9bb5a8' }}, grid: {{ color: '#2a433a' }} }}
    }}
  }}
}});
</script>
"""
    return _shell("Trends", "trends.html", body)


def render_map(pi: PostalIntelligenceDB) -> str:
    points = []
    for b in pi.list_branch_intelligence(limit=2000):
        lat, lng = b.get("latitude"), b.get("longitude")
        if lat is None or lng is None:
            continue
        points.append(
            {
                "name": b["branch_name"],
                "company": b["company_name"],
                "score": b["branch_score"],
                "city": b.get("city"),
                "lat": lat,
                "lng": lng,
            }
        )
    body = f"""
<section class="card">
  <h2>Interactive branch map</h2>
  <p class="muted">{len(points)} branches with coordinates. Marker color scales with branch score.</p>
  <div id="map"></div>
</section>
<script>
const points = {json.dumps(points, ensure_ascii=False)};
const map = L.map('map').setView([32.4, 53.5], 5);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 18, attribution: '&copy; OpenStreetMap'
}}).addTo(map);
function color(score) {{
  if (score >= 70) return '#3ecf8e';
  if (score >= 50) return '#e0b44e';
  return '#e07171';
}}
for (const p of points) {{
  const m = L.circleMarker([p.lat, p.lng], {{
    radius: 6, color: color(p.score), fillColor: color(p.score), fillOpacity: .75, weight: 1
  }}).addTo(map);
  m.bindPopup(`<strong>${{p.company}}</strong><br>${{p.name}}<br>${{p.city || ''}}<br>Score: ${{p.score}}`);
}}
</script>
"""
    return _shell("Interactive Map", "map.html", body)


def render_comparison(pi: PostalIntelligenceDB) -> str:
    comparison = pi.latest_comparison("all_companies") or {"tables": {}}
    tables = comparison.get("tables") or {}

    def table_html(title: str, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return f"<div class='card'><h2>{_esc(title)}</h2><p class='muted'>No data</p></div>"
        cols = list(rows[0].keys())
        head = "".join(f"<th>{_esc(c)}</th>" for c in cols)
        body_rows = []
        for r in rows:
            body_rows.append(
                "<tr>" + "".join(f"<td>{_esc(r.get(c))}</td>" for c in cols) + "</tr>"
            )
        return (
            f"<div class='card' style='margin-bottom:14px'><h2>{_esc(title)}</h2>"
            f"<div style='overflow:auto'><table><tr>{head}</tr>{''.join(body_rows)}</table></div></div>"
        )

    sections = "".join(table_html(name.replace("_", " ").title(), rows) for name, rows in tables.items())
    body = f"<section>{sections}</section>"
    return _shell("Comparison", "comparison.html", body)


def export_all_dashboards(pi: PostalIntelligenceDB, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": render_overview(pi),
        "company_ranking.html": render_company_ranking(pi),
        "branch_ranking.html": render_branch_ranking(pi),
        "province_ranking.html": render_province_ranking(pi),
        "complaints.html": render_complaints(pi),
        "sentiment.html": render_sentiment(pi),
        "trends.html": render_trends(pi),
        "map.html": render_map(pi),
        "comparison.html": render_comparison(pi),
    }
    written = []
    for name, content in pages.items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return written
