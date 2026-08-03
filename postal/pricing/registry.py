"""Provider registry — adapters self-register; engine never hardcodes carriers."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable

from postal.pricing.base import PricingProvider

_REGISTRY: dict[str, PricingProvider] = {}
_DISCOVERED = False


def register_provider(provider: PricingProvider) -> PricingProvider:
    """Register (or replace) a provider instance by slug."""
    slug = provider.slug.strip().lower()
    if not slug:
        raise ValueError("provider.slug must be non-empty")
    _REGISTRY[slug] = provider
    return provider


def unregister_provider(slug: str) -> None:
    _REGISTRY.pop(slug.strip().lower(), None)


def clear_registry() -> None:
    global _DISCOVERED
    _REGISTRY.clear()
    _DISCOVERED = False


def get_provider(slug: str) -> PricingProvider | None:
    ensure_builtin_providers()
    return _REGISTRY.get(slug.strip().lower())


def list_providers(*, discover: bool = True) -> list[PricingProvider]:
    if discover:
        ensure_builtin_providers()
    return [ _REGISTRY[k] for k in sorted(_REGISTRY.keys()) ]


def iter_providers() -> Iterable[PricingProvider]:
    return list_providers()


def ensure_builtin_providers() -> None:
    """Import postal.pricing.adapters.* so each module can register itself."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    import postal.pricing.adapters as pkg

    for mod in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        if mod.name.endswith(".__init__"):
            continue
        # skip private helper modules
        leaf = mod.name.rsplit(".", 1)[-1]
        if leaf.startswith("_"):
            continue
        importlib.import_module(mod.name)
    _DISCOVERED = True
