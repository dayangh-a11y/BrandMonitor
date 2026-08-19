"""Content hashing for change detection (never silently overwrite Raw)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def compute_source_hash(payload: Any) -> str:
    """Stable SHA-256 over canonical JSON of the extracted payload."""
    blob = canonical_json(payload).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
