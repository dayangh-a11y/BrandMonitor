"""Persian / geo / date / rating normalization for multi-source rows."""

from __future__ import annotations

import re
from datetime import datetime

from collectors.iran_geo import IRAN_PROVINCES, PROVINCE_CITIES

# Arabic Yeh/Kaf → Persian
_AR_YE = "ي"
_FA_YE = "ی"
_AR_KAF = "ك"
_FA_KAF = "ک"
_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670]")
_WS = re.compile(r"\s+")
_ZWNJ = "\u200c"

_PROVINCE_ALIASES: dict[str, str] = {}
for p in IRAN_PROVINCES:
    _PROVINCE_ALIASES[p["fa"]] = p["fa"]
    _PROVINCE_ALIASES[p["en"].casefold()] = p["fa"]
    _PROVINCE_ALIASES[p["en"]] = p["fa"]

# Common aliases
_PROVINCE_ALIASES.update(
    {
        "تهران": "تهران",
        "استان تهران": "تهران",
        "tehran province": "تهران",
        "خراسان رضوی": "خراسان رضوی",
        "khorasan razavi": "خراسان رضوی",
        "آذربایجان شرقی": "آذربایجان شرقی",
        "آذربايجان شرقي": "آذربایجان شرقی",
    }
)

_CITY_TO_PROVINCE: dict[str, tuple[str, str]] = {}
for p_en, cities in PROVINCE_CITIES.items():
    p_fa = next(p["fa"] for p in IRAN_PROVINCES if p["en"] == p_en)
    for c in cities:
        _CITY_TO_PROVINCE[c.fa] = (c.fa, p_fa)
        _CITY_TO_PROVINCE[c.en.casefold()] = (c.fa, p_fa)


def normalize_persian(text: str) -> str:
    if not text:
        return ""
    t = str(text)
    t = t.replace(_AR_YE, _FA_YE).replace(_AR_KAF, _FA_KAF)
    t = _DIACRITICS.sub("", t)
    t = t.replace(_ZWNJ, " ")
    t = _WS.sub(" ", t).strip()
    return t


def normalize_branch_name(name: str) -> str:
    t = normalize_persian(name)
    t = re.sub(r"\b(شعبه|نمایندگی|دفتر|tipax|chapar|mahex|alopeyk|post)\b", "", t, flags=re.I)
    return _WS.sub(" ", t).strip() or normalize_persian(name)


def normalize_province(value: str) -> str:
    raw = normalize_persian(value)
    if not raw:
        return ""
    if raw in _PROVINCE_ALIASES:
        return _PROVINCE_ALIASES[raw]
    key = raw.casefold()
    if key in _PROVINCE_ALIASES:
        return _PROVINCE_ALIASES[key]
    for needle, fa in _PROVINCE_ALIASES.items():
        if needle and needle in raw:
            return fa
    return raw


def normalize_city(value: str, province: str = "") -> str:
    raw = normalize_persian(value)
    if not raw:
        return ""
    hit = _CITY_TO_PROVINCE.get(raw) or _CITY_TO_PROVINCE.get(raw.casefold())
    if hit:
        return hit[0]
    return raw


def normalize_rating(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        r = float(value)
    except (TypeError, ValueError):
        return None
    if r < 0:
        return None
    # Some stores use 0-100
    if r > 5 and r <= 100:
        r = r / 20.0
    return round(max(0.0, min(5.0, r)), 2)


_ISO = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
_FA_REL = re.compile(r"(\d+)\s*(روز|هفته|ماه|سال)\s*پیش")


def normalize_date(value: str) -> str:
    """Return YYYY-MM-DD when parseable, else normalized original or empty."""
    raw = normalize_persian(value or "")
    if not raw:
        return ""
    m = _ISO.match(raw.replace(".", "-"))
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return raw
    # Keep relative Persian/English as-is but cleaned (cannot invent absolute dates)
    return raw


def infer_city_province(address: str, city: str = "", province: str = "") -> tuple[str, str]:
    city_n = normalize_city(city)
    prov_n = normalize_province(province)
    blob = normalize_persian(address)
    if not city_n:
        for needle, (cfa, pfa) in _CITY_TO_PROVINCE.items():
            if needle and needle in blob:
                city_n, prov_n = cfa, prov_n or pfa
                break
    if not prov_n:
        prov_n = normalize_province(blob)
        if prov_n == blob:
            prov_n = ""
            for p in IRAN_PROVINCES:
                if p["fa"] in blob:
                    prov_n = p["fa"]
                    break
    return city_n, prov_n


def is_spam_or_empty(text: str, rating: float | None = None) -> bool:
    t = normalize_persian(text)
    if not t:
        return True
    if len(t) < 2 and (rating is None or rating == 0):
        return True
    # Repeated character spam
    if len(set(t.replace(" ", ""))) <= 1 and len(t) >= 6:
        return True
    if re.fullmatch(r"[.\-_!؟?]+", t):
        return True
    return False
