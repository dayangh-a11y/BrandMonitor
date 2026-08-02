# Phase 6 AI Evaluation Report

Dataset size: **200** reviews (`data/eval/reviews_200.jsonl`)  
Production mode: **schema_mock_openai**

## Extraction accuracy

| Field | Fake | Production |
|-------|------|------------|
| sentiment | 59.00% | 100.00% |
| complaint_categories | 61.50% | 100.00% |
| positive_categories | 58.50% | 100.00% |
| delivery_speed | 58.50% | 100.00% |
| customer_service | 51.00% | 100.00% |
| package_damage | 79.50% | 100.00% |
| pricing | 87.50% | 100.00% |
| tracking | 83.50% | 100.00% |

Macro accuracy — Fake: **67.37%** · Production: **100.00%**

## Sentiment confusion matrix (Fake)

```json
{
  "Positive": {
    "Positive": 42,
    "Neutral": 41,
    "Negative": 0
  },
  "Neutral": {
    "Positive": 0,
    "Neutral": 32,
    "Negative": 0
  },
  "Negative": {
    "Positive": 0,
    "Neutral": 41,
    "Negative": 44
  }
}
```

## Sentiment confusion matrix (Production)

```json
{
  "Positive": {
    "Positive": 83,
    "Neutral": 0,
    "Negative": 0
  },
  "Neutral": {
    "Positive": 0,
    "Neutral": 32,
    "Negative": 0
  },
  "Negative": {
    "Positive": 0,
    "Neutral": 0,
    "Negative": 85
  }
}
```

## Latency

| Adapter | Total (s) | Avg (ms/review) |
|---------|-----------|-----------------|
| Fake | 0.007 | 0.033 |
| Production | 0.072 | 0.358 |

## Cost

```json
{
  "requests": 200,
  "successes": 200,
  "failures": 0,
  "prompt_tokens": 80000,
  "completion_tokens": 44000,
  "total_tokens": 124000,
  "cost_usd": 0.0384,
  "avg_latency_ms": 0.243,
  "retry_events": 0,
  "model": "gpt-4o-mini",
  "input_price_per_1m": 0.15,
  "output_price_per_1m": 0.6
}
```

Projected cost for 1000 reviews (same mix): **$0.192**

> If `production_mode=schema_mock_openai`, live OpenAI was not called (no `OPENAI_API_KEY`).  
> Accuracy for production then reflects the OpenAI adapter parse/validate path on gold-aligned JSON.  
> Fake macro accuracy **67.37%** vs gold is the offline baseline to beat with `--live` OpenAI.

## Example production raw_response (shape)

Stored on each `review_analyses.raw_response` for debugging:

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "response": { "id": "chatcmpl-...", "choices": [{"message": {"content": "{...json...}"}}], "usage": {} },
  "parsed_content": { "sentiment": "Negative", "complaint_categories": ["delivery_speed"] }
}
```

## Remaining AI limitations

See `docs/PHASE6_AI.md` — live Persian quality, in-process metrics, closed taxonomy, approximate pricing, need periodic `--live` golden evaluation.
