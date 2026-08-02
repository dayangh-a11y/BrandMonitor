from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# USD per 1M tokens (approximate public list prices; override via config if needed)
_MODEL_PRICES_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_openai(cls, usage: dict[str, Any] | None) -> TokenUsage:
        usage = usage or {}
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        total = int(usage.get("total_tokens") or (prompt + completion))
        return cls(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


@dataclass
class CostLedger:
    """In-process token + cost accounting for AI providers."""

    model: str = "gpt-4o-mini"
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None
    records: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.input_price_per_1m is None or self.output_price_per_1m is None:
            inp, out = _MODEL_PRICES_PER_1M.get(self.model, (1.0, 3.0))
            self.input_price_per_1m = inp if self.input_price_per_1m is None else self.input_price_per_1m
            self.output_price_per_1m = out if self.output_price_per_1m is None else self.output_price_per_1m

    def estimate_cost_usd(self, usage: TokenUsage) -> float:
        assert self.input_price_per_1m is not None
        assert self.output_price_per_1m is not None
        return (
            usage.prompt_tokens * self.input_price_per_1m
            + usage.completion_tokens * self.output_price_per_1m
        ) / 1_000_000.0

    def record(
        self,
        usage: TokenUsage,
        *,
        success: bool,
        latency_ms: float,
        retries: int = 0,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cost = self.estimate_cost_usd(usage)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "model": self.model,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cost_usd": round(cost, 8),
            "success": success,
            "latency_ms": round(latency_ms, 3),
            "retries": retries,
            "meta": meta or {},
        }
        self.records.append(row)
        return row

    def summary(self) -> dict[str, Any]:
        if not self.records:
            return {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "avg_latency_ms": 0.0,
                "retry_events": 0,
            }
        successes = sum(1 for r in self.records if r["success"])
        return {
            "requests": len(self.records),
            "successes": successes,
            "failures": len(self.records) - successes,
            "prompt_tokens": sum(r["prompt_tokens"] for r in self.records),
            "completion_tokens": sum(r["completion_tokens"] for r in self.records),
            "total_tokens": sum(r["total_tokens"] for r in self.records),
            "cost_usd": round(sum(r["cost_usd"] for r in self.records), 6),
            "avg_latency_ms": round(
                sum(r["latency_ms"] for r in self.records) / len(self.records), 3
            ),
            "retry_events": sum(max(0, int(r["retries"]) - 1) for r in self.records),
            "model": self.model,
            "input_price_per_1m": self.input_price_per_1m,
            "output_price_per_1m": self.output_price_per_1m,
        }
