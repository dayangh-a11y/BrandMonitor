"""Smoke tests for Postal Intelligence interactive demo AI layer."""

from __future__ import annotations

from pathlib import Path

import pytest

DB = Path("data/postal_intelligence.db")


@pytest.mark.skipif(not DB.exists(), reason="postal_intelligence.db missing")
def test_demo_ai_search_and_compare():
    from postal.demo_ai import DemoAI
    from postal.demo_data import IntelDemoData

    data = IntelDemoData(str(DB))
    data.connect()
    ai = DemoAI(data)
    snap = data.snapshot()
    assert snap["companies"]
    assert snap["totals"]["reviews"] > 0

    home = ai.home_insights()
    assert home
    assert "data_sources" in home[0]
    assert "confidence_level" in home[0]
    assert "last_updated" in home[0]

    tipax = data.company_by_slug("tipax")
    chapar = data.company_by_slug("chapar")
    assert tipax and chapar
    summary = ai.company_executive_summary(tipax)
    assert summary["text"]
    assert "postal_score_v1" in summary["text"] or summary["insufficient_evidence"]

    cmp = ai.compare("tipax", "chapar")
    assert "insights" in cmp
    assert cmp["summary"]["data_sources"]

    sat = ai.search("Which company has the best customer satisfaction?")
    assert sat["answer"]["text"]
    assert sat["intent"] == "best_satisfaction"

    why = ai.search("Why is Tipax ranked higher than Chapar?")
    assert why["intent"] == "compare"
    assert "Chapar" in why["answer"]["text"] or "Tipax" in why["answer"]["text"]

    prov = ai.search("Which provinces have the highest complaint rate?")
    assert prov["intent"] == "province_complaints"
    assert prov["answer"]["data_sources"]
