from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CompanySpec:
    name: str
    query: str
    source: str = "google_maps"
    enabled: bool = True
    schedule_interval_seconds: int = 21600


@dataclass(frozen=True)
class CollectionDefaults:
    mode: str = "incremental"
    max_attempts: int = 3
    source: str = "google_maps"


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "companies.yaml"


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """
    Minimal YAML subset parser for companies.yaml (no PyYAML dependency).

    Supports:
    - top-level mapping
    - nested mapping under keys
    - list of mappings under a key
    """
    root: dict[str, Any] = {}
    current_list: list[dict[str, Any]] | None = None
    current_list_key: str | None = None
    current_item: dict[str, Any] | None = None
    current_map_key: str | None = None
    current_map: dict[str, Any] | None = None

    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        if indent == 0 and line.endswith(":") and not line.startswith("-"):
            key = line[:-1].strip()
            # Flush previous list
            if current_list_key and current_list is not None:
                if current_item is not None:
                    current_list.append(current_item)
                    current_item = None
                root[current_list_key] = current_list
            current_list = None
            current_list_key = None
            current_map_key = key
            current_map = {}
            root[key] = current_map
            continue

        if indent == 0 and ":" in line and not line.startswith("-"):
            key, value = line.split(":", 1)
            root[key.strip()] = _coerce(value.strip())
            current_list = None
            current_list_key = None
            current_map = None
            current_map_key = None
            continue

        if line.startswith("- "):
            # Starting a list item under the last top-level key that expected a list
            if current_map_key and current_list is None:
                # convert map placeholder to list
                current_list_key = current_map_key
                current_list = []
                root[current_list_key] = current_list
                current_map = None
            if current_item is not None and current_list is not None:
                current_list.append(current_item)
            current_item = {}
            rest = line[2:].strip()
            if ":" in rest:
                k, v = rest.split(":", 1)
                current_item[k.strip()] = _coerce(v.strip())
            continue

        if current_item is not None and ":" in line and indent >= 2:
            k, v = line.split(":", 1)
            current_item[k.strip()] = _coerce(v.strip())
            continue

        if current_map is not None and ":" in line and indent >= 2:
            k, v = line.split(":", 1)
            current_map[k.strip()] = _coerce(v.strip())
            continue

    if current_list is not None and current_item is not None:
        current_list.append(current_item)
        if current_list_key:
            root[current_list_key] = current_list

    return root


def _coerce(value: str) -> Any:
    if value == "":
        return ""
    if value.lower() in {"true", "yes", "on"}:
        return True
    if value.lower() in {"false", "no", "off"}:
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def load_company_config(path: str | Path | None = None) -> tuple[list[CompanySpec], CollectionDefaults]:
    config_path = Path(path or os.getenv("COMPANIES_CONFIG", str(_DEFAULT_CONFIG_PATH)))
    if not config_path.exists():
        raise FileNotFoundError(f"Company config not found: {config_path}")

    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = _parse_simple_yaml(text)

    defaults_raw = data.get("defaults") or {}
    defaults = CollectionDefaults(
        mode=str(defaults_raw.get("mode") or "incremental"),
        max_attempts=int(defaults_raw.get("max_attempts") or 3),
        source=str(defaults_raw.get("source") or "google_maps"),
    )
    companies: list[CompanySpec] = []
    for item in data.get("companies") or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        companies.append(
            CompanySpec(
                name=name,
                query=str(item.get("query") or name).strip(),
                source=str(item.get("source") or defaults.source).strip(),
                enabled=bool(item.get("enabled", True)),
                schedule_interval_seconds=int(
                    item.get("schedule_interval_seconds") or 21600
                ),
            )
        )
    return companies, defaults


def list_enabled_companies(path: str | Path | None = None) -> list[CompanySpec]:
    companies, _ = load_company_config(path)
    return [c for c in companies if c.enabled]
