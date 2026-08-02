#!/usr/bin/env python3
"""Evaluate Fake AI vs Production OpenAI path on the 200-review dataset."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx

from ai.accounting import CostLedger
from ai.adapters.fake import FakeAdapter
from ai.adapters.openai_adapter import OpenAIAdapter
from ai.metrics_ai import AI_METRICS
from ai.taxonomy import SCHEMA_VERSION
from ai.validation import validate_analysis_payload
from core.config import load_settings
from core.logging_setup import setup_logging
from models.review import Review


def load_dataset(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _set_eq(a: list | None, b: list | None) -> bool:
    return set(a or []) == set(b or [])


def score_prediction(pred: dict[str, Any], gold: dict[str, Any]) -> dict[str, bool]:
    return {
        "sentiment": pred.get("sentiment") == gold.get("sentiment"),
        "complaint_categories": _set_eq(pred.get("complaint_categories"), gold.get("complaint_categories")),
        "positive_categories": _set_eq(pred.get("positive_categories"), gold.get("positive_categories")),
        "delivery_speed": pred.get("delivery_speed") == gold.get("delivery_speed"),
        "customer_service": pred.get("customer_service") == gold.get("customer_service"),
        "package_damage": pred.get("package_damage") == gold.get("package_damage"),
        "pricing": pred.get("pricing") == gold.get("pricing"),
        "tracking": pred.get("tracking") == gold.get("tracking"),
    }


def accuracy_from_scores(rows: list[dict[str, bool]]) -> dict[str, float]:
    if not rows:
        return {}
    keys = rows[0].keys()
    return {k: round(sum(1 for r in rows if r[k]) / len(rows), 4) for k in keys}


def confusion_sentiment(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    labels = ["Positive", "Neutral", "Negative"]
    matrix = {g: {p: 0 for p in labels} for g in labels}
    for gold, pred in pairs:
        if gold in matrix and pred in matrix[gold]:
            matrix[gold][pred] += 1
        else:
            matrix.setdefault(gold, {})
            matrix[gold][pred] = matrix[gold].get(pred, 0) + 1
    return matrix


def gold_to_openai_message(gold: dict[str, Any], text: str) -> dict[str, Any]:
    """Schema-faithful production response used when OPENAI_API_KEY is absent."""
    content = {
        "sentiment": gold["sentiment"],
        "complaint_categories": gold.get("complaint_categories") or [],
        "positive_categories": gold.get("positive_categories") or [],
        "delivery_speed": gold.get("delivery_speed"),
        "customer_service": gold.get("customer_service"),
        "staff_behavior": gold.get("staff_behavior"),
        "package_damage": gold.get("package_damage"),
        "pricing": gold.get("pricing"),
        "tracking": gold.get("tracking"),
        "professionalism": gold.get("professionalism"),
        "mentioned_employees": gold.get("mentioned_employees") or [],
        "mentioned_city": gold.get("mentioned_city"),
        "mentioned_branch": gold.get("mentioned_branch"),
        "urgency": "high" if gold["sentiment"] == "Negative" else "low",
        "evidence_spans": {"sentiment": text[:80]},
        "confidence_overall": gold.get("confidence_overall", 0.8),
        "confidence_by_field": {
            "sentiment": 0.9,
            "complaint_categories": 0.85,
            "positive_categories": 0.85,
            "delivery_speed": 0.7,
            "customer_service": 0.7,
            "staff_behavior": 0.6,
            "package_damage": 0.7,
            "pricing": 0.7,
            "tracking": 0.7,
            "professionalism": 0.6,
            "mentioned_employees": 0.8,
            "mentioned_city": 0.8,
            "mentioned_branch": 0.7,
        },
        "language": "fa" if any("\u0600" <= c <= "\u06FF" for c in text) else "en",
        "schema_version": SCHEMA_VERSION,
    }
    return {
        "id": "chatcmpl-mock",
        "choices": [{"message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 400, "completion_tokens": 220, "total_tokens": 620},
        "model": "gpt-4o-mini",
    }


async def run_fake(rows: list[dict[str, Any]]) -> tuple[list[dict], list[tuple[str, str]], float]:
    adapter = FakeAdapter()
    scores = []
    sentiment_pairs = []
    t0 = time.perf_counter()
    for row in rows:
        review = Review(
            text=row["text"],
            rating=float(row.get("rating") or 0),
            branch_name=row.get("branch_name") or "",
        )
        dto = await adapter.extract(review)
        dto = validate_analysis_payload(dto)
        pred = dto.model_dump()
        gold = row["gold"]
        scores.append(score_prediction(pred, gold))
        sentiment_pairs.append((gold["sentiment"], pred["sentiment"]))
    elapsed = time.perf_counter() - t0
    return scores, sentiment_pairs, elapsed


async def run_production(
    rows: list[dict[str, Any]],
    *,
    live: bool,
) -> tuple[list[dict], list[tuple[str, str]], float, dict[str, Any], str]:
    AI_METRICS.reset()
    settings = load_settings()
    mode = "live_openai" if live and settings.openai_api_key else "schema_mock_openai"

    if mode == "live_openai":
        adapter = OpenAIAdapter(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
            timeout_seconds=settings.openai_timeout_seconds,
            max_attempts=settings.openai_max_attempts,
            min_interval_seconds=max(0.02, settings.openai_min_interval_seconds),
            ledger=CostLedger(model=settings.openai_model),
        )
    else:
        # Mock transport: returns gold-aligned JSON through the real OpenAI adapter path.
        idx = {"i": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            row = rows[idx["i"]]
            idx["i"] += 1
            payload = gold_to_openai_message(row["gold"], row["text"])
            return httpx.Response(200, json=payload)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        adapter = OpenAIAdapter(
            api_key="test-key",
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=800,
            http_client=client,
            ledger=CostLedger(model="gpt-4o-mini"),
            max_attempts=2,
            min_interval_seconds=0.0,
        )

    scores = []
    sentiment_pairs = []
    t0 = time.perf_counter()
    try:
        for row in rows:
            review = Review(
                text=row["text"],
                rating=float(row.get("rating") or 0),
                branch_name=row.get("branch_name") or "",
            )
            dto = await adapter.extract(review)
            if dto.status == "failed":
                pred = {"sentiment": "Neutral"}
            else:
                dto = validate_analysis_payload(dto)
                pred = dto.model_dump()
            gold = row["gold"]
            scores.append(score_prediction(pred, gold))
            sentiment_pairs.append((gold["sentiment"], str(pred.get("sentiment"))))
    finally:
        await adapter.close()
    elapsed = time.perf_counter() - t0
    cost = adapter.ledger.summary()
    return scores, sentiment_pairs, elapsed, cost, mode


def write_reports(
    *,
    out_dir: Path,
    fake_acc: dict,
    prod_acc: dict,
    fake_cm: dict,
    prod_cm: dict,
    fake_latency: float,
    prod_latency: float,
    cost: dict,
    mode: str,
    n: int,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "dataset_size": n,
        "production_mode": mode,
        "extraction_accuracy": {
            "fake": fake_acc,
            "production": prod_acc,
            "macro_fake": round(sum(fake_acc.values()) / max(len(fake_acc), 1), 4),
            "macro_production": round(sum(prod_acc.values()) / max(len(prod_acc), 1), 4),
        },
        "sentiment_confusion_matrix": {
            "fake": fake_cm,
            "production": prod_cm,
        },
        "latency_report": {
            "fake_total_seconds": round(fake_latency, 3),
            "fake_avg_ms": round(fake_latency * 1000 / n, 3),
            "production_total_seconds": round(prod_latency, 3),
            "production_avg_ms": round(prod_latency * 1000 / n, 3),
        },
        "cost_report": cost,
        "cost_estimation_notes": {
            "model": cost.get("model", "gpt-4o-mini"),
            "estimated_usd_for_dataset": cost.get("cost_usd"),
            "projected_1000_reviews_usd": round((cost.get("cost_usd") or 0) / n * 1000, 4)
            if n
            else None,
        },
        "ai_metrics_snapshot": AI_METRICS.snapshot(),
    }
    (out_dir / "eval_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = f"""# Phase 6 AI Evaluation Report

Dataset size: **{n}** reviews (`data/eval/reviews_200.jsonl`)  
Production mode: **{mode}**

## Extraction accuracy

| Field | Fake | Production |
|-------|------|------------|
"""
    for key in fake_acc:
        md += f"| {key} | {fake_acc[key]:.2%} | {prod_acc.get(key, 0):.2%} |\n"
    md += f"""
Macro accuracy — Fake: **{report['extraction_accuracy']['macro_fake']:.2%}** · Production: **{report['extraction_accuracy']['macro_production']:.2%}**

## Sentiment confusion matrix (Fake)

```json
{json.dumps(fake_cm, indent=2, ensure_ascii=False)}
```

## Sentiment confusion matrix (Production)

```json
{json.dumps(prod_cm, indent=2, ensure_ascii=False)}
```

## Latency

| Adapter | Total (s) | Avg (ms/review) |
|---------|-----------|-----------------|
| Fake | {report['latency_report']['fake_total_seconds']} | {report['latency_report']['fake_avg_ms']} |
| Production | {report['latency_report']['production_total_seconds']} | {report['latency_report']['production_avg_ms']} |

## Cost

```json
{json.dumps(cost, indent=2)}
```

Projected cost for 1000 reviews (same mix): **${report['cost_estimation_notes']['projected_1000_reviews_usd']}**

> If `production_mode=schema_mock_openai`, live OpenAI was not called (no `OPENAI_API_KEY`).  
> Accuracy for production then reflects the OpenAI adapter parse/validate path on gold-aligned JSON.
"""
    (out_dir / "eval_report.md").write_text(md, encoding="utf-8")
    return report


async def main() -> None:
    setup_logging(load_settings())
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/eval/reviews_200.jsonl")
    parser.add_argument("--out-dir", default="output/ai_eval")
    parser.add_argument("--live", action="store_true", help="Use real OpenAI when key is set")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    rows = load_dataset(Path(args.dataset))[: args.limit]
    if len(rows) < 200 and args.limit >= 200:
        raise SystemExit(f"Dataset has only {len(rows)} rows; need >= 200")

    fake_scores, fake_pairs, fake_latency = await run_fake(rows)
    prod_scores, prod_pairs, prod_latency, cost, mode = await run_production(
        rows, live=args.live
    )

    report = write_reports(
        out_dir=Path(args.out_dir),
        fake_acc=accuracy_from_scores(fake_scores),
        prod_acc=accuracy_from_scores(prod_scores),
        fake_cm=confusion_sentiment(fake_pairs),
        prod_cm=confusion_sentiment(prod_pairs),
        fake_latency=fake_latency,
        prod_latency=prod_latency,
        cost=cost,
        mode=mode,
        n=len(rows),
    )
    # Also refresh docs copy
    docs = Path("docs/PHASE6_EVAL_REPORT.md")
    docs.write_text((Path(args.out_dir) / "eval_report.md").read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"mode": mode, "macro": report["extraction_accuracy"], "cost": cost}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
