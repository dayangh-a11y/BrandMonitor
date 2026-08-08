"""Canonical paths for Master Night Run outputs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "output" / "historical" / "horse_racing.db"
PEDIGREE_DIR = ROOT / "data" / "pedigree"
PF_DIR = ROOT / "data" / "prediction_foundation"
NIGHT_DIR = ROOT / "data" / "night_run"
