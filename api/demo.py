from __future__ import annotations

from html import escape
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from api.deps import get_db
from core.db import Database

router = APIRouter(tags=["demo"])


def _layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)} · BrandMonitor Demo</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f6f7f9; color: #222; }}
    header {{ background: #111; color: #fff; padding: 12px 16px; }}
    header a {{ color: #fff; text-decoration: none; margin-right: 12px; }}
    main {{ max-width: 920px; margin: 20px auto; padding: 0 16px 40px; }}
    .card {{ background: #fff; border: 1px solid #ddd; padding: 14px; margin: 12px 0; }}
    .muted {{ color: #666; }}
    .score {{ font-size: 32px; font-weight: bold; }}
    .row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .pill {{ display: inline-block; background: #eee; padding: 4px 8px; margin: 2px; border-radius: 4px; font-size: 13px; }}
    .pill.bad {{ background: #fde2e1; }}
    .pill.good {{ background: #e3f6e8; }}
    input[type=text] {{ width: min(420px, 100%); padding: 8px; }}
    button, .btn {{ padding: 8px 12px; background: #111; color: #fff; border: 0; text-decoration: none; display: inline-block; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td, th {{ border-top: 1px solid #eee; padding: 8px; text-align: left; vertical-align: top; }}
    .sentiment-Negative {{ color: #b00020; font-weight: bold; }}
    .sentiment-Positive {{ color: #0b7a33; font-weight: bold; }}
  </style>
</head>
<body>
  <header>
    <a href="/demo">BrandMonitor Demo</a>
    <a href="/docs">API Docs</a>
  </header>
  <main>
    <h1>{escape(title)}</h1>
    {body}
  </main>
</body>
</html>"""


def _pills(items: list[str], kind: str = "") -> str:
    if not items:
        return '<span class="muted">None</span>'
    cls = f"pill {kind}".strip()
    return " ".join(f'<span class="{cls}">{escape(item)}</span>' for item in items)


@router.get("/demo", response_class=HTMLResponse)
async def demo_home(
    q: str = Query(""),
    db: Database = Depends(get_db),
) -> HTMLResponse:
    results = ""
    if q.strip():
        data = await db.search(q.strip(), limit=20, sort="highest_score")
        company_rows = "".join(
            f"""<tr>
              <td><a href="/demo/companies/{c['id']}">{escape(c['name'])}</a></td>
              <td>{c.get('branch_count') or 0}</td>
              <td>{c.get('latest_score') if c.get('latest_score') is not None else '—'}</td>
            </tr>"""
            for c in data["companies"]
        ) or '<tr><td colspan="3" class="muted">No companies</td></tr>'
        branch_rows = "".join(
            f"""<tr>
              <td><a href="/demo/branches/{b['id']}">{escape(b['name'])}</a></td>
              <td>{escape(b.get('company_name') or '')}</td>
              <td>{escape(b.get('address') or '')}</td>
              <td>{b.get('latest_score') if b.get('latest_score') is not None else '—'}</td>
            </tr>"""
            for b in data["branches"]
        ) or '<tr><td colspan="4" class="muted">No branches</td></tr>'
        results = f"""
        <div class="card">
          <h2>Companies</h2>
          <table>
            <tr><th>Name</th><th>Branches</th><th>Score</th></tr>
            {company_rows}
          </table>
        </div>
        <div class="card">
          <h2>Branches</h2>
          <table>
            <tr><th>Branch</th><th>Company</th><th>Address</th><th>Score</th></tr>
            {branch_rows}
          </table>
        </div>
        """
    else:
        companies = await db.list_companies(sort="highest_score", limit=10)
        rows = "".join(
            f"""<tr>
              <td><a href="/demo/companies/{c['id']}">{escape(c['name'])}</a></td>
              <td>{c.get('branch_count') or 0}</td>
              <td>{c.get('latest_score') if c.get('latest_score') is not None else '—'}</td>
            </tr>"""
            for c in companies
        ) or '<tr><td colspan="3" class="muted">No data yet. Run scripts/seed_demo_data.py</td></tr>'
        results = f"""
        <div class="card">
          <h2>Top companies</h2>
          <table>
            <tr><th>Name</th><th>Branches</th><th>Score</th></tr>
            {rows}
          </table>
        </div>
        """

    body = f"""
    <div class="card">
      <p class="muted">Vertical-slice demo: search → company → branch → reviews/analysis/score explanation.</p>
      <form method="get" action="/demo">
        <input type="text" name="q" value="{escape(q)}" placeholder="Search courier (e.g. Tipax)" />
        <button type="submit">Search</button>
      </form>
    </div>
    {results}
    """
    return HTMLResponse(_layout("Search", body))


@router.get("/demo/companies/{company_id}", response_class=HTMLResponse)
async def demo_company(company_id: int, db: Database = Depends(get_db)) -> HTMLResponse:
    company = await db.get_company(company_id)
    if company is None:
        return HTMLResponse(_layout("Not found", "<p>Company not found.</p>"), status_code=404)

    score = await db.get_company_score(company_id)
    insights = await db.get_company_insights(company_id)
    branches = await db.list_company_branches(company_id, sort="highest_score", limit=50)

    score_html = (
        f'<div class="score">{score["score"]:.1f}/100</div>'
        if score
        else '<div class="muted">No score yet</div>'
    )
    summary = escape((insights or {}).get("summary") or "No AI summary yet.")
    pros = _pills((insights or {}).get("pros") or [], "good")
    cons = _pills((insights or {}).get("cons") or [], "bad")
    why = ""
    if score and isinstance(score.get("components"), dict):
        reasons = score["components"].get("why") or []
        if reasons:
            why = "<ul>" + "".join(f"<li>{escape(str(r))}</li>" for r in reasons) + "</ul>"

    branch_rows = "".join(
        f"""<tr>
          <td><a href="/demo/branches/{b['id']}">{escape(b['name'])}</a></td>
          <td>{escape(b.get('address') or '')}</td>
          <td>{b.get('review_count') or 0}</td>
          <td>{b.get('latest_score') if b.get('latest_score') is not None else '—'}</td>
        </tr>"""
        for b in branches
    )

    body = f"""
    <div class="card">
      <p class="muted"><a href="/demo?q={quote_plus(company['name'])}">← Back to search</a></p>
      <h2>{escape(company['name'])}</h2>
      {score_html}
      <p>Branches: <strong>{company.get('branch_count') or 0}</strong> ·
         Reviews: <strong>{company.get('review_count') or 0}</strong></p>
    </div>
    <div class="card">
      <h3>AI summary</h3>
      <p>{summary}</p>
      <h4>Top positive categories</h4>
      {pros}
      <h4>Top complaint categories</h4>
      {cons}
      {"<h4>Score explanation</h4>" + why if why else ""}
    </div>
    <div class="card">
      <h3>Branches</h3>
      <table>
        <tr><th>Branch</th><th>Address</th><th>Reviews</th><th>Score</th></tr>
        {branch_rows}
      </table>
    </div>
    """
    return HTMLResponse(_layout(company["name"], body))


@router.get("/demo/branches/{branch_id}", response_class=HTMLResponse)
async def demo_branch(branch_id: int, db: Database = Depends(get_db)) -> HTMLResponse:
    branch = await db.get_branch(branch_id)
    if branch is None:
        return HTMLResponse(_layout("Not found", "<p>Branch not found.</p>"), status_code=404)

    score = await db.get_branch_score(branch_id)
    insights = await db.get_branch_insights(branch_id)
    reviews, total = await db.list_branch_reviews(branch_id, limit=20, offset=0, sort="newest")

    score_html = (
        f'<div class="score">{score["score"]:.1f}/100</div>'
        if score
        else '<div class="muted">No score yet</div>'
    )
    summary = escape((insights or {}).get("summary") or "No AI summary yet.")
    pros = _pills((insights or {}).get("pros") or [], "good")
    cons = _pills((insights or {}).get("cons") or [], "bad")

    explanation = ""
    if score and isinstance(score.get("components"), dict):
        comp = score["components"]
        why = comp.get("why") or []
        parts = []
        if "sentiment_score" in comp:
            parts.append(f"Sentiment component: {comp['sentiment_score']}")
        if "complaint_penalty" in comp:
            parts.append(f"Complaint penalty: {comp['complaint_penalty']}")
        if "positive_reward" in comp:
            parts.append(f"Positive reward: {comp['positive_reward']}")
        if "kappa" in comp:
            parts.append(f"Volume confidence (kappa): {comp['kappa']}")
        bullets = "".join(f"<li>{escape(str(x))}</li>" for x in why)
        explanation = f"""
        <h4>Score explanation</h4>
        <p class="muted">{escape(' · '.join(str(p) for p in parts))}</p>
        <ul>{bullets}</ul>
        """

    review_cards = []
    for review in reviews:
        sentiment = review.get("sentiment") or "—"
        cats = _pills(review.get("complaint_categories") or [], "bad")
        pos = _pills(review.get("positive_categories") or [], "good")
        review_cards.append(
            f"""
            <div class="card">
              <div><strong>{escape(review.get('author') or 'Anonymous')}</strong>
                · rating {review.get('rating')}
                · <span class="sentiment-{escape(str(sentiment))}">{escape(str(sentiment))}</span>
              </div>
              <p>{escape(review.get('text') or '')}</p>
              <div class="muted">City: {escape(review.get('mentioned_city') or '—')}</div>
              <div>Complaints: {cats}</div>
              <div>Positives: {pos}</div>
            </div>
            """
        )

    body = f"""
    <div class="card">
      <p class="muted"><a href="/demo/companies/{branch['company_id']}">← Back to company</a></p>
      <h2>{escape(branch['name'])}</h2>
      <p class="muted">{escape(branch.get('company_name') or '')} · {escape(branch.get('address') or '')}</p>
      {score_html}
      <p>Review count: <strong>{total}</strong></p>
    </div>
    <div class="card">
      <h3>AI summary</h3>
      <p>{summary}</p>
      <h4>Top positives</h4>{pros}
      <h4>Top complaints</h4>{cons}
      {explanation}
    </div>
    <h3>Recent reviews + AI analysis</h3>
    {''.join(review_cards) or '<p class="muted">No reviews</p>'}
    """
    return HTMLResponse(_layout(branch["name"], body))
