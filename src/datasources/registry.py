"""Registry mapping datasource names to factory callables."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from src.datasources.base import DataSource
from src.utils.retry import CollectorError

if TYPE_CHECKING:
    pass

_REGISTRY: dict[str, Callable[[], DataSource]] = {}


def register_datasource(name: str, factory: Callable[[], DataSource]) -> None:
    key = name.strip().lower()
    _REGISTRY[key] = factory
    logger.debug("Registered datasource '{}'", key)


def get_datasource(name: str) -> DataSource:
    key = name.strip().lower()
    if key not in _REGISTRY:
        # Lazy import concrete sources to avoid hard-wiring at import time
        _ensure_builtins_loaded()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise CollectorError(f"Unknown datasource '{name}'. Available: {available}")
    return _REGISTRY[key]()


def list_datasources() -> list[str]:
    _ensure_builtins_loaded()
    return sorted(_REGISTRY)


def _ensure_builtins_loaded() -> None:
    if "asbdavani" in _REGISTRY:
        return
    # Import side-effect: asbdavani package registers itself
    from src.asbdavani import register  # noqa: F401

    register()


__all__ = [
    "DataSource",
    "get_datasource",
    "list_datasources",
    "register_datasource",
]
