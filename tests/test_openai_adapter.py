from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from ai.accounting import CostLedger, TokenUsage
from ai.adapters.openai_adapter import OpenAIAdapter
from ai.factory import build_adapter
from ai.metrics_ai import AI_METRICS
from ai.pipeline import AnalysisPipeline
from ai.prompts.analysis_v1 import SYSTEM_PROMPT, build_user_prompt, expected_json_keys
from ai.resilience import RateLimiter, RetryPolicy, with_retry
from ai.taxonomy import SCHEMA_VERSION
from core.config import load_settings
from core.db import Database
from models.review import Review


def _openai_payload(content: dict, *, status_extra: dict | None = None) -> dict:
    body = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(content, ensure_ascii=False),
                }
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "model": "gpt-4o-mini",
    }
    if status_extra:
        body.update(status_extra)
    return body


SAMPLE_ANALYSIS = {
    "sentiment": "Negative",
    "complaint_categories": ["delivery_speed", "package_damage"],
    "positive_categories": [],
    "delivery_speed": "slow",
    "customer_service": "bad",
    "staff_behavior": "bad",
    "package_damage": True,
    "pricing": None,
    "tracking": None,
    "professionalism": None,
    "mentioned_employees": [],
    "mentioned_city": "Tehran",
    "mentioned_branch": "Vanak",
    "urgency": "medium",
    "evidence_spans": {"sentiment": "late and damaged"},
    "confidence_overall": 0.91,
    "confidence_by_field": {
        "sentiment": 0.9,
        "complaint_categories": 0.88,
        "positive_categories": 0.2,
        "delivery_speed": 0.9,
        "customer_service": 0.7,
        "staff_behavior": 0.6,
        "package_damage": 0.95,
        "pricing": 0.1,
        "tracking": 0.1,
        "professionalism": 0.1,
        "mentioned_employees": 0.1,
        "mentioned_city": 0.8,
        "mentioned_branch": 0.7,
    },
    "language": "en",
}


def test_prompt_covers_required_fields():
    assert "sentiment" in SYSTEM_PROMPT
    assert "confidence" in SYSTEM_PROMPT.lower() or "confidence_overall" in SYSTEM_PROMPT
    for key in expected_json_keys():
        assert key in SYSTEM_PROMPT
    user = build_user_prompt("تأخیر زیاد", branch_name="ونک", rating=1.0)
    assert "تأخیر" in user


def test_token_cost_accounting():
    ledger = CostLedger(model="gpt-4o-mini")
    usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000)
    cost = ledger.estimate_cost_usd(usage)
    assert cost == pytest.approx(0.15 + 0.60)
    ledger.record(usage, success=True, latency_ms=12.0, retries=1)
    summary = ledger.summary()
    assert summary["requests"] == 1
    assert summary["cost_usd"] > 0


def test_retry_and_rate_limit():
    async def run() -> None:
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("boom")
            return "ok"

        result, attempts = await with_retry(
            flaky,
            policy=RetryPolicy(max_attempts=4, base_delay_seconds=0.01, timeout_seconds=2),
            rate_limiter=RateLimiter(min_interval_seconds=0.0),
            is_retryable=lambda e: isinstance(e, httpx.ConnectError),
        )
        assert result == "ok"
        assert attempts == 3

    asyncio.run(run())


def test_openai_adapter_mocked_success():
    async def run() -> None:
        AI_METRICS.reset()

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/chat/completions")
            return httpx.Response(200, json=_openai_payload(SAMPLE_ANALYSIS))

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter = OpenAIAdapter(
            api_key="sk-test",
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=400,
            http_client=client,
            min_interval_seconds=0.0,
        )
        review = Review(text="Package arrived late and was damaged in Tehran.", rating=1)
        dto = await adapter.extract(review, meta={"review_id": 1})
        assert dto.status == "succeeded"
        assert dto.provider == "openai"
        assert dto.sentiment == "Negative"
        assert "package_damage" in dto.complaint_categories
        assert "response" in dto.raw_response
        assert adapter.ledger.summary()["requests"] == 1
        snap = AI_METRICS.snapshot()
        assert snap["successes"] >= 1
        await adapter.close()

    asyncio.run(run())


def test_openai_adapter_retries_on_429():
    async def run() -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, text="rate limit")
            return httpx.Response(200, json=_openai_payload(SAMPLE_ANALYSIS))

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter = OpenAIAdapter(
            api_key="sk-test",
            http_client=client,
            max_attempts=3,
            min_interval_seconds=0.0,
        )
        # Patch policy delays via low base in resilience by using short policy already on adapter
        adapter._policy.base_delay_seconds = 0.01
        dto = await adapter.extract(Review(text="late damaged package review text", rating=1))
        assert dto.status == "succeeded"
        assert calls["n"] == 2
        await adapter.close()

    asyncio.run(run())


def test_pipeline_skips_identical_reviews(tmp_path):
    async def run() -> None:
        db = Database(str(tmp_path / "ai.db"))
        await db.connect()
        from models.branch import Branch

        cid = await db.upsert_company("AICo")
        bid = await db.upsert_branch(
            cid, Branch(name="HQ", address="X", company_name="AICo", place_id="p")
        )
        rid = await db.upsert_review(
            bid, Review(text="Fast delivery and friendly staff.", rating=5, external_id="r1")
        )

        def handler(request: httpx.Request) -> httpx.Response:
            content = dict(SAMPLE_ANALYSIS)
            content["sentiment"] = "Positive"
            content["complaint_categories"] = []
            content["positive_categories"] = ["delivery_speed"]
            content["package_damage"] = False
            return httpx.Response(200, json=_openai_payload(content))

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter = OpenAIAdapter(api_key="sk", http_client=client, min_interval_seconds=0.0)
        pipeline = AnalysisPipeline(db, adapter)
        review = Review(text="Fast delivery and friendly staff.", rating=5, external_id="r1")
        first = await pipeline.process_review(rid, review)
        second = await pipeline.process_review(rid, review)
        assert first.sentiment == second.sentiment
        # second should be cache hit path (same hash)
        assert AI_METRICS.snapshot()["cache_hits"] >= 1
        assert first.raw_response  # raw saved
        await adapter.close()
        await db.close()

    asyncio.run(run())


def test_factory_fake_default(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "fake")
    adapter = build_adapter(load_settings())
    assert adapter.id == "fake-v1"


def test_factory_openai_requires_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_adapter(load_settings())
