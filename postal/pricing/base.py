"""PricingProvider protocol — one adapter per carrier, identical I/O."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from postal.pricing.types import QuoteRequest, QuoteResult


@runtime_checkable
class PricingProvider(Protocol):
    """Reusable carrier pricing adapter.

    Implementations must:
    - never invent prices or ETAs
    - return QuoteResult with the canonical public fields
    - report unavailable/error clearly when evidence is missing
    """

    @property
    def slug(self) -> str:
        """Stable machine id, e.g. 'tipax'."""
        ...

    @property
    def company(self) -> str:
        """Human company name, e.g. 'Tipax'."""
        ...

    @property
    def data_source(self) -> str:
        """Short label for the upstream used, e.g. 'chapar_cdn_api'."""
        ...

    def quote(self, request: QuoteRequest) -> QuoteResult:
        """Return a single normalized quote (or unavailable/error result)."""
        ...
