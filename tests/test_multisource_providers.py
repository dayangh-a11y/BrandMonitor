from collectors.normalize.text import normalize_persian, normalize_rating, is_spam_or_empty
from collectors.providers import build_provider, list_providers
from collectors.multisource.dedupe_cross import cross_source_dedupe
from collectors.providers.base import UnifiedReview


def test_providers_registered():
    ids = {p["source_id"] for p in list_providers()}
    assert {"google_maps", "neshan", "balad", "cafebazaar", "myket"} <= ids


def test_neshan_manual_import():
    p = build_provider("neshan")
    rows = p.collect("Tipax")
    assert p.healthcheck()["ready"] is True
    assert any(r.source == "neshan" for r in rows)


def test_normalize_and_spam():
    assert "ی" in normalize_persian("ي")
    assert normalize_rating(80) == 4.0
    assert is_spam_or_empty("") is True


def test_cross_source_dedupe_merges():
    a = UnifiedReview(source="neshan", brand="Tipax", branch="Vanak", city="تهران", rating=2, review="تاخیر زیاد در تحویل", review_date="2026-06-01", reviewer="u1")
    b = UnifiedReview(source="balad", brand="Tipax", branch="Vanak", city="تهران", rating=2, review="تاخیر زیاد در تحویل!", review_date="2026-06-01", reviewer="u2")
    kept, dropped = cross_source_dedupe([a, b], text_threshold=0.9)
    assert dropped >= 1
    assert len(kept) == 1
    assert "balad" in (kept[0].metadata.get("also_seen_on") or []) or kept[0].source in {"neshan", "balad"}
