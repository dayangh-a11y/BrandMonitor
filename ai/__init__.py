"""AI analysis package (adapters, pipeline, worker)."""

__all__ = [
    "AnalysisPipeline",
    "AnalysisWorker",
    "FakeAdapter",
    "ModelAdapter",
]


def __getattr__(name: str):
    if name == "AnalysisPipeline":
        from ai.pipeline import AnalysisPipeline

        return AnalysisPipeline
    if name == "AnalysisWorker":
        from ai.worker import AnalysisWorker

        return AnalysisWorker
    if name == "FakeAdapter":
        from ai.adapters.fake import FakeAdapter

        return FakeAdapter
    if name == "ModelAdapter":
        from ai.adapters.base import ModelAdapter

        return ModelAdapter
    raise AttributeError(name)
