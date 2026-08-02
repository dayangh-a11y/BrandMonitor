from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from core.logging_setup import get_logger

log = get_logger("ai_worker")

T = TypeVar("T")


@dataclass
class RetryPolicy:
    max_attempts: int = 4
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 20.0
    timeout_seconds: float = 45.0
    jitter: float = 0.25


@dataclass
class RateLimiter:
    """Simple spacing limiter (min interval between acquisitions)."""

    min_interval_seconds: float = 0.05
    _lock: asyncio.Lock | None = None
    _last: float = 0.0

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        assert self._lock is not None
        async with self._lock:
            now = time.monotonic()
            wait = self.min_interval_seconds - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class ResilienceError(RuntimeError):
    def __init__(self, message: str, *, attempts: int, last_error: str | None = None):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


def _delay_for_attempt(policy: RetryPolicy, attempt: int) -> float:
    # attempt is 1-based for the retry about to sleep before next try
    exp = policy.base_delay_seconds * (2 ** (attempt - 1))
    capped = min(exp, policy.max_delay_seconds)
    jitter = capped * policy.jitter * random.random()
    return capped + jitter


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    rate_limiter: RateLimiter | None = None,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    is_retryable: Callable[[BaseException], bool] | None = None,
) -> tuple[T, int]:
    """
    Execute async operation with timeout, rate limit, exponential backoff.

    Returns (result, attempts_used).
    """
    policy = policy or RetryPolicy()
    last_error: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            if rate_limiter is not None:
                await rate_limiter.acquire()
            result = await asyncio.wait_for(operation(), timeout=policy.timeout_seconds)
            return result, attempt
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            retryable = isinstance(exc, retry_on) and (
                True if is_retryable is None else is_retryable(exc)
            )
            log.warning(
                "ai_retryable_error attempt=%s/%s error=%s",
                attempt,
                policy.max_attempts,
                exc,
            )
            if not retryable or attempt >= policy.max_attempts:
                break
            await asyncio.sleep(_delay_for_attempt(policy, attempt))
    raise ResilienceError(
        f"operation failed after {policy.max_attempts} attempts",
        attempts=policy.max_attempts,
        last_error=str(last_error) if last_error else None,
    ) from last_error
