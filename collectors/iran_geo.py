"""Iran province/city/district helpers for nationwide Maps discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


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

# Brand / alias phrases used to surface hidden Maps listings.
TIPAX_DISCOVERY_ALIASES: list[str] = [
    "تیپاکس",
    "Tipax",
    "نمایندگی تیپاکس",
    "اکسس پوینت تیپاکس",
    "Tipax branch",
    "Tipax service point",
]

# Primary FA aliases for bulk city/province sweeps (keeps query budget sane).
TIPAX_CORE_ALIASES: list[str] = [
    "تیپاکس",
    "نمایندگی تیپاکس",
    "اکسس پوینت تیپاکس",
]

# Extra aliases for gap provinces / hidden-result probes.
TIPAX_GAP_ALIASES: list[str] = [
    "تیپاکس",
    "Tipax",
    "نمایندگی تیپاکس",
    "اکسس پوینت تیپاکس",
    "Tipax branch",
    "Tipax service point",
    "تیپاکس نمایندگی",
    "مرکز تیپاکس",
]

QueryLevel = Literal["nationwide", "province", "city", "district", "gap_probe"]


@dataclass(frozen=True)
class GeoCity:
    fa: str
    en: str
    districts: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoveryQuery:
    text: str
    level: QueryLevel
    province_fa: str = ""
    province_en: str = ""
    city_fa: str = ""
    city_en: str = ""
    district_fa: str = ""
    alias: str = ""
    priority: int = 100  # lower = earlier


# Major cities (+ districts for dense metros) keyed by province English name.
PROVINCE_CITIES: dict[str, list[GeoCity]] = {
    "Tehran": [
        GeoCity(
            "تهران",
            "Tehran",
            (
                "تجریش",
                "ونک",
                "سعادت آباد",
                "پونک",
                "جردن",
                "نیاوران",
                "پیروزی",
                "نارمک",
                "تهرانپارس",
                "شهرری",
                "اسلامشهر",
                "چیتگر",
                "آزادی",
                "انقلاب",
                "ولیعصر",
                "شریعتی",
                "صادقیه",
                "یوسف آباد",
                "ستارخان",
                "شهران",
            ),
        ),
        GeoCity("اسلامشهر", "Eslamshahr"),
        GeoCity("شهریار", "Shahriar"),
        GeoCity("قدس", "Qods"),
        GeoCity("ملارد", "Malard"),
        GeoCity("پاکدشت", "Pakdasht"),
        GeoCity("ورامین", "Varamin"),
        GeoCity("پردیس", "Pardis"),
        GeoCity("ری", "Rey"),
        GeoCity("دماوند", "Damavand"),
        GeoCity("فیروزکوه", "Firuzkuh"),
    ],
    "Alborz": [
        GeoCity(
            "کرج",
            "Karaj",
            ("گلشهر", "مهرشهر", "فردیس", "ماهدشت", "جهانشهر", "عظیمیه", "گوهردشت"),
        ),
        GeoCity("فردیس", "Fardis"),
        GeoCity("نظرآباد", "Nazarabad"),
        GeoCity("هشتگرد", "Hashtgerd"),
        GeoCity("طالقان", "Taleqan"),
        GeoCity("اشتهارد", "Eshtehard"),
    ],
    "Isfahan": [
        GeoCity(
            "اصفهان",
            "Isfahan",
            ("جلفا", "سی‌وسه‌پل", "خواجو", "ملک‌شهر", "خانه اصفهان", "خمینی‌شهر"),
        ),
        GeoCity("کاشان", "Kashan"),
        GeoCity("نجف‌آباد", "Najafabad"),
        GeoCity("خمینی‌شهر", "Khomeyni Shahr"),
        GeoCity("شاهین‌شهر", "Shahin Shahr"),
        GeoCity("فولادشهر", "Fooladshahr"),
        GeoCity("شهرضا", "Shahreza"),
        GeoCity("زرین‌شهر", "Zarrinshahr"),
        GeoCity("آران و بیدگل", "Aran va Bidgol"),
        GeoCity("نطنز", "Natanz"),
    ],
    "Fars": [
        GeoCity(
            "شیراز",
            "Shiraz",
            ("معالی‌آباد", "قصردشت", "ستارخان", "صدرا", "مرودشت", "زندییه"),
        ),
        GeoCity("مرودشت", "Marvdasht"),
        GeoCity("جهرم", "Jahrom"),
        GeoCity("فسا", "Fasa"),
        GeoCity("کازرون", "Kazerun"),
        GeoCity("لار", "Lar"),
        GeoCity("داراب", "Darab"),
        GeoCity("آباده", "Abadeh"),
        GeoCity("نی‌ریز", "Neyriz"),
    ],
    "Razavi Khorasan": [
        GeoCity(
            "مشهد",
            "Mashhad",
            ("احمدآباد", "سجاد", "هاشمیه", "وکیل‌آباد", "طرقبه", "قاسم‌آباد", "رضاشهر"),
        ),
        GeoCity("نیشابور", "Neyshabur"),
        GeoCity("سبزوار", "Sabzevar"),
        GeoCity("تربت حیدریه", "Torbat-e Heydarieh"),
        GeoCity("قوچان", "Quchan"),
        GeoCity("کاشمر", "Kashmar"),
        GeoCity("تربت جام", "Torbat-e Jam"),
        GeoCity("چناران", "Chenaran"),
        GeoCity("گناباد", "Gonabad"),
    ],
    "East Azerbaijan": [
        GeoCity(
            "تبریز",
            "Tabriz",
            ("ولیعصر", "آبرسان", "مارالان", "الهیه", "باغ‌میشه", "ولیعصر جنوبی"),
        ),
        GeoCity("مراغه", "Maragheh"),
        GeoCity("مرند", "Marand"),
        GeoCity("میانه", "Mianeh"),
        GeoCity("اهر", "Ahar"),
        GeoCity("بناب", "Bonab"),
        GeoCity("سراب", "Sarab"),
    ],
    "West Azerbaijan": [
        GeoCity("ارومیه", "Urmia", ("خیام", "انزلی", "مدرس", "شهرک")),
        GeoCity("خوی", "Khoy"),
        GeoCity("مهاباد", "Mahabad"),
        GeoCity("بوکان", "Bukan"),
        GeoCity("میاندوآب", "Miandoab"),
        GeoCity("سلماس", "Salmas"),
        GeoCity("پیرانشهر", "Piranshahr"),
    ],
    "Ardabil": [
        GeoCity("اردبیل", "Ardabil", ("محمودآباد", "ملک‌آباد", "آزادگان", "شهرک رضوان")),
        GeoCity("پارس‌آباد", "Parsabad"),
        GeoCity("خلخال", "Khalkhal"),
        GeoCity("مشگین‌شهر", "Meshginshahr"),
        GeoCity("گرمی", "Germi"),
        GeoCity("نمین", "Namin"),
        GeoCity("بیله‌سوار", "Bileh Savar"),
    ],
    "Yazd": [
        GeoCity("یزد", "Yazd", ("صفائیه", "آزادشهر", "امامشهر")),
        GeoCity("میبد", "Meybod"),
        GeoCity("اردکان", "Ardakan"),
        GeoCity("تفت", "Taft"),
        GeoCity("بافق", "Bafq"),
    ],
    "Kerman": [
        GeoCity("کرمان", "Kerman", ("آزادگان", "شهدا", "مشتاق")),
        GeoCity("رفسنجان", "Rafsanjan"),
        GeoCity("سیرجان", "Sirjan"),
        GeoCity("جیرفت", "Jiroft"),
        GeoCity("بم", "Bam"),
        GeoCity("زرند", "Zarand"),
        GeoCity("کهنوج", "Kahnuj"),
    ],
    "Kermanshah": [
        GeoCity("کرمانشاه", "Kermanshah", ("۲۲ بهمن", "آزادگان", "کشاورز", "الهیه", "دولت‌آباد")),
        GeoCity("اسلام‌آباد غرب", "Eslamabad-e Gharb"),
        GeoCity("سنقر", "Sonqor"),
        GeoCity("کنگاور", "Kangavar"),
        GeoCity("صحنه", "Sahneh"),
        GeoCity("جوانرود", "Javanrud"),
        GeoCity("پاوه", "Paveh"),
        GeoCity("سرپل ذهاب", "Sarpol-e Zahab"),
    ],
    "Hamadan": [
        GeoCity("همدان", "Hamadan"),
        GeoCity("ملایر", "Malayer"),
        GeoCity("نهاوند", "Nahavand"),
        GeoCity("اسدآباد", "Asadabad"),
        GeoCity("تویسرکان", "Tuyserkan"),
    ],
    "Qazvin": [
        GeoCity("قزوین", "Qazvin"),
        GeoCity("تاکستان", "Takestan"),
        GeoCity("آبیک", "Abyek"),
        GeoCity("الوند", "Alvand"),
        GeoCity("بوئین‌زهرا", "Buin Zahra"),
    ],
    "Qom": [
        GeoCity("قم", "Qom", ("پردیسان", "انقلاب", "دورشهر")),
    ],
    "Markazi": [
        GeoCity("اراک", "Arak"),
        GeoCity("ساوه", "Saveh"),
        GeoCity("خمین", "Khomein"),
        GeoCity("محلات", "Mahallat"),
        GeoCity("دلیجان", "Delijan"),
    ],
    "Lorestan": [
        GeoCity("خرم‌آباد", "Khorramabad"),
        GeoCity("بروجرد", "Borujerd"),
        GeoCity("دورود", "Dorud"),
        GeoCity("الیگودرز", "Aligudarz"),
        GeoCity("کوهدشت", "Kuhdasht"),
        GeoCity("نورآباد", "Nurabad"),
    ],
    "Khuzestan": [
        GeoCity("اهواز", "Ahvaz", ("کیانپارس", "گلستان", "زیتون", "پاداد")),
        GeoCity("آبادان", "Abadan"),
        GeoCity("دزفول", "Dezful"),
        GeoCity("ماهشهر", "Mahshahr"),
        GeoCity("اندیمشک", "Andimeshk"),
        GeoCity("خرمشهر", "Khorramshahr"),
        GeoCity("بهبهان", "Behbahan"),
        GeoCity("شوشتر", "Shushtar"),
        GeoCity("ایذه", "Izeh"),
    ],
    "Bushehr": [
        GeoCity("بوشهر", "Bushehr"),
        GeoCity("برازجان", "Borazjan"),
        GeoCity("کنگان", "Kangan"),
        GeoCity("گناوه", "Genaveh"),
        GeoCity("عسلویه", "Asaluyeh"),
    ],
    "Hormozgan": [
        GeoCity("بندرعباس", "Bandar Abbas"),
        GeoCity("میناب", "Minab"),
        GeoCity("قشم", "Qeshm"),
        GeoCity("کیش", "Kish"),
        GeoCity("بندر لنگه", "Bandar Lengeh"),
        GeoCity("حاجی‌آباد", "Hajiabad"),
    ],
    "Sistan and Baluchestan": [
        GeoCity("زاهدان", "Zahedan"),
        GeoCity("چابهار", "Chabahar"),
        GeoCity("ایرانشهر", "Iranshahr"),
        GeoCity("زابل", "Zabol"),
        GeoCity("خاش", "Khash"),
        GeoCity("سراوان", "Saravan"),
    ],
    "Kurdistan": [
        GeoCity("سنندج", "Sanandaj"),
        GeoCity("سقز", "Saqqez"),
        GeoCity("بانه", "Baneh"),
        GeoCity("مریوان", "Marivan"),
        GeoCity("قروه", "Qorveh"),
        GeoCity("بیجار", "Bijar"),
    ],
    "Ilam": [
        GeoCity("ایلام", "Ilam"),
        GeoCity("دهلران", "Dehloran"),
        GeoCity("ایوان", "Eyvan"),
        GeoCity("آبدانان", "Abdanan"),
        GeoCity("مهران", "Mehran"),
    ],
    "Kohgiluyeh and Boyer-Ahmad": [
        GeoCity("یاسوج", "Yasuj"),
        GeoCity("دوگنبدان", "Dogonbadan"),
        GeoCity("دهدشت", "Dehdasht"),
        GeoCity("سی‌سخت", "Sisakht"),
    ],
    "Chaharmahal and Bakhtiari": [
        GeoCity("شهرکرد", "Shahrekord"),
        GeoCity("بروجن", "Borujen"),
        GeoCity("فارسان", "Farsan"),
        GeoCity("لردگان", "Lordegan"),
        GeoCity("سامان", "Saman"),
    ],
    "Gilan": [
        GeoCity("رشت", "Rasht", ("گلسار", "فلکه گاز", "دیانتی")),
        GeoCity("انزلی", "Bandar Anzali"),
        GeoCity("لاهیجان", "Lahijan"),
        GeoCity("آستارا", "Astara"),
        GeoCity("رودسر", "Rudsar"),
        GeoCity("فومن", "Fuman"),
        GeoCity("صومعه‌سرا", "Sowme'eh Sara"),
        GeoCity("تالش", "Talesh"),
    ],
    "Mazandaran": [
        GeoCity("ساری", "Sari"),
        GeoCity("بابل", "Babol"),
        GeoCity("آمل", "Amol"),
        GeoCity("قائم‌شهر", "Qaem Shahr"),
        GeoCity("بابلسر", "Babolsar"),
        GeoCity("چالوس", "Chalus"),
        GeoCity("نوشهر", "Nowshahr"),
        GeoCity("تنکابن", "Tonekabon"),
        GeoCity("بهشهر", "Behshahr"),
        GeoCity("رامسر", "Ramsar"),
    ],
    "Golestan": [
        GeoCity("گرگان", "Gorgan"),
        GeoCity("گنبد کاووس", "Gonbad-e Kavus"),
        GeoCity("علی‌آباد", "Aliabad"),
        GeoCity("آق‌قلا", "Aqqala"),
        GeoCity("کردکوی", "Kordkuy"),
        GeoCity("بندر ترکمن", "Bandar Torkaman"),
    ],
    "Semnan": [
        GeoCity("سمنان", "Semnan"),
        GeoCity("شاهرود", "Shahrud"),
        GeoCity("دامغان", "Damghan"),
        GeoCity("گرمسار", "Garmsar"),
        GeoCity("ایوانکی", "Eyvanekey"),
    ],
    "Zanjan": [
        GeoCity("زنجان", "Zanjan"),
        GeoCity("ابهر", "Abhar"),
        GeoCity("خرمدره", "Khorramdarreh"),
        GeoCity("قیدار", "Qeydar"),
    ],
    "North Khorasan": [
        GeoCity("بجنورد", "Bojnurd"),
        GeoCity("شیروان", "Shirvan"),
        GeoCity("اسفراین", "Esfarayen"),
        GeoCity("جاجرم", "Jajarm"),
    ],
    "South Khorasan": [
        GeoCity("بیرجند", "Birjand"),
        GeoCity("قائن", "Qaen"),
        GeoCity("فردوس", "Ferdows"),
        GeoCity("طبس", "Tabas"),
        GeoCity("نهبندان", "Nehbandan"),
    ],
}


_LEVEL_RANK = {
    "district": 50,
    "city": 40,
    "gap_probe": 30,
    "province": 20,
    "nationwide": 10,
}


def _dedupe_queries(queries: list[DiscoveryQuery]) -> list[DiscoveryQuery]:
    """Deduplicate by text; keep the more specific geo level when phrases collide."""
    best: dict[str, DiscoveryQuery] = {}
    for q in queries:
        key = q.text.casefold().strip()
        if not key:
            continue
        prev = best.get(key)
        if prev is None:
            best[key] = q
            continue
        prev_rank = _LEVEL_RANK.get(prev.level, 0)
        new_rank = _LEVEL_RANK.get(q.level, 0)
        # Prefer richer geo tagging / more specific level.
        if new_rank > prev_rank:
            best[key] = q
        elif new_rank == prev_rank and (q.city_fa and not prev.city_fa):
            best[key] = q
    out = sorted(best.values(), key=lambda x: (x.priority, _LEVEL_RANK.get(x.level, 0) * -1, x.text))
    return out


def tipax_search_queries(
    brand_query: str = "تیپاکس",
    *,
    include_english: bool = False,
) -> list[str]:
    """Legacy nationwide + per-province queries (Phase Tipax Iran)."""
    brand = (brand_query or "تیپاکس").strip()
    queries = [brand, f"{brand} ایران"]
    for province in IRAN_PROVINCES:
        queries.append(f"{brand} {province['fa']}")
        if include_english:
            queries.append(f"{brand} {province['en']}")
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def build_discovery_queries(
    *,
    include_districts: bool = False,
    include_gap_probes: bool = True,
    gap_provinces: set[str] | None = None,
    aliases: list[str] | None = None,
    core_aliases: list[str] | None = None,
) -> list[DiscoveryQuery]:
    """
    Multi-level Tipax discovery plan:

    - nationwide aliases
    - province × core aliases
    - city × core aliases
    - optional pre-seeded districts for mega-cities
    - gap probes (all aliases + EN) for known-zero provinces
    """
    core = list(core_aliases or TIPAX_CORE_ALIASES)
    all_aliases = list(aliases or TIPAX_DISCOVERY_ALIASES)
    gaps = {g.casefold() for g in (gap_provinces or {"Ardabil", "Kermanshah"})}
    queries: list[DiscoveryQuery] = []

    for i, alias in enumerate(all_aliases):
        queries.append(
            DiscoveryQuery(
                text=alias,
                level="nationwide",
                alias=alias,
                priority=10 + i,
            )
        )
        queries.append(
            DiscoveryQuery(
                text=f"{alias} ایران",
                level="nationwide",
                alias=alias,
                priority=15 + i,
            )
        )

    for province in IRAN_PROVINCES:
        p_fa, p_en = province["fa"], province["en"]
        is_gap = p_en.casefold() in gaps
        alias_set = TIPAX_GAP_ALIASES if is_gap and include_gap_probes else core[:2]
        for i, alias in enumerate(alias_set):
            queries.append(
                DiscoveryQuery(
                    text=f"{alias} {p_fa}",
                    level="gap_probe" if is_gap else "province",
                    province_fa=p_fa,
                    province_en=p_en,
                    alias=alias,
                    priority=30 + i,
                )
            )
            if is_gap:
                queries.append(
                    DiscoveryQuery(
                        text=f"{alias} {p_en}",
                        level="gap_probe",
                        province_fa=p_fa,
                        province_en=p_en,
                        alias=alias,
                        priority=35 + i,
                    )
                )

        for city in PROVINCE_CITIES.get(p_en, []):
            if is_gap and include_gap_probes:
                city_aliases = TIPAX_GAP_ALIASES
            elif city.districts:
                # Dense metros: two FA aliases to surface hidden cards.
                city_aliases = core[:2]
            else:
                # One primary alias per city; districts expand adaptively if busy.
                city_aliases = core[:1]
            for i, alias in enumerate(city_aliases):
                queries.append(
                    DiscoveryQuery(
                        text=f"{alias} {city.fa}",
                        level="gap_probe" if is_gap else "city",
                        province_fa=p_fa,
                        province_en=p_en,
                        city_fa=city.fa,
                        city_en=city.en,
                        alias=alias,
                        priority=50 + i,
                    )
                )
            if include_districts and city.districts:
                for district in city.districts:
                    queries.append(
                        DiscoveryQuery(
                            text=f"{core[0]} {city.fa} {district}",
                            level="district",
                            province_fa=p_fa,
                            province_en=p_en,
                            city_fa=city.fa,
                            city_en=city.en,
                            district_fa=district,
                            alias=core[0],
                            priority=80,
                        )
                    )

    return _dedupe_queries(queries)


def district_expansion_queries(
    *,
    province_fa: str,
    province_en: str,
    city_fa: str,
    city_en: str,
    districts: tuple[str, ...] | list[str],
    aliases: list[str] | None = None,
) -> list[DiscoveryQuery]:
    """Extra district queries when a city search returns many results."""
    alias_list = list(aliases or TIPAX_CORE_ALIASES[:2])
    queries: list[DiscoveryQuery] = []
    for district in districts:
        for i, alias in enumerate(alias_list):
            queries.append(
                DiscoveryQuery(
                    text=f"{alias} {city_fa} {district}",
                    level="district",
                    province_fa=province_fa,
                    province_en=province_en,
                    city_fa=city_fa,
                    city_en=city_en,
                    district_fa=district,
                    alias=alias,
                    priority=70 + i,
                )
            )
            # Phrase variation: district first (helps Maps ranking diversity).
            queries.append(
                DiscoveryQuery(
                    text=f"{alias} {district} {city_fa}",
                    level="district",
                    province_fa=province_fa,
                    province_en=province_en,
                    city_fa=city_fa,
                    city_en=city_en,
                    district_fa=district,
                    alias=alias,
                    priority=75 + i,
                )
            )
    return _dedupe_queries(queries)


def cities_for_province(province_en: str) -> list[GeoCity]:
    return list(PROVINCE_CITIES.get(province_en, []))


def province_lookup() -> dict[str, tuple[str, str]]:
    """Needle → (city_hint, province) for address inference."""
    mapping: dict[str, tuple[str, str]] = {}
    for province in IRAN_PROVINCES:
        mapping[province["fa"]] = ("", province["fa"])
        mapping[province["en"].casefold()] = ("", province["en"])
    for province_en, cities in PROVINCE_CITIES.items():
        province_fa = next(p["fa"] for p in IRAN_PROVINCES if p["en"] == province_en)
        for city in cities:
            mapping[city.fa] = (city.fa, province_fa)
            mapping[city.en.casefold()] = (city.en, province_en)
            for district in city.districts:
                mapping[district] = (city.fa, province_fa)
    return mapping
