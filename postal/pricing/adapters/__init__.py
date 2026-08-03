"""Pricing provider adapters.

Each module registers itself with ``register_provider`` on import.
The registry discovers modules in this package via pkgutil — adding a
future carrier requires only one new adapter file here.
"""
