# Phase 6 — Production AI Integration

## Overview

Replaces Fake-only analysis with a production **OpenAI** provider while keeping the
unchanged `ModelAdapter.extract()` architecture.

| Piece | Path |
|-------|------|
| OpenAI adapter | `ai/adapters/openai_adapter.py` |
| Prompt | `ai/prompts/analysis_v1.py` |
| Retry / timeout / backoff / rate limit | `ai/resilience.py` |
| Token + cost accounting | `ai/accounting.py` |
| AI metrics | `ai/metrics_ai.py` |
| Factory | `ai/factory.py` |
| Batch runner | `scripts/run_ai_analysis.py` |
| Metrics dashboard (file-based) | `scripts/ai_metrics_report.py` |
| Evaluation | `scripts/evaluate_ai.py` |
| Dataset | `data/eval/reviews_200.jsonl` |

**Not modified:** Scoring, API, UI, Crawler, `ModelAdapter` interface, DTO field contract.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `AI_PROVIDER` | `fake` (or `openai` if key set) | `fake` \| `openai` |
| `OPENAI_API_KEY` | empty | Required for live OpenAI |
| `OPENAI_MODEL` | `gpt-4o-mini` | GPT model name |
| `OPENAI_TEMPERATURE` | `0` | Sampling temperature |
| `OPENAI_MAX_TOKENS` | `800` | Completion token limit |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API base |
| `OPENAI_TIMEOUT_SECONDS` | `45` | Per-attempt timeout |
| `OPENAI_MAX_ATTEMPTS` | `4` | Retries with exponential backoff |
| `OPENAI_MIN_INTERVAL_SECONDS` | `0.05` | Client-side rate spacing |

```bash
export AI_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o-mini
export OPENAI_TEMPERATURE=0
PYTHONPATH=. python3 scripts/run_ai_analysis.py --limit 50
```

## Prompt engineering

System prompt (`ANALYSIS_PROMPT_ID=analysis_prompt_v1`) asks for JSON extracting:

sentiment, complaint/positive categories (taxonomy-bound), delivery_speed, customer_service,
staff_behavior, package_damage, pricing, tracking, professionalism, mentioned_employees,
mentioned_city, mentioned_branch, urgency, evidence_spans, confidence_overall,
confidence_by_field, language.

See `ai/prompts/analysis_v1.py`.

## Reliability features

1. **Retry** + **exponential backoff** + **jitter** (`ai/resilience.py`)
2. **Timeout** per attempt
3. **Rate limiting** (min interval between calls)
4. **Token accounting** + **USD cost estimate** (`ai/accounting.py`)
5. **Cache / skip** identical reviews via `input_hash` in `AnalysisPipeline`
6. **raw_response** stored on every analysis row for debugging

## AI metrics dashboard

```bash
PYTHONPATH=. python3 scripts/ai_metrics_report.py --out-dir output/ai_metrics
# open output/ai_metrics/dashboard.html
```

Tracks: requests/day, cost/day, average latency, success rate, retry rate, confidence distribution, cache hits.

## Evaluation

```bash
PYTHONPATH=. python3 scripts/evaluate_ai.py --limit 200
# with live key:
PYTHONPATH=. python3 scripts/evaluate_ai.py --limit 200 --live
```

Produces `output/ai_eval/eval_report.md` and updates `docs/PHASE6_EVAL_REPORT.md`.

Without `OPENAI_API_KEY`, production path runs in **schema_mock_openai** mode (gold-aligned JSON through the real OpenAI adapter) to validate parse/validate/cost metrics.

## Example outputs

### Successful OpenAI DTO (shape)

```json
{
  "sentiment": "Negative",
  "complaint_categories": ["delivery_speed", "package_damage"],
  "positive_categories": [],
  "delivery_speed": "slow",
  "customer_service": "bad",
  "package_damage": true,
  "mentioned_city": "Tehran",
  "confidence_overall": 0.91,
  "provider": "openai",
  "model_id": "openai:gpt-4o-mini",
  "raw_response": { "provider": "openai", "response": { "...": "chat.completion" } }
}
```

### Cost estimate (gpt-4o-mini list prices used in ledger)

From the Phase 6 eval run on 200 reviews (`schema_mock_openai`, ~620 tokens/request):

| Traffic | Approx. USD |
|---------|-------------|
| 200 reviews | **$0.0384** |
| 1,000 reviews (projected) | **~$0.19** |
| 10,000 reviews / month | **~$1.92** |

Live `--live` runs will differ with real prompt/completion sizes. Re-run `scripts/evaluate_ai.py` to refresh.

## Remaining AI limitations

1. Live quality depends on model + prompt; Persian slang/typos still error-prone.
2. No human-in-the-loop review UI yet.
3. Metrics are **in-process** (reset on restart) unless exported.
4. Category taxonomy is closed; novel issues collapse to `other`.
5. Employee/branch NER is quote-based and can miss nicknames.
6. Cost table is approximate public pricing — confirm against your OpenAI bill.
7. Schema-mock eval is not a substitute for periodic live golden-set scoring with `--live`.
8. Scoring engine still consumes analyses separately (unchanged in Phase 6).
