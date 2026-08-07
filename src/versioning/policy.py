"""Append-only versioning policy for Raw records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.versioning.hashing import compute_source_hash

T = TypeVar("T")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def prepare_append(
    session: Session,
    *,
    model: type[T],
    identity_filters: list[Any],
    payload: Any,
    source_url: str | None,
    parser_version: str,
    field_values: dict[str, Any],
) -> T | None:
    """
    Insert a new Raw version if content changed; never overwrite prior rows.

    Returns:
      - new row if inserted
      - None if current hash matches (duplicate / unchanged)
    """
    source_hash = compute_source_hash(payload)
    current = session.scalar(
        select(model).where(*identity_filters, model.is_current.is_(True))  # type: ignore[attr-defined]
    )

    if current is not None and getattr(current, "source_hash", None) == source_hash:
        logger.debug(
            "Raw unchanged for {} hash={} — skip insert",
            model.__tablename__,  # type: ignore[attr-defined]
            source_hash[:12],
        )
        # Touch updated_time only as metadata on the current pointer? Policy says
        # never silently overwrite important values — skip entirely.
        return None

    next_version = 1
    if current is not None:
        next_version = int(getattr(current, "version", 1)) + 1
        current.is_current = False  # type: ignore[attr-defined]
        current.updated_time = now_utc()  # type: ignore[attr-defined]
        session.flush()

    row = model(  # type: ignore[call-arg]
        **field_values,
        source_url=source_url,
        parser_version=parser_version,
        crawl_time=now_utc(),
        updated_time=now_utc(),
        source_hash=source_hash,
        is_current=True,
        version=next_version,
    )
    session.add(row)
    session.flush()
    logger.info(
        "Raw append {}.{} version={} hash={}",
        model.__tablename__,  # type: ignore[attr-defined]
        next_version,
        next_version,
        source_hash[:12],
    )
    return row
