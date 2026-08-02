from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from ai.accounting import CostLedger, TokenUsage
from ai.adapters.base import ModelAdapter
from ai.metrics_ai import AI_METRICS
from ai.prompts.analysis_v1 import SYSTEM_PROMPT, build_user_prompt
from ai.resilience import RateLimiter, ResilienceError, RetryPolicy, with_retry
from ai.taxonomy import PROMPT_VERSION, SCHEMA_VERSION
from core.logging_setup import get_logger
from models.analysis import AnalysisDTO, ConfidenceByField
from models.review import Review

log = get_logger("ai_worker")


class OpenAIAdapter(ModelAdapter):
    """
    Production OpenAI Chat Completions adapter.

    Keeps ModelAdapter.extract() contract unchanged.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: int = 800,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 45.0,
        max_attempts: int = 4,
        min_interval_seconds: float = 0.05,
        http_client: httpx.AsyncClient | None = None,
        ledger: CostLedger | None = None,
    ):
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout_seconds)
        self._policy = RetryPolicy(
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
        )
        self._limiter = RateLimiter(min_interval_seconds=min_interval_seconds)
        self.ledger = ledger or CostLedger(model=model)

    @property
    def id(self) -> str:
        return f"openai:{self._model}"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def health(self) -> bool:
        return bool(self._api_key)

    async def extract(self, review: Review, *, meta: dict | None = None) -> AnalysisDTO:
        text = (review.text or "").strip()
        if len(text) < 3:
            return AnalysisDTO(
                sentiment="Neutral",
                status="skipped",
                error="empty_or_too_short",
                provider="openai",
                model_id=self.id,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                confidence_overall=0.0,
                raw_response={"reason": "skipped_short_text", "meta": meta or {}},
            )

        t0 = time.perf_counter()
        attempts = 0
        try:

            async def _call():
                return await self._chat_completion(review)

            raw_payload, attempts = await with_retry(
                _call,
                policy=self._policy,
                rate_limiter=self._limiter,
                is_retryable=self._is_retryable,
            )
            usage = TokenUsage.from_openai(raw_payload.get("usage"))
            latency_ms = (time.perf_counter() - t0) * 1000
            cost_row = self.ledger.record(
                usage,
                success=True,
                latency_ms=latency_ms,
                retries=attempts,
                meta={"review_meta": meta or {}},
            )
            dto = self._dto_from_response(raw_payload, review=review)
            AI_METRICS.record_request(
                success=True,
                latency_ms=latency_ms,
                cost_usd=float(cost_row["cost_usd"]),
                retries=max(0, attempts - 1),
                confidence=dto.confidence_overall,
                cached=False,
            )
            log.info(
                "openai_extract_ok model=%s latency_ms=%.1f tokens=%s",
                self._model,
                latency_ms,
                usage.total_tokens,
            )
            return dto
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.perf_counter() - t0) * 1000
            self.ledger.record(
                TokenUsage(),
                success=False,
                latency_ms=latency_ms,
                retries=attempts or 1,
                meta={"error": str(exc), "meta": meta or {}},
            )
            AI_METRICS.record_request(
                success=False,
                latency_ms=latency_ms,
                cost_usd=0.0,
                retries=max(0, (attempts or 1) - 1),
                confidence=None,
                cached=False,
            )
            log.error("openai_extract_failed error=%s", exc)
            return AnalysisDTO(
                sentiment="Neutral",
                status="failed",
                error=str(exc),
                provider="openai",
                model_id=self.id,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                confidence_overall=0.0,
                raw_response={"error": str(exc), "meta": meta or {}},
            )

    async def _chat_completion(self, review: Review) -> dict[str, Any]:
        body = {
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        review.text or "",
                        branch_name=review.branch_name or "",
                        rating=review.rating,
                    ),
                },
            ],
        }
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"OpenAI HTTP {response.status_code}: {response.text[:500]}",
                request=response.request,
                response=response,
            )
        return response.json()

    @staticmethod
    def _is_retryable(exc: BaseException) -> bool:
        if isinstance(exc, ResilienceError):
            return False
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code if exc.response is not None else 0
            return code in {408, 409, 429, 500, 502, 503, 504}
        if isinstance(exc, (httpx.TransportError, TimeoutError)):
            return True
        return False

    def _dto_from_response(self, payload: dict[str, Any], *, review: Review) -> AnalysisDTO:
        content = ""
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Unexpected OpenAI response shape: {exc}") from exc

        parsed = _parse_json_content(content)
        confidence_by_field = parsed.get("confidence_by_field") or {}
        return AnalysisDTO(
            sentiment=parsed.get("sentiment") or "Neutral",
            complaint_categories=list(parsed.get("complaint_categories") or []),
            positive_categories=list(parsed.get("positive_categories") or []),
            delivery_speed=parsed.get("delivery_speed"),
            customer_service=parsed.get("customer_service"),
            staff_behavior=parsed.get("staff_behavior"),
            package_damage=parsed.get("package_damage"),
            pricing=parsed.get("pricing"),
            tracking=parsed.get("tracking"),
            professionalism=parsed.get("professionalism"),
            mentioned_employees=list(parsed.get("mentioned_employees") or []),
            mentioned_city=parsed.get("mentioned_city"),
            mentioned_branch=parsed.get("mentioned_branch") or (review.branch_name or None),
            urgency=parsed.get("urgency") or "low",
            evidence_spans=parsed.get("evidence_spans") or {},
            confidence_overall=float(parsed.get("confidence_overall") or 0.0),
            confidence_by_field=ConfidenceByField(
                **{
                    k: float(confidence_by_field.get(k, 0.0) or 0.0)
                    for k in ConfidenceByField.model_fields
                }
            ),
            language=parsed.get("language"),
            status="succeeded",
            provider="openai",
            model_id=self.id,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            raw_response={
                "provider": "openai",
                "model": self._model,
                "response": payload,
                "parsed_content": parsed,
            },
        )


def _parse_json_content(content: str) -> dict[str, Any]:
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))
