from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricSample:
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class MetricsRegistry:
    """
    In-process metrics for production readiness.

    Tracks:
    - crawl_speed (reviews/sec)
    - ai_throughput (jobs/sec)
    - processing_latency_ms
    - duplicate_rate
    - failed_review_rate
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._timings_ms: dict[str, list[float]] = defaultdict(list)
        self._samples: list[MetricSample] = []

    def incr(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += value
            self._samples.append(MetricSample(name=name, value=value, labels=labels))

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value
            self._samples.append(MetricSample(name=name, value=value, labels=labels))

    def observe_ms(self, name: str, duration_ms: float, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._timings_ms[key].append(duration_ms)
            self._samples.append(MetricSample(name=name, value=duration_ms, labels=labels))

    def time_block(self, name: str, **labels: str):
        registry = self

        class _Timer:
            def __enter__(self):
                self._t0 = time.perf_counter()
                return self

            def __exit__(self, exc_type, exc, tb):
                elapsed_ms = (time.perf_counter() - self._t0) * 1000
                registry.observe_ms(name, elapsed_ms, **labels)
                return False

        return _Timer()

    def record_crawl(
        self,
        *,
        reviews_found: int,
        reviews_new: int,
        reviews_updated: int,
        duration_seconds: float,
        failed_branches: int = 0,
        branches: int = 0,
    ) -> None:
        self.incr("reviews_found", reviews_found)
        self.incr("reviews_new", reviews_new)
        self.incr("reviews_updated", reviews_updated)
        self.incr("branches_processed", branches)
        self.incr("branches_failed", failed_branches)
        if duration_seconds > 0:
            self.set_gauge("crawl_speed_reviews_per_sec", reviews_found / duration_seconds)
        total_seen = reviews_new + reviews_updated
        if total_seen > 0:
            self.set_gauge("duplicate_rate", reviews_updated / total_seen)
        if branches > 0:
            self.set_gauge("failed_review_rate", failed_branches / branches)
            self.set_gauge("avg_reviews_per_branch", reviews_found / branches)

    def record_ai_job(self, *, latency_ms: float, success: bool) -> None:
        self.incr("ai_jobs_total")
        self.incr("ai_jobs_succeeded" if success else "ai_jobs_failed")
        self.observe_ms("ai_processing_latency_ms", latency_ms)
        # rolling throughput proxy: successes per observed second bucket is derived in snapshot
        with self._lock:
            successes = self._counters.get("ai_jobs_succeeded", 0.0)
            window = max(len(self._timings_ms.get("ai_processing_latency_ms", [1])), 1)
            avg_latency_s = (
                sum(self._timings_ms.get("ai_processing_latency_ms", [1000.0])) / window
            ) / 1000.0
            if avg_latency_s > 0:
                self._gauges["ai_throughput_jobs_per_sec"] = 1.0 / avg_latency_s

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            timing_avgs = {
                k: (sum(v) / len(v) if v else 0.0) for k, v in self._timings_ms.items()
            }
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "timing_avg_ms": timing_avgs,
                "sample_count": len(self._samples),
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timings_ms.clear()
            self._samples.clear()

    @staticmethod
    def _key(name: str, labels: dict[str, str]) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}|{label_str}"


METRICS = MetricsRegistry()
