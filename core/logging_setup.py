from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from core.config import Settings, load_settings

COMPONENT_LOGGERS = ("crawler", "ai_worker", "scoring", "api", "scheduler", "ops")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "component": getattr(record, "component", record.name.split(".")[-1]),
            "message": record.getMessage(),
        }
        for key in ("run_id", "job_id", "branch_id", "duration_ms", "metric", "error"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ComponentAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("component", self.extra.get("component", "app"))
        return msg, kwargs


_CONFIGURED = False


def setup_logging(settings: Settings | None = None) -> None:
    global _CONFIGURED
    settings = settings or load_settings()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
    root.addHandler(handler)

    for name in COMPONENT_LOGGERS:
        logging.getLogger(name).setLevel(root.level)

    _CONFIGURED = True


def get_logger(component: str) -> ComponentAdapter:
    if not _CONFIGURED:
        setup_logging()
    if component not in COMPONENT_LOGGERS and not component.startswith("brandmonitor"):
        # Still allow custom names, but prefer known components.
        pass
    return ComponentAdapter(logging.getLogger(component), {"component": component})
