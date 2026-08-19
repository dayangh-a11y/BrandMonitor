"""Module 13 — Audit Log."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy.orm import Session

from src.standardization.constants import PLATFORM_VERSION
from src.standardization.models import StdAuditLog


def write_audit(
    session: Session,
    *,
    question: str | None = None,
    rule_id: str | None = None,
    sql_text: str | None = None,
    rows_analyzed: int | None = None,
    execution_time_ms: float | None = None,
    version: str | None = None,
    confidence: str | None = None,
    result_summary: str | None = None,
    payload: dict[str, Any] | None = None,
) -> StdAuditLog:
    row = StdAuditLog(
        question=question,
        rule_id=rule_id,
        sql_text=sql_text,
        rows_analyzed=rows_analyzed,
        execution_time_ms=execution_time_ms,
        version=version or PLATFORM_VERSION,
        confidence=confidence,
        result_summary=result_summary,
        payload_json=payload,
    )
    session.add(row)
    session.flush()
    return row


@contextmanager
def audited_query(
    session: Session,
    *,
    question: str,
    rule_id: str,
    sql_text: str | None = None,
    version: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Context manager that records execution time + rows into the audit log."""
    started = time.perf_counter()
    state: dict[str, Any] = {
        "rows_analyzed": 0,
        "confidence": None,
        "result_summary": None,
        "payload": {},
    }
    try:
        yield state
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        write_audit(
            session,
            question=question,
            rule_id=rule_id,
            sql_text=sql_text,
            rows_analyzed=int(state.get("rows_analyzed") or 0),
            execution_time_ms=round(elapsed_ms, 3),
            version=version,
            confidence=state.get("confidence"),
            result_summary=state.get("result_summary"),
            payload=state.get("payload") or {},
        )
