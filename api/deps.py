from __future__ import annotations

import os
from collections.abc import AsyncIterator

from core.db import Database

_DB: Database | None = None


def get_db_path() -> str:
    return os.getenv("DB_PATH", "data/brandmonitor.db")


async def init_db(path: str | None = None) -> Database:
    global _DB
    db = Database(path or get_db_path())
    await db.connect()
    _DB = db
    return db


async def close_db() -> None:
    global _DB
    if _DB is not None:
        await _DB.close()
        _DB = None


async def get_db() -> AsyncIterator[Database]:
    if _DB is None:
        await init_db()
    assert _DB is not None
    yield _DB
