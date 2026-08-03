"""Geographic helpers for Fair Comparison Mode."""

from __future__ import annotations

import re
import sqlite3
from typing import Any


def normalize_city(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    # Drop common noise suffixes
    text = re.sub(r"\s*(province|county|city)$", "", text, flags=re.I).strip()
    aliases = {
        "tehran": "tehran",
        "تهران": "tehran",
        "tehran province": "tehran",
        "isfahan": "isfahan",
        "اصفهان": "isfahan",
        "mashhad": "mashhad",
        "مشهد": "mashhad",
        "shiraz": "shiraz",
        "شیراز": "shiraz",
        "tabriz": "tabriz",
        "تبریز": "tabriz",
        "karaj": "karaj",
        "کرج": "karaj",
        "gorgan": "gorgan",
        "گرگان": "gorgan",
    }
    key = text.casefold()
    return aliases.get(key, key)


def normalize_province(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    aliases = {
        "tehran": "tehran",
        "tehran province": "tehran",
        "تهران": "tehran",
        "golestan": "golestan",
        "گلستان": "golestan",
        "isfahan": "isfahan",
        "isfahan province": "isfahan",
        "اصفهان": "isfahan",
    }
    key = text.casefold()
    return aliases.get(key, key)


def company_geo_sets(
    conn: sqlite3.Connection, company_id: int
) -> dict[str, Any]:
    cities = set()
    provinces = set()
    branch_count = 0
    for row in conn.execute(
        "SELECT city, province FROM pi_branches WHERE company_id=?",
        (company_id,),
    ):
        branch_count += 1
        c = normalize_city(row["city"] if isinstance(row, sqlite3.Row) else row[0])
        p = normalize_province(
            row["province"] if isinstance(row, sqlite3.Row) else row[1]
        )
        if c:
            cities.add(c)
        if p:
            provinces.add(p)
    return {
        "cities": cities,
        "provinces": provinces,
        "branch_count": branch_count,
    }


def coverage_percentage(observed: int, target: int) -> float:
    if target <= 0:
        return 0.0
    return round(100.0 * min(observed, target) / float(target), 2)
