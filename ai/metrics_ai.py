from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _day_key(ts: datetime | None = None) -> str:
    ts = ts or datetime.now(timezone.utc)
    return ts.strftime("%Y-%m-%d")


@dataclass
class AIMetrics:
    """AI-specific metrics for ops dashboards (in-process)."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    requests_by_day: Counter[str] = field(default_factory=Counter)
    cost_by_day: Counter[str] = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)
    successes: int = 0
    failures: int = 0
    retries: int = 0
    confidence_buckets: Counter[str] = field(default_factory=Counter)
    cache_hits: int = 0
    cache_misses: int = 0

    def record_request(
        self,
        *,
        success: bool,
        latency_ms: float,
        cost_usd: float = 0.0,
        retries: int = 0,
        confidence: float | None = None,
        cached: bool = False,
    ) -> None:
        day = _day_key()
        with self._lock:
            self.requests_by_day[day] += 1
            self.cost_by_day[day] += cost_usd
            self.latencies_ms.append(latency_ms)
            if success:
                self.successes += 1
            else:
                self.failures += 1
            self.retries += max(0, retries)
            if cached:
                self.cache_hits += 1
            else:
                self.cache_misses += 1
            if confidence is not None:
                self.confidence_buckets[self._bucket(confidence)] += 1

    @staticmethod
    def _bucket(confidence: float) -> str:
        if confidence < 0.4:
            return "0.0-0.4"
        if confidence < 0.7:
            return "0.4-0.7"
        if confidence < 0.9:
            return "0.7-0.9"
        return "0.9-1.0"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total = self.successes + self.failures
            day = _day_key()
            avg_latency = (
                sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0
            )
            return {
                "requests_today": int(self.requests_by_day.get(day, 0)),
                "cost_today_usd": round(float(self.cost_by_day.get(day, 0.0)), 6),
                "requests_by_day": dict(self.requests_by_day),
                "cost_by_day_usd": {k: round(v, 6) for k, v in self.cost_by_day.items()},
                "average_latency_ms": round(avg_latency, 3),
                "success_rate": round(self.successes / total, 4) if total else 0.0,
                "retry_rate": round(self.retries / total, 4) if total else 0.0,
                "successes": self.successes,
                "failures": self.failures,
                "retries": self.retries,
                "confidence_distribution": dict(self.confidence_buckets),
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
            }

    def reset(self) -> None:
        with self._lock:
            self.requests_by_day.clear()
            self.cost_by_day.clear()
            self.latencies_ms.clear()
            self.successes = 0
            self.failures = 0
            self.retries = 0
            self.confidence_buckets.clear()
            self.cache_hits = 0
            self.cache_misses = 0


AI_METRICS = AIMetrics()
