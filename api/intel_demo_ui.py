"""Shared shell / CSS helpers for the Postal Intelligence interactive demo."""

from __future__ import annotations

import html
from typing import Any


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


CSS = r"""
:root {
  --bg: #0b1411;
  --panel: rgba(18, 32, 27, 0.88);
  --line: #2a433a;
  --text: #e8f3ed;
  --muted: #93b0a2;
  --accent: #2f9e7a;
  --accent2: #c4a35a;
  --good: #3ecf8e;
  --warn: #e0b44e;
  --bad: #e07171;
  --serif: "Fraunces", Georgia, serif;
  --sans: "IBM Plex Sans", "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; color: var(--text); font-family: var(--sans);
  background:
    radial-gradient(900px 480px at 8% -10%, #1a3d32 0%, transparent 55%),
    radial-gradient(700px 420px at 100% 0%, #2a3218 0%, transparent 48%),
    linear-gradient(180deg, #08110e, var(--bg));
  min-height: 100vh;
}
a { color: #7dd3b0; text-decoration: none; }
a:hover { color: #b7f0d6; }
.shell { max-width: 1180px; margin: 0 auto; padding: 0 22px 56px; }
.topbar {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: 14px; padding: 22px 0 10px; animation: fadeDown .7s ease both;
}
.brand-block { display: flex; flex-direction: column; gap: 2px; }
.brand {
  font-family: var(--serif); font-size: clamp(1.7rem, 3.2vw, 2.35rem);
  margin: 0; letter-spacing: -0.03em; line-height: 1.05;
}
.brand span { color: var(--accent2); font-weight: 600; }
.tagline { color: var(--muted); font-size: .92rem; }
nav.main { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; }
nav.main a {
  color: var(--muted); font-size: .9rem; padding: 6px 0;
  border-bottom: 2px solid transparent; transition: color .2s, border-color .2s;
}
nav.main a:hover, nav.main a.active { color: var(--text); border-color: var(--accent); }
.hero {
  padding: 34px 0 18px;
  display: grid; grid-template-columns: 1.3fr .7fr; gap: 24px; align-items: end;
  animation: rise .8s ease .05s both;
}
@media (max-width: 860px) { .hero { grid-template-columns: 1fr; } }
.hero h1 {
  font-family: var(--serif); font-size: clamp(1.8rem, 4vw, 2.8rem);
  margin: 0 0 10px; letter-spacing: -0.03em; line-height: 1.1;
}
.hero p.lead { margin: 0; color: var(--muted); max-width: 46ch; font-size: 1.02rem; }
.hero-aside {
  background: linear-gradient(145deg, rgba(47,158,122,.18), rgba(196,163,90,.08));
  border: 1px solid var(--line); border-radius: 16px; padding: 16px 18px;
}
.hero-aside .k { color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .06em; }
.hero-aside .v { font-family: var(--serif); font-size: 1.8rem; margin-top: 4px; }
.kpis {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 8px 0 22px;
  animation: rise .8s ease .12s both;
}
@media (max-width: 860px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
.kpi {
  background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px;
  transition: transform .25s ease, border-color .25s;
}
.kpi:hover { transform: translateY(-2px); border-color: #3d5f52; }
.kpi .label { color: var(--muted); font-size: .74rem; text-transform: uppercase; letter-spacing: .05em; }
.kpi .value { font-family: var(--serif); font-size: 1.75rem; margin-top: 6px; }
.kpi .hint { color: var(--muted); font-size: .78rem; margin-top: 4px; }
.grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
.panel {
  background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 16px 18px;
  animation: rise .7s ease both;
}
.panel h2 {
  margin: 0 0 12px; font-size: .95rem; font-weight: 600; letter-spacing: .01em;
  display: flex; justify-content: space-between; align-items: baseline; gap: 8px;
}
.panel h2 .muted { font-weight: 400; font-size: .78rem; color: var(--muted); }
.span-12 { grid-column: span 12; }
.span-8 { grid-column: span 8; }
.span-7 { grid-column: span 7; }
.span-6 { grid-column: span 6; }
.span-5 { grid-column: span 5; }
.span-4 { grid-column: span 4; }
.span-3 { grid-column: span 3; }
@media (max-width: 900px) {
  .span-8, .span-7, .span-6, .span-5, .span-4, .span-3 { grid-column: span 12; }
}
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
th, td { padding: 9px 6px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
th { color: var(--muted); font-weight: 500; font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; }
tr:hover td { background: rgba(47,158,122,.06); }
.score-pill { display: inline-flex; align-items: center; gap: 6px; font-family: var(--serif); font-size: 1.05rem; }
.bar { height: 7px; border-radius: 99px; background: #24352e; overflow: hidden; min-width: 64px; }
.bar > i { display:block; height:100%; background: linear-gradient(90deg, #2f9e7a, #7dd3b0); }
.conf-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.conf-dot.high { background: var(--good); }
.conf-dot.medium { background: var(--warn); }
.conf-dot.low { background: var(--bad); }
.insight {
  border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; margin: 0 0 12px;
  background: rgba(12,22,18,.55);
}
.insight[data-level="insufficient"] { border-color: #5a4a2a; }
.insight-head { display: flex; justify-content: space-between; gap: 10px; align-items: center; margin-bottom: 8px; }
.insight-title { font-size: .78rem; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.conf-badge {
  font-size: .72rem; padding: 3px 8px; border-radius: 6px; border: 1px solid var(--line);
  text-transform: uppercase; letter-spacing: .04em;
}
.conf-badge.high { color: var(--good); border-color: #2f6b4f; }
.conf-badge.medium { color: var(--warn); border-color: #6b5a2f; }
.conf-badge.low, .conf-badge.insufficient { color: var(--bad); border-color: #6b3a3a; }
.insight-text { margin: 0 0 10px; line-height: 1.55; font-size: .95rem; }
.insight-meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0; font-size: .78rem; }
@media (max-width: 700px) { .insight-meta { grid-template-columns: 1fr; } }
.insight-meta dt { color: var(--muted); margin: 0; }
.insight-meta dd { margin: 2px 0 0; }
.evidence { margin-top: 8px; font-size: .8rem; color: var(--muted); }
.evidence ul { margin: 6px 0 0; padding-left: 18px; }
.chart-wrap { position: relative; height: 280px; }
.chart-wrap.sm { height: 220px; }
#map { height: 380px; border-radius: 12px; border: 1px solid var(--line); }
.muted { color: var(--muted); }
.btn, button.btn {
  appearance: none; border: 1px solid #3d5f52; background: linear-gradient(180deg, #1d3b32, #162820);
  color: var(--text); padding: 10px 16px; border-radius: 10px; cursor: pointer; font: inherit;
  transition: transform .15s, border-color .15s;
}
.btn:hover, button.btn:hover { border-color: var(--accent); transform: translateY(-1px); }
.btn.primary {
  background: linear-gradient(180deg, #2f9e7a, #217a5d); border-color: #3eb890;
  color: #04140f; font-weight: 600;
}
form.inline { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
label.field {
  display: flex; flex-direction: column; gap: 6px; font-size: .78rem; color: var(--muted);
  min-width: 160px; flex: 1;
}
input[type=text], select, textarea {
  background: #0e1a15; border: 1px solid var(--line); color: var(--text);
  border-radius: 10px; padding: 10px 12px; font: inherit; width: 100%;
}
.dim-list { display: grid; gap: 8px; }
.dim-row { display: grid; grid-template-columns: 140px 1fr 48px; gap: 10px; align-items: center; font-size: .85rem; }
.page-title {
  font-family: var(--serif); font-size: clamp(1.6rem, 3vw, 2.2rem); margin: 22px 0 6px;
  letter-spacing: -0.02em; animation: rise .6s ease both;
}
.page-sub { color: var(--muted); margin: 0 0 18px; animation: rise .6s ease .05s both; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
.chip {
  border: 1px solid var(--line); border-radius: 999px; padding: 6px 12px; font-size: .8rem;
  color: var(--muted); background: rgba(0,0,0,.15);
}
.chip:hover { color: var(--text); border-color: var(--accent); }
.footer-note {
  margin-top: 28px; padding-top: 16px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: .78rem; line-height: 1.5;
}
.rank-num { font-family: var(--serif); color: var(--accent2); width: 28px; display: inline-block; }
@keyframes fadeDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: none; } }
@keyframes rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
"""


def insight_card(insight: dict[str, Any], *, title: str = "AI Insight") -> str:
    level = insight.get("confidence_level") or "low"
    insufficient = bool(insight.get("insufficient_evidence"))
    badge = "insufficient" if insufficient else level
    sources = ", ".join(insight.get("data_sources") or []) or "—"
    evidence = insight.get("evidence") or []
    evid_html = ""
    if evidence:
        items = "".join(f"<li>{esc(e)}</li>" for e in evidence[:8])
        evid_html = (
            f'<details class="evidence"><summary>Evidence</summary><ul>{items}</ul></details>'
        )
    return f"""
    <article class="insight" data-level="{esc(badge)}">
      <header class="insight-head">
        <span class="insight-title">{esc(title)}</span>
        <span class="conf-badge {esc(badge)}">{esc(badge)} confidence</span>
      </header>
      <p class="insight-text">{esc(insight.get("text") or "")}</p>
      <dl class="insight-meta">
        <div><dt>Data sources</dt><dd>{esc(sources)}</dd></div>
        <div><dt>Confidence</dt><dd>{esc(level)} ({float(insight.get("confidence_score") or 0):.0%})</dd></div>
        <div><dt>Last update</dt><dd>{esc(insight.get("last_updated") or "—")}</dd></div>
      </dl>
      {evid_html}
    </article>
    """


def shell(title: str, active: str, body: str, scripts: str = "") -> str:
    nav = [
        ("/intel", "Dashboard", "home"),
        ("/intel/insights", "AI Insights", "insights"),
        ("/intel/compare", "AI Compare", "compare"),
        ("/intel/search", "AI Search", "search"),
    ]
    links = " ".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for href, label, key in nav
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc(title)} · BrandMonitor Postal Intelligence</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,550;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet"/>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>{CSS}</style>
</head>
<body>
<div class="shell">
  <header class="topbar">
    <div class="brand-block">
      <p class="brand">Brand<span>Monitor</span></p>
      <span class="tagline">AI-powered postal intelligence</span>
    </div>
    <nav class="main">{links}</nav>
  </header>
  {body}
  <p class="footer-note">
    Demo snapshot from the Postal Intelligence warehouse. Scores use algorithm
    <code>postal_score_v1</code>. AI narratives are deterministic summaries of stored
    evidence only — they never invent facts. Confidence labels reflect dataset
    coverage, not model certainty about the physical world.
  </p>
</div>
{scripts}
</body>
</html>"""


def conf_level(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"
