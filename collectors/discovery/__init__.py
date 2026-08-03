"""Discovery package — coverage-first nationwide branch finding."""

from collectors.discovery.engine import (
    DiscoveryRunResult,
    NationwideDiscoveryEngine,
    build_zero_province_investigation,
    write_discovery_reports,
)

__all__ = [
    "DiscoveryRunResult",
    "NationwideDiscoveryEngine",
    "build_zero_province_investigation",
    "write_discovery_reports",
]
