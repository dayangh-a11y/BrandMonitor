from __future__ import annotations

from abc import ABC, abstractmethod

from models.analysis import AnalysisDTO
from models.review import Review


class ModelAdapter(ABC):
    """Provider-agnostic analysis interface. Swap implementations via config."""

    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def extract(self, review: Review, *, meta: dict | None = None) -> AnalysisDTO:
        """Return structured analysis for one review."""
        raise NotImplementedError

    async def health(self) -> bool:
        return True
