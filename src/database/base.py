"""SQLAlchemy declarative base shared by Raw and Features layers."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Common metadata base for the data warehouse."""
