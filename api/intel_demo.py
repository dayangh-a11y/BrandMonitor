"""BrandMonitor Postal Intelligence — interactive investor demo routes."""

from __future__ import annotations

import html
import json
from functools import lru_cache

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from api.intel_demo_ui import conf_level, esc, insight_card, shell
from postal.demo_ai import DIM_LABELS, DemoAI
from postal.demo_data import IntelDemoData

router = APIRouter(tags=["intel-demo"])


@lru_cache(maxsize=1)
def _data() -> IntelDemoData:
    d = IntelDemoData()
    d.connect()
    d.snapshot()
    return d


def _ai() -> DemoAI:
    return DemoAI(_data())


@router.get("/intel", response_class=HTMLResponse)
async def intel_home() -> HTMLResponse:
    data = _data()
    snap = data.snapshot()
    companies = snap["companies"]
    totals = snap["totals"]
    insights = _ai().home_insights()
    rows = []
    for c in companies:
        conf = float(c["confidence"]["overall_dataset_confidence"])
        level = conf_level(conf)
        rows.append(
            f"""<tr>
              <td><span class="rank-num">#{c['rank']}</span>
                <a href="/intel/companies/{esc(c['slug'])}">{esc(c['name'])}</a></td>
              <td><span class="score-pill">{c['score']:.2f}</span>
                <div class="bar"><i style="width:{min(100, float(c['score'] or 0))}%"></i></div></td>
              <td>{c['review_count']}</td>
              <td>{c['branch_count']}</td>
              <td>{c['province_count']}</td>
              <td><span class="conf-dot {level}"></span> {conf:.0%}
                <span class="muted">({level})</span></td>
            </tr>"""
        )
    insight_html = "".join(
        insight_card(ins, title=f"Market signal {i}")
        for i, ins in enumerate(insights, 1)
    )
    chart_payload = {
        "labels": [c["name"] for c in companies],
        "scores": [c["score"] for c in companies],
        "confidence": [c["confidence"]["overall_dataset_confidence"] for c in companies],
        "sentiment": snap["trends"]["sentiment_by_month"],
        "map": data.map_points(limit=400),
    }
    leader = companies[0]["name"] if companies else "—"
    leader_score = f"{companies[0]['score']:.2f}/100" if companies else ""
    built = esc(snap["meta"]["built_at"][:19])
    body = f"""
    <section class="hero">
      <div>
        <h1>Postal intelligence for Iran’s logistics market</h1>
        <p class="lead">
          Rank carriers on evidence — scored reviews, official service profiles,
          branch quality, and coverage — not a review browser.
        </p>
      </div>
      <aside class="hero-aside">
        <div class="k">Algorithm</div>
        <div class="v">postal_score_v1</div>
        <p class="muted" style="margin:8px 0 0;font-size:.82rem">
          Snapshot {built}Z · {totals['companies']} carriers
        </p>
      </aside>
    </section>
    <section class="kpis">
      <div class="kpi"><div class="label">Market leader</div>
        <div class="value">{esc(leader)}</div>
        <div class="hint">{esc(leader_score)}</div></div>
      <div class="kpi"><div class="label">Total reviews</div>
        <div class="value">{totals['reviews']:,}</div>
        <div class="hint">Analyzed warehouse corpus</div></div>
      <div class="kpi"><div class="label">Branch coverage</div>
        <div class="value">{totals['branches']:,}</div>
        <div class="hint">Observed mapped locations</div></div>
      <div class="kpi"><div class="label">Avg confidence</div>
        <div class="value">{totals['avg_confidence']:.0%}</div>
        <div class="hint">Dataset evidence grade</div></div>
    </section>
    <section class="grid">
      <div class="panel span-7">
        <h2>Company ranking <span class="muted">postal_score_v1</span></h2>
        <div class="chart-wrap sm"><canvas id="rankChart"></canvas></div>
        <table>
          <thead><tr>
            <th>Company</th><th>Score</th><th>Reviews</th><th>Branches</th>
            <th>Provinces</th><th>Confidence</th>
          </tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <div class="panel span-5">
        <h2>AI Insights <span class="muted">evidence-bound</span></h2>
        {insight_html}
        <p><a class="btn" href="/intel/insights">Open AI Insights →</a></p>
      </div>
      <div class="panel span-6">
        <h2>Sentiment trend <span class="muted">warehouse-wide</span></h2>
        <div class="chart-wrap"><canvas id="sentChart"></canvas></div>
      </div>
      <div class="panel span-6">
        <h2>Confidence by carrier</h2>
        <div class="chart-wrap"><canvas id="confChart"></canvas></div>
      </div>
      <div class="panel span-12">
        <h2>Geographic distribution <span class="muted">branch scores</span></h2>
        <div id="map"></div>
      </div>
    </section>
    """
    scripts = f"""
<script>
const DATA = {json.dumps(chart_payload)};
Chart.defaults.color = '#93b0a2';
Chart.defaults.borderColor = '#2a433a';
new Chart(document.getElementById('rankChart'), {{
  type: 'bar',
  data: {{
    labels: DATA.labels,
    datasets: [{{
      label: 'postal_score_v1',
      data: DATA.scores,
      backgroundColor: '#2f9e7a99',
      borderColor: '#2f9e7a',
      borderWidth: 1,
      borderRadius: 6
    }}]
  }},
  options: {{
    indexAxis: 'y',
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ min: 0, max: 100 }} }},
    animation: {{ duration: 900, easing: 'easeOutQuart' }}
  }}
}});
new Chart(document.getElementById('sentChart'), {{
  type: 'line',
  data: {{
    labels: DATA.sentiment.map(x => x.month),
    datasets: [
      {{ label: 'Positive', data: DATA.sentiment.map(x=>x.Positive), borderColor:'#3ecf8e', tension:.35, fill:false }},
      {{ label: 'Neutral', data: DATA.sentiment.map(x=>x.Neutral), borderColor:'#93b0a2', tension:.35, fill:false }},
      {{ label: 'Negative', data: DATA.sentiment.map(x=>x.Negative), borderColor:'#e07171', tension:.35, fill:false }}
    ]
  }},
  options: {{ plugins: {{ legend: {{ position: 'bottom' }} }}, animation: {{ duration: 1000 }} }}
}});
new Chart(document.getElementById('confChart'), {{
  type: 'radar',
  data: {{
    labels: DATA.labels,
    datasets: [{{
      label: 'Dataset confidence',
      data: DATA.confidence.map(x => +(x*100).toFixed(1)),
      borderColor: '#c4a35a',
      backgroundColor: '#c4a35a33',
      pointBackgroundColor: '#c4a35a'
    }}]
  }},
  options: {{
    scales: {{ r: {{ min: 0, max: 100, ticks: {{ display: false }} }} }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});
const map = L.map('map', {{ scrollWheelZoom: false }}).setView([32.4, 53.5], 5);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; OSM &copy; CARTO', maxZoom: 18
}}).addTo(map);
DATA.map.forEach(p => {{
  const color = p.score >= 70 ? '#3ecf8e' : p.score >= 50 ? '#e0b44e' : '#e07171';
  L.circleMarker([p.lat, p.lng], {{
    radius: 5, color, fillColor: color, fillOpacity: .75, weight: 1
  }}).bindPopup(
    `<strong>${{p.name}}</strong><br>${{p.company}} · score ${{Number(p.score).toFixed(1)}}` +
    `<br><a href="/intel/branches/${{p.id}}">Open branch</a>`
  ).addTo(map);
}});
</script>
"""
    return HTMLResponse(shell("Dashboard", "home", body, scripts=scripts))


@router.get("/intel/companies/{slug}", response_class=HTMLResponse)
async def intel_company(slug: str) -> HTMLResponse:
    data = _data()
    company = data.company_by_slug(slug)
    if not company:
        return HTMLResponse(shell("Not found", "home", "<p>Company not found.</p>"), 404)
    ai = _ai().company_insights(slug)
    trends = data.company_trends(company["id"])
    provinces = data.province_performance(company["id"])
    branches = data.top_branches_for_company(company["id"], limit=15)
    dims = company.get("dimensions") or {}
    dim_rows = []
    for key, label in DIM_LABELS.items():
        d = dims.get(key) or {}
        score = float(d.get("score") or 0)
        w = float((company.get("weights") or {}).get(key) or 0)
        dim_rows.append(
            f"""<div class="dim-row">
              <span>{esc(label)}</span>
              <div class="bar"><i style="width:{score}%"></i></div>
              <strong>{score:.1f}</strong>
            </div>
            <p class="muted" style="margin:0 0 8px 0;font-size:.78rem">
              weight {w:.0%} · {esc(d.get('explanation') or '')}
            </p>"""
        )
    complaints = company.get("complaints") or {}
    prov_rows = "".join(
        f"""<tr>
          <td>{esc(p['geo_name'])}</td>
          <td>{float(p['score'] or 0):.1f}</td>
          <td>{p['review_count']}</td>
          <td>{p['branch_count']}</td>
          <td>{float(p['avg_rating'] or 0):.2f}</td>
        </tr>"""
        for p in provinces[:12]
    ) or '<tr><td colspan="5" class="muted">Insufficient province ranking evidence.</td></tr>'
    branch_rows = "".join(
        f"""<tr>
          <td><a href="/intel/branches/{b['branch_id']}">{esc(b['branch_name'])}</a></td>
          <td>{esc(b.get('city') or '')}</td>
          <td>{float(b.get('branch_score') or 0):.1f}</td>
          <td>{b.get('review_count') or 0}</td>
        </tr>"""
        for b in branches
    ) or '<tr><td colspan="4" class="muted">No branch intelligence rows.</td></tr>'

    strengths = "".join(insight_card(s, title="Strength") for s in ai.get("strengths") or [])
    weaknesses = "".join(insight_card(s, title="Weakness") for s in ai.get("weaknesses") or [])
    summary = insight_card(ai["executive_summary"], title="Executive summary")
    market = insight_card(ai["market_context"], title="Market context")
    conf = company["confidence"]
    payload = {
        "complaints": {"labels": list(complaints.keys()), "values": list(complaints.values())},
        "rating": trends["rating_by_month"],
        "sentiment": trends["sentiment_by_month"],
        "dimensions": {
            "labels": [DIM_LABELS[k] for k in DIM_LABELS],
            "values": [float((dims.get(k) or {}).get("score") or 0) for k in DIM_LABELS],
        },
    }
    body = f"""
    <h1 class="page-title">{esc(company['name'])}</h1>
    <p class="page-sub">
      Rank #{company['rank']} · postal_score_v1 <strong>{company['score']:.2f}</strong>
      · {company['review_count']} reviews · {company['branch_count']} branches
      · confidence {conf_level(float(conf['overall_dataset_confidence']))}
      ({float(conf['overall_dataset_confidence']):.0%})
    </p>
    <section class="kpis">
      <div class="kpi"><div class="label">Overall score</div><div class="value">{company['score']:.2f}</div></div>
      <div class="kpi"><div class="label">Avg rating</div><div class="value">{company['avg_rating']:.2f}</div></div>
      <div class="kpi"><div class="label">Provinces</div><div class="value">{company['province_count']}</div></div>
      <div class="kpi"><div class="label">Negative reviews</div>
        <div class="value">{int((company.get('sentiments') or {}).get('Negative') or 0)}</div></div>
    </section>
    <section class="grid">
      <div class="panel span-7">
        <h2>AI executive summary</h2>
        {summary}{market}
      </div>
      <div class="panel span-5">
        <h2>Score dimensions</h2>
        <div class="chart-wrap sm"><canvas id="dimChart"></canvas></div>
        <div class="dim-list">{''.join(dim_rows)}</div>
      </div>
      <div class="panel span-6"><h2>Strengths</h2>{strengths}</div>
      <div class="panel span-6"><h2>Weaknesses</h2>{weaknesses}</div>
      <div class="panel span-6">
        <h2>Complaint breakdown</h2>
        <div class="chart-wrap"><canvas id="compChart"></canvas></div>
      </div>
      <div class="panel span-6">
        <h2>Rating trend</h2>
        <div class="chart-wrap"><canvas id="rateChart"></canvas></div>
      </div>
      <div class="panel span-6">
        <h2>Sentiment trend</h2>
        <div class="chart-wrap"><canvas id="sentChart"></canvas></div>
      </div>
      <div class="panel span-6">
        <h2>Province performance</h2>
        <table>
          <thead><tr><th>Province</th><th>Score</th><th>Reviews</th><th>Branches</th><th>Avg</th></tr></thead>
          <tbody>{prov_rows}</tbody>
        </table>
      </div>
      <div class="panel span-12">
        <h2>Top branches</h2>
        <table>
          <thead><tr><th>Branch</th><th>City</th><th>Score</th><th>Reviews</th></tr></thead>
          <tbody>{branch_rows}</tbody>
        </table>
      </div>
    </section>
    <p style="margin-top:16px">
      <a class="btn" href="/intel/compare?a={esc(company['slug'])}">Compare this company →</a>
    </p>
    """
    scripts = f"""
<script>
const D = {json.dumps(payload)};
Chart.defaults.color = '#93b0a2';
Chart.defaults.borderColor = '#2a433a';
new Chart(document.getElementById('dimChart'), {{
  type: 'radar',
  data: {{ labels: D.dimensions.labels, datasets: [{{
    data: D.dimensions.values, borderColor:'#2f9e7a', backgroundColor:'#2f9e7a33',
    pointBackgroundColor:'#7dd3b0'
  }}] }},
  options: {{
    scales: {{ r: {{ min:0, max:100, ticks:{{display:false}} }} }},
    plugins:{{legend:{{display:false}}}}, animation:{{duration:900}}
  }}
}});
new Chart(document.getElementById('compChart'), {{
  type: 'doughnut',
  data: {{ labels: D.complaints.labels, datasets: [{{ data: D.complaints.values,
    backgroundColor: ['#e07171','#e0b44e','#2f9e7a','#7dd3b0','#93b0a2','#c4a35a','#5a8f7b'] }}] }},
  options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
}});
new Chart(document.getElementById('rateChart'), {{
  type: 'line',
  data: {{ labels: D.rating.map(x=>x.month), datasets: [{{
    label: 'Avg rating', data: D.rating.map(x=>x.avg_rating),
    borderColor:'#c4a35a', tension:.35, spanGaps:true
  }}] }},
  options: {{ scales: {{ y: {{ min: 0, max: 5 }} }} }}
}});
new Chart(document.getElementById('sentChart'), {{
  type: 'bar',
  data: {{
    labels: D.sentiment.map(x=>x.month),
    datasets: [
      {{ label:'Positive', data:D.sentiment.map(x=>x.Positive), backgroundColor:'#3ecf8e99', stack:'s' }},
      {{ label:'Neutral', data:D.sentiment.map(x=>x.Neutral), backgroundColor:'#93b0a299', stack:'s' }},
      {{ label:'Negative', data:D.sentiment.map(x=>x.Negative), backgroundColor:'#e0717199', stack:'s' }}
    ]
  }},
  options: {{
    scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }},
    plugins: {{ legend: {{ position: 'bottom' }} }}
  }}
}});
</script>
"""
    return HTMLResponse(shell(company["name"], "home", body, scripts=scripts))


@router.get("/intel/branches/{branch_id}", response_class=HTMLResponse)
async def intel_branch(branch_id: int) -> HTMLResponse:
    data = _data()
    branch = data.branch_by_id(branch_id)
    if not branch:
        return HTMLResponse(shell("Not found", "home", "<p>Branch not found.</p>"), 404)
    reviews = data.branch_reviews(branch_id, limit=40)
    insight = _ai().branch_insight(branch)
    complaints = branch.get("complaint_categories") or {}
    sentiment = branch.get("sentiment") or {}
    rev_rows = "".join(
        f"""<tr>
          <td>{esc(r.get('published_at') or r.get('collected_at') or '')}</td>
          <td>{r.get('rating') if r.get('rating') is not None else '—'}</td>
          <td>{esc(r.get('sentiment') or '')}</td>
          <td>{esc(r.get('complaint_category') or '')}</td>
          <td>{esc((r.get('text') or '')[:180])}</td>
        </tr>"""
        for r in reviews
    ) or '<tr><td colspan="5" class="muted">No reviews stored for this branch.</td></tr>'
    payload = {
        "complaints": {"labels": list(complaints.keys()), "values": list(complaints.values())},
        "sentiment": sentiment,
    }
    prov = esc(", " + branch["province"]) if branch.get("province") else ""
    body = f"""
    <h1 class="page-title">{esc(branch.get('branch_name'))}</h1>
    <p class="page-sub">
      <a href="/intel/companies/{esc(branch.get('company_slug'))}">{esc(branch.get('company_name'))}</a>
      · {esc(branch.get('city') or '')}{prov}
      · branch score <strong>{float(branch.get('branch_score') or 0):.1f}</strong>
    </p>
    <section class="kpis">
      <div class="kpi"><div class="label">Branch score</div>
        <div class="value">{float(branch.get('branch_score') or 0):.1f}</div></div>
      <div class="kpi"><div class="label">Reviews</div>
        <div class="value">{branch.get('review_count') or 0}</div></div>
      <div class="kpi"><div class="label">Overall rating</div>
        <div class="value">{branch.get('overall_rating') if branch.get('overall_rating') is not None else '—'}</div></div>
      <div class="kpi"><div class="label">Last activity</div>
        <div class="value" style="font-size:1rem">{esc(str(branch.get('last_activity') or '—')[:16])}</div></div>
    </section>
    <section class="grid">
      <div class="panel span-6">
        <h2>AI branch insight</h2>
        {insight_card(insight, title="Branch narrative")}
        <p class="muted" style="font-size:.82rem">{esc(branch.get('address') or '')}</p>
      </div>
      <div class="panel span-3">
        <h2>Sentiment</h2>
        <div class="chart-wrap sm"><canvas id="sentChart"></canvas></div>
      </div>
      <div class="panel span-3">
        <h2>Complaints</h2>
        <div class="chart-wrap sm"><canvas id="compChart"></canvas></div>
      </div>
      <div class="panel span-12">
        <h2>Recent activity / reviews</h2>
        <table>
          <thead><tr><th>When</th><th>Rating</th><th>Sentiment</th><th>Category</th><th>Text</th></tr></thead>
          <tbody>{rev_rows}</tbody>
        </table>
      </div>
    </section>
    """
    scripts = f"""
<script>
const D = {json.dumps(payload)};
Chart.defaults.color = '#93b0a2';
Chart.defaults.borderColor = '#2a433a';
new Chart(document.getElementById('sentChart'), {{
  type: 'doughnut',
  data: {{
    labels: Object.keys(D.sentiment || {{}}),
    datasets: [{{ data: Object.values(D.sentiment || {{}}),
      backgroundColor: ['#3ecf8e','#93b0a2','#e07171'] }}]
  }},
  options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
}});
new Chart(document.getElementById('compChart'), {{
  type: 'bar',
  data: {{
    labels: D.complaints.labels,
    datasets: [{{ data: D.complaints.values, backgroundColor: '#e0717199' }}]
  }},
  options: {{ plugins: {{ legend: {{ display: false }} }}, indexAxis: 'y' }}
}});
</script>
"""
    return HTMLResponse(shell(str(branch.get("branch_name")), "home", body, scripts=scripts))


@router.get("/intel/insights", response_class=HTMLResponse)
async def intel_insights() -> HTMLResponse:
    data = _data()
    companies = data.snapshot()["companies"]
    home = _ai().home_insights()
    company_blocks = []
    for c in companies:
        summary = _ai().company_executive_summary(c)
        company_blocks.append(
            f"""<div class="panel span-6">
              <h2><a href="/intel/companies/{esc(c['slug'])}">{esc(c['name'])}</a>
                <span class="muted">#{c['rank']} · {c['score']:.2f}</span></h2>
              {insight_card(summary, title="Company summary")}
            </div>"""
        )
    body = f"""
    <h1 class="page-title">AI Insights</h1>
    <p class="page-sub">
      Natural-language summaries generated only from warehouse evidence. Gaps are labeled explicitly.
    </p>
    <section class="grid">
      <div class="panel span-12">
        <h2>Market-level signals</h2>
        {''.join(insight_card(i, title=f"Signal {n}") for n, i in enumerate(home, 1))}
      </div>
      {''.join(company_blocks)}
    </section>
    """
    return HTMLResponse(shell("AI Insights", "insights", body))


@router.get("/intel/compare", response_class=HTMLResponse)
async def intel_compare(a: str = Query(""), b: str = Query("")) -> HTMLResponse:
    data = _data()
    companies = data.snapshot()["companies"]
    result_html = ""
    scripts = ""
    if a and b:
        result = _ai().compare(a, b)
        if result.get("error"):
            result_html = insight_card(result["summary"], title="Compare")
        else:
            deltas = result["dimension_deltas"]
            insights = "".join(
                insight_card(ins, title=f"Compare insight {i}")
                for i, ins in enumerate(result["insights"], 1)
            )
            result_html = f"""
            <div class="grid" style="margin-top:16px">
              <div class="panel span-12">
                <h2>{esc(result['a']['name'])} vs {esc(result['b']['name'])}</h2>
                {insights}
              </div>
              <div class="panel span-12">
                <h2>Dimension deltas</h2>
                <div class="chart-wrap"><canvas id="deltaChart"></canvas></div>
              </div>
            </div>
            """
            scripts = f"""
<script>
const DELTAS = {json.dumps(deltas)};
Chart.defaults.color = '#93b0a2';
Chart.defaults.borderColor = '#2a433a';
new Chart(document.getElementById('deltaChart'), {{
  type: 'bar',
  data: {{
    labels: DELTAS.map(d => d.label),
    datasets: [
      {{ label: {json.dumps(result['a']['name'])}, data: DELTAS.map(d => d.a), backgroundColor: '#2f9e7a99' }},
      {{ label: {json.dumps(result['b']['name'])}, data: DELTAS.map(d => d.b), backgroundColor: '#c4a35a99' }}
    ]
  }},
  options: {{
    scales: {{ y: {{ min: 0, max: 100 }} }},
    plugins: {{ legend: {{ position: 'bottom' }} }},
    animation: {{ duration: 900 }}
  }}
}});
</script>
"""
    default_a = a or (companies[0]["slug"] if companies else "")
    default_b = b or (companies[1]["slug"] if len(companies) > 1 else "")
    opts_a = "".join(
        f'<option value="{esc(c["slug"])}" {"selected" if c["slug"] == default_a else ""}>{esc(c["name"])}</option>'
        for c in companies
    )
    opts_b = "".join(
        f'<option value="{esc(c["slug"])}" {"selected" if c["slug"] == default_b else ""}>{esc(c["name"])}</option>'
        for c in companies
    )
    body = f"""
    <h1 class="page-title">AI Compare</h1>
    <p class="page-sub">Compare any two carriers using postal_score_v1 dimensions and coverage evidence.</p>
    <form class="inline panel" method="get" action="/intel/compare" style="padding:16px">
      <label class="field">Company A<select name="a">{opts_a}</select></label>
      <label class="field">Company B<select name="b">{opts_b}</select></label>
      <button class="btn primary" type="submit">Compare with AI</button>
    </form>
    {result_html}
    """
    return HTMLResponse(shell("AI Compare", "compare", body, scripts=scripts))


@router.get("/intel/search", response_class=HTMLResponse)
async def intel_search(q: str = Query("")) -> HTMLResponse:
    answer_html = ""
    suggestions = [
        "Which company has the best customer satisfaction?",
        "Why is Tipax ranked higher than Chapar?",
        "Which provinces have the highest complaint rate?",
        "Who leads the postal_score_v1 ranking?",
        "Which company has the widest branch coverage?",
    ]
    if q.strip():
        result = _ai().search(q)
        answer_html = insight_card(
            result["answer"], title=f"Answer · {result.get('intent') or 'query'}"
        )
        if result.get("suggestions"):
            suggestions = result["suggestions"]
    chips = "".join(
        f'<a class="chip" href="/intel/search?q={html.escape(s, quote=True)}">{esc(s)}</a>'
        for s in suggestions
    )
    body = f"""
    <h1 class="page-title">AI Search</h1>
    <p class="page-sub">Ask natural-language questions. Answers cite warehouse evidence or state insufficiency.</p>
    <form class="inline panel" method="get" action="/intel/search" style="padding:16px;margin-bottom:14px">
      <label class="field" style="flex:3">Question
        <input type="text" name="q" value="{esc(q)}"
          placeholder="e.g. Why is Tipax ranked higher than Chapar?"/>
      </label>
      <button class="btn primary" type="submit">Ask</button>
    </form>
    <div class="chips">{chips}</div>
    {answer_html}
    """
    return HTMLResponse(shell("AI Search", "search", body))


@router.get("/intel/api/snapshot")
async def intel_api_snapshot() -> JSONResponse:
    return JSONResponse(_data().snapshot())


@router.get("/intel/api/search")
async def intel_api_search(q: str = Query("")) -> JSONResponse:
    return JSONResponse(_ai().search(q))


@router.get("/intel/api/compare")
async def intel_api_compare(a: str = Query(...), b: str = Query(...)) -> JSONResponse:
    return JSONResponse(_ai().compare(a, b))
