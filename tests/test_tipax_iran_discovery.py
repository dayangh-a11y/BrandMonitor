from __future__ import annotations

from collectors.iran_geo import IRAN_PROVINCES, tipax_search_queries
from collectors.google_maps.parser import GoogleMapsParser


def test_tipax_queries_cover_all_provinces():
    queries = tipax_search_queries("تیپاکس")
    assert len(IRAN_PROVINCES) == 31
    assert "تیپاکس" in queries
    for province in IRAN_PROVINCES:
        assert any(province["fa"] in q for q in queries)


def test_parser_infers_more_provinces():
    parser = GoogleMapsParser()
    city, province = parser.infer_city_province("اهواز، خوزستان، ایران")
    assert "خوزستان" in province or city
    city2, province2 = parser.infer_city_province("Rasht, Gilan, Iran")
    assert province2
