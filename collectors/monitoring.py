from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CrawlMonitor:
    """Lightweight in-memory + serializable crawl monitoring."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def event(self, name: str, **payload: Any) -> None:
        self.events.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": name,
                **payload,
            }
        )

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.events:
            key = str(item.get("event"))
            counts[key] = counts.get(key, 0) + 1
        return {
            "event_count": len(self.events),
            "by_event": counts,
            "last_event": self.events[-1] if self.events else None,
        }

    def to_json(self) -> str:
        return json.dumps(
            {"events": self.events, "summary": self.summary()},
            ensure_ascii=False,
            indent=2,
        )

    def health(self) -> dict[str, Any]:
        failed = sum(1 for e in self.events if e.get("event") == "branch_failed")
        interrupted = sum(1 for e in self.events if e.get("event") == "interrupt_run")
        status = "ok"
        if interrupted:
            status = "degraded"
        if failed > 0:
            status = "attention"
        return {"status": status, "failed_branches": failed, "interrupted": interrupted}
