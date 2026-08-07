"""Database engine / session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.database.base import Base
from src.utils.settings import Settings, get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _register_all_models() -> None:
    """Import every model module so Base.metadata is complete."""
    import src.database.features  # noqa: F401
    import src.database.raw  # noqa: F401
    import src.crawler.models  # noqa: F401
    import src.features.models  # noqa: F401
    import src.quality.models  # noqa: F401
    import src.warehouse.models  # noqa: F401


def get_engine(settings: Settings | None = None, *, url: str | None = None) -> Engine:
    global _engine, _SessionLocal
    cfg = settings or get_settings()
    db_url = url or cfg.database_url
    if _engine is None or (url is not None and str(_engine.url) != db_url):
        _register_all_models()
        _engine = create_engine(db_url, echo=cfg.database_echo, future=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def reset_engine() -> None:
    """Dispose engine (useful in tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db(settings: Settings | None = None, *, url: str | None = None) -> None:
    engine = get_engine(settings, url=url)
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope(
    settings: Settings | None = None,
    *,
    url: str | None = None,
) -> Iterator[Session]:
    get_engine(settings, url=url)
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
