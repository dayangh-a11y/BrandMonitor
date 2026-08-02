#!/usr/bin/env python3
"""Generate AI metrics dashboard (HTML + JSON) without touching API/UI."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ai.metrics_ai import AI_METRICS


def render_html(snapshot: dict) -> str:
    conf = snapshot.get("confidence_distribution") or {}
    conf_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in sorted(conf.items())
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>BrandMonitor AI Metrics</title>
<style>
body {{ font-family: "IBM Plex Sans", sans-serif; background:#0f1419; color:#e7ecf3; padding:24px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }}
.card {{ background:#1a2332; border:1px solid #2a3a52; border-radius:10px; padding:14px; }}
.label {{ color:#9aa8bc; font-size:.8rem; }} .value {{ font-size:1.4rem; font-weight:600; margin-top:6px; }}
table {{ width:100%; border-collapse:collapse; margin-top:16px; }} th,td {{ padding:8px; border-bottom:1px solid #2a3a52; text-align:left; }}
</style></head><body>
<h1>AI Metrics Dashboard</h1>
<p>Generated {datetime.now(timezone.utc).isoformat()} (in-process snapshot)</p>
<div class="grid">
  <div class="card"><div class="label">Requests / day (today)</div><div class="value">{snapshot.get('requests_today',0)}</div></div>
  <div class="card"><div class="label">Cost / day (USD)</div><div class="value">{snapshot.get('cost_today_usd',0)}</div></div>
  <div class="card"><div class="label">Average latency (ms)</div><div class="value">{snapshot.get('average_latency_ms',0)}</div></div>
  <div class="card"><div class="label">Success rate</div><div class="value">{snapshot.get('success_rate',0)}</div></div>
  <div class="card"><div class="label">Retry rate</div><div class="value">{snapshot.get('retry_rate',0)}</div></div>
  <div class="card"><div class="label">Cache hits</div><div class="value">{snapshot.get('cache_hits',0)}</div></div>
</div>
<h2>Confidence distribution</h2>
<table><thead><tr><th>Bucket</th><th>Count</th></tr></thead><tbody>{conf_rows or '<tr><td colspan=2>None yet</td></tr>'}</tbody></table>
<pre>{json.dumps(snapshot, indent=2)}</pre>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="output/ai_metrics")
    parser.add_argument("--from-json", default=None, help="Optional metrics JSON to render")
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if args.from_json:
        raw = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        snapshot = raw.get("ai_metrics_snapshot") or raw
    else:
        snapshot = AI_METRICS.snapshot()
    (out / "metrics.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    (out / "dashboard.html").write_text(render_html(snapshot), encoding="utf-8")
    print(json.dumps({"wrote": str(out), "snapshot": snapshot}, indent=2))


if __name__ == "__main__":
    main()
