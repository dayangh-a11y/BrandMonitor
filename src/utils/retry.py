"""Retry helpers with timeout-aware error handling."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from loguru import logger
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T")


class CollectorError(Exception):
    """Base error for collector operations."""


class FetchError(CollectorError):
    """Raised when a page/resource cannot be fetched."""


class ParseError(CollectorError):
    """Raised when page content cannot be parsed into domain models."""


class TimeoutError_(CollectorError):
    """Raised when an operation exceeds its timeout."""


def _log_retry(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "Retry {}/{} after error: {}",
        retry_state.attempt_number,
        retry_state.retry_object.stop.max_attempt_number  # type: ignore[attr-defined]
        if hasattr(retry_state.retry_object.stop, "max_attempt_number")
        else "?",
        exc,
    )


def with_retry(
    *,
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    exceptions: tuple[type[BaseException], ...] = (FetchError, TimeoutError_, TimeoutError),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator factory for retrying flaky network / browser operations."""

    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=_log_retry,
    )
