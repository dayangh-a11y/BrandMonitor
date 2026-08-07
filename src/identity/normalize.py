"""Persian-aware text normalization for horse identity.

Never treat raw strings as identity keys. Always normalize first.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Zero-width / invisible characters common in Persian web text
_ZW_CHARS = (
    "\u200b",  # ZERO WIDTH SPACE
    "\u200c",  # ZWNJ
    "\u200d",  # ZWJ
    "\ufeff",  # BOM
    "\u2060",  # WORD JOINER
    "\u00ad",  # SOFT HYPHEN
)

# Arabic letter forms → Persian
_AR_FA_MAP = str.maketrans(
    {
        "ك": "ک",
        "ي": "ی",
        "ى": "ی",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ۀ": "ه",
        "ء": "",
        "ٔ": "",
        "ٰ": "",
    }
)

_DIGITS_FA_AR = str.maketrans(
    {
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
)

_PUNCT_RE = re.compile("[" + re.escape("\"'`«»٬،؛:·•|/\\_[](){}<>") + "“”‘’]+")
_SPACE_RE = re.compile(r"\s+")
_PAREN_TAIL_RE = re.compile(r"\([^)]*\)")


def strip_zero_width(value: str) -> str:
    text = value
    for ch in _ZW_CHARS:
        text = text.replace(ch, "")
    return text


def normalize_persian_text(value: str | None, *, keep_spaces: bool = True) -> str:
    """
    Normalize Persian/Arabic display text for identity matching.

    - NFKC unicode
    - remove zero-width characters
    - map Arabic letters to Persian
    - normalize digits
    - strip quotes/punctuation noise
    - collapse whitespace (or remove all spaces when keep_spaces=False)
    - casefold for Latin fragments
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = strip_zero_width(text)
    text = text.translate(_AR_FA_MAP)
    text = text.translate(_DIGITS_FA_AR)
    text = _PUNCT_RE.sub(" ", text)
    text = text.casefold().strip()
    if keep_spaces:
        text = _SPACE_RE.sub(" ", text)
    else:
        text = _SPACE_RE.sub("", text)
    return text


def normalize_name(value: str | None) -> str:
    """Canonical name key used for aliases and clustering."""
    text = normalize_persian_text(value, keep_spaces=True)
    # Drop parenthetical nicknames: بادپا (تماشا) → بادپا
    text = _PAREN_TAIL_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def normalize_sex(value: str | None) -> str | None:
    """Map sex labels to male|female|gelding|unknown."""
    if not value:
        return None
    n = normalize_persian_text(value, keep_spaces=False)
    if not n:
        return None
    if n in {"نر", "مادهنر", "male", "colt", "stallion", "horse", "h"}:
        return "male"
    if n in {"ماده", "female", "filly", "mare", "m"}:
        return "female"
    if n in {"اخته", "گلدینگ", "gelding", "g"}:
        return "gelding"
    if "اخته" in n or "geld" in n:
        return "gelding"
    if "ماده" in n or "filly" in n or "mare" in n or n == "f":
        return "female"
    if "نر" in n or "colt" in n or "stallion" in n or n == "c":
        return "male"
    return "unknown"


def name_similarity(a: str | None, b: str | None) -> float:
    """Fuzzy similarity on normalized names (0..1). Never exact-raw-string."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Token-aware: if one contains the other after space removal, boost
    ca, cb = na.replace(" ", ""), nb.replace(" ", "")
    if ca == cb:
        return 0.99
    if ca in cb or cb in ca:
        base = SequenceMatcher(None, na, nb).ratio()
        return max(base, 0.90)
    return SequenceMatcher(None, na, nb).ratio()
