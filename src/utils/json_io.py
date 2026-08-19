"""JSON file helpers for collector output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel


def ensure_dir(path: Path | str) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_json(path: Path | str, data: BaseModel | dict[str, Any] | list[Any]) -> Path:
    """Serialize Pydantic model / dict / list to UTF-8 JSON."""
    target = Path(path)
    ensure_dir(target.parent)

    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json", by_alias=True)
    else:
        payload = data

    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Wrote {}", target.resolve())
    return target


def read_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
