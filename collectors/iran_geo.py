"""Iran province/city helpers for nationwide Maps discovery."""

from __future__ import annotations

# 31 provinces — FA search needles + English labels for metadata.
IRAN_PROVINCES: list[dict[str, str]] = [
    {"fa": "تهران", "en": "Tehran"},
    {"fa": "البرز", "en": "Alborz"},
    {"fa": "اصفهان", "en": "Isfahan"},
    {"fa": "فارس", "en": "Fars"},
    {"fa": "خراسان رضوی", "en": "Razavi Khorasan"},
    {"fa": "آذربایجان شرقی", "en": "East Azerbaijan"},
    {"fa": "آذربایجان غربی", "en": "West Azerbaijan"},
    {"fa": "اردبیل", "en": "Ardabil"},
    {"fa": "یزد", "en": "Yazd"},
    {"fa": "کرمان", "en": "Kerman"},
    {"fa": "کرمانشاه", "en": "Kermanshah"},
    {"fa": "همدان", "en": "Hamadan"},
    {"fa": "قزوین", "en": "Qazvin"},
    {"fa": "قم", "en": "Qom"},
    {"fa": "مرکزی", "en": "Markazi"},
    {"fa": "لرستان", "en": "Lorestan"},
    {"fa": "خوزستان", "en": "Khuzestan"},
    {"fa": "بوشهر", "en": "Bushehr"},
    {"fa": "هرمزگان", "en": "Hormozgan"},
    {"fa": "سیستان و بلوچستان", "en": "Sistan and Baluchestan"},
    {"fa": "کردستان", "en": "Kurdistan"},
    {"fa": "ایلام", "en": "Ilam"},
    {"fa": "کهگیلویه و بویراحمد", "en": "Kohgiluyeh and Boyer-Ahmad"},
    {"fa": "چهارمحال و بختیاری", "en": "Chaharmahal and Bakhtiari"},
    {"fa": "گیلان", "en": "Gilan"},
    {"fa": "مازندران", "en": "Mazandaran"},
    {"fa": "گلستان", "en": "Golestan"},
    {"fa": "سمنان", "en": "Semnan"},
    {"fa": "زنجان", "en": "Zanjan"},
    {"fa": "خراسان شمالی", "en": "North Khorasan"},
    {"fa": "خراسان جنوبی", "en": "South Khorasan"},
]


def tipax_search_queries(brand_query: str = "تیپاکس") -> list[str]:
    """Nationwide + per-province Google Maps queries for Tipax coverage."""
    brand = (brand_query or "تیپاکس").strip()
    queries = [brand, f"{brand} ایران"]
    for province in IRAN_PROVINCES:
        queries.append(f"{brand} {province['fa']}")
        queries.append(f"{brand} {province['en']}")
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def province_lookup() -> dict[str, tuple[str, str]]:
    """Needle → (city_hint, province) for address inference."""
    mapping: dict[str, tuple[str, str]] = {}
    for province in IRAN_PROVINCES:
        mapping[province["fa"]] = ("", province["fa"])
        mapping[province["en"].casefold()] = ("", province["en"])
    # Major cities
    cities = {
        "تهران": ("تهران", "تهران"),
        "tehran": ("Tehran", "Tehran"),
        "کرج": ("کرج", "البرز"),
        "karaj": ("Karaj", "Alborz"),
        "مشهد": ("مشهد", "خراسان رضوی"),
        "mashhad": ("Mashhad", "Razavi Khorasan"),
        "اصفهان": ("اصفهان", "اصفهان"),
        "isfahan": ("Isfahan", "Isfahan"),
        "شیراز": ("شیراز", "فارس"),
        "shiraz": ("Shiraz", "Fars"),
        "تبریز": ("تبریز", "آذربایجان شرقی"),
        "tabriz": ("Tabriz", "East Azerbaijan"),
        "اهواز": ("اهواز", "خوزستان"),
        "رشت": ("رشت", "گیلان"),
        "ساری": ("ساری", "مازندران"),
        "یزد": ("یزد", "یزد"),
        "کرمان": ("کرمان", "کرمان"),
        "ارومیه": ("ارومیه", "آذربایجان غربی"),
        "قم": ("قم", "قم"),
        "همدان": ("همدان", "همدان"),
        "کرمانشاه": ("کرمانشاه", "کرمانشاه"),
        "زاهدان": ("زاهدان", "سیستان و بلوچستان"),
        "بندرعباس": ("بندرعباس", "هرمزگان"),
        "بوشهر": ("بوشهر", "بوشهر"),
        "اردبیل": ("اردبیل", "اردبیل"),
        "سنندج": ("سنندج", "کردستان"),
        "خرم‌آباد": ("خرم‌آباد", "لرستان"),
        "اراک": ("اراک", "مرکزی"),
        "قزوین": ("قزوین", "قزوین"),
        "زنجان": ("زنجان", "زنجان"),
        "سمنان": ("سمنان", "سمنان"),
        "گرگان": ("گرگان", "گلستان"),
        "بجنورد": ("بجنورد", "خراسان شمالی"),
        "بیرجند": ("بیرجند", "خراسان جنوبی"),
        "یاسوج": ("یاسوج", "کهگیلویه و بویراحمد"),
        "شهرکرد": ("شهرکرد", "چهارمحال و بختیاری"),
        "ایلام": ("ایلام", "ایلام"),
    }
    mapping.update(cities)
    return mapping
