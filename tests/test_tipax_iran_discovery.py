from __future__ import annotations

from collectors.discovery.engine import (
    NationwideDiscoveryEngine,
    build_zero_province_investigation,
)
from collectors.iran_geo import (
    IRAN_PROVINCES,
    PROVINCE_CITIES,
    TIPAX_DISCOVERY_ALIASES,
    build_discovery_queries,
    district_expansion_queries,
    tipax_search_queries,
)
from collectors.crawl_models import CrawlConfig
from collectors.google_maps.parser import GoogleMapsParser


def test_tipax_queries_cover_all_provinces():
    queries = tipax_search_queries("تیپاکس")
    assert len(IRAN_PROVINCES) == 31
    assert "تیپاکس" in queries
    # FA-only by default: brand + Iran + 31 provinces
    assert len(queries) == 33
    for province in IRAN_PROVINCES:
        assert any(province["fa"] in q for q in queries)
    wide = tipax_search_queries("تیپاکس", include_english=True)
    assert len(wide) > len(queries)


def test_parser_infers_more_provinces():
    parser = GoogleMapsParser()
    city, province = parser.infer_city_province("اهواز، خوزستان، ایران")
    assert "خوزستان" in province or city
    city2, province2 = parser.infer_city_province("Rasht, Gilan, Iran")
    assert province2


def test_phase10_discovery_plan_is_multi_level():
    plan = build_discovery_queries(include_districts=False, include_gap_probes=True)
    levels = {q.level for q in plan}
    assert "nationwide" in levels
    assert "province" in levels
    assert "city" in levels
    assert "gap_probe" in levels
    texts = {q.text for q in plan}
    for alias in TIPAX_DISCOVERY_ALIASES:
        assert alias in texts
    # Every province has at least one city in the atlas.
    assert len(PROVINCE_CITIES) == 31
    for province in IRAN_PROVINCES:
        assert province["en"] in PROVINCE_CITIES
        assert PROVINCE_CITIES[province["en"]]
    # Gap provinces get English probes.
    assert any(
        q.province_en == "Ardabil" and "Ardabil" in q.text for q in plan
    )
    assert any(
        q.province_en == "Kermanshah" and "Kermanshah" in q.text for q in plan
    )
    # City coverage includes capitals.
    assert any(q.city_fa == "تهران" for q in plan)
    assert any(q.city_fa == "کرمانشاه" for q in plan)
    assert any(q.city_fa == "اردبیل" for q in plan)


def test_district_expansion_varies_phrases():
    extras = district_expansion_queries(
        province_fa="تهران",
        province_en="Tehran",
        city_fa="تهران",
        city_en="Tehran",
        districts=("ونک", "نیاوران"),
    )
    texts = [q.text for q in extras]
    assert any(t.endswith("ونک") or "ونک تهران" in t or "تهران ونک" in t for t in texts)
    assert any("نیاوران" in t for t in texts)
    assert all(q.level == "district" for q in extras)


def test_discovery_only_config_flag():
    cfg = CrawlConfig(company_name="Tipax", discovery_only=True)
    assert cfg.discovery_only is True


def test_zero_investigation_builder_empty_when_covered():
    engine = NationwideDiscoveryEngine(source=object())
    # Minimal synthetic result via engine types
    from collectors.discovery.engine import DiscoveryRunResult, ProvinceCoverage

    provinces = [
        ProvinceCoverage(
            province_en=p["en"],
            province_fa=p["fa"],
            branches_discovered=1,
            queries_executed=1,
        )
        for p in IRAN_PROVINCES
    ]
    result = DiscoveryRunResult(
        generated_at="now",
        company="Tipax",
        queries_planned=10,
        queries_executed=10,
        unique_branches=31,
        new_branches_vs_baseline=0,
        baseline_unique=31,
        district_expansions=0,
        provinces=provinces,
        zero_provinces=[],
    )
    inv = build_zero_province_investigation(result)
    assert inv["provinces"] == []
