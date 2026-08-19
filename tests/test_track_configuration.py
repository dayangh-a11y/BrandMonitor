"""Track Configuration (finishing straight length) tests."""

from __future__ import annotations

from src.racecourses.track_config import (
    categorize_straight_length,
    comparable_on_straight,
    get_track_configuration,
    propose_straight_length_update,
    resolve_track_configuration,
    straight_length_features,
)


def test_categories() -> None:
    assert categorize_straight_length(138) == "Short"
    assert categorize_straight_length(199) == "Short"
    assert categorize_straight_length(200) == "Medium"
    assert categorize_straight_length(275) == "Medium"
    assert categorize_straight_length(276) == "Long"
    assert categorize_straight_length(388) == "Long"


def test_all_seeded_tracks() -> None:
    expected = {
        "mashhad": 388,
        "aq-qala": 321,
        "tehran": 278,
        "kish": 276,
        "gonbad-kavous": 263,
        "bandar-torkaman": 244,
        "ahvaz": 221,
        "yazd": 138,
    }
    for tid, meters in expected.items():
        cfg = get_track_configuration(tid)
        assert cfg is not None
        assert cfg.straight_length_m == meters
        assert cfg.source == "visual_track_diagram"
        assert cfg.source_confidence == 0.95


def test_resolve_by_code_and_city() -> None:
    assert resolve_track_configuration(racecourse_code="gonbad-kavous").straight_length_m == 263
    assert resolve_track_configuration(track_name="گنبدکاووس").track_id == "gonbad-kavous"
    assert resolve_track_configuration(city="تهران").track_name == "نوروزآباد تهران"
    assert resolve_track_configuration(track_name="ثامن مشهد").track_id == "mashhad"
    assert resolve_track_configuration(track_name="نوروزآباد تهران").track_id == "tehran"
    assert resolve_track_configuration(track_name="نیرو اهواز").track_id == "ahvaz"
    assert resolve_track_configuration(track_name="صفائیه یزد").straight_length_m == 138


def test_no_guess_unknown_or_unconfigured() -> None:
    assert resolve_track_configuration(track_name="شهر فرضی ناشناس") is None
    assert resolve_track_configuration(racecourse_code="ir-unknown") is None
    # Anbar Alum is a known registry city but has no straight config
    assert resolve_track_configuration(track_name="انبارآلوم") is None
    feats = straight_length_features(track_name="انبارآلوم")
    assert feats["track_config_applied"] is False
    assert feats["straight_length_m"] is None


def test_conflict_does_not_apply() -> None:
    report = propose_straight_length_update(
        "yazd",
        999,
        source="other_diagram",
        source_confidence=0.5,
    )
    assert report["status"] == "conflict_reported"
    assert report["applied"] is False
    assert get_track_configuration("yazd").straight_length_m == 138


def test_comparable_on_straight() -> None:
    a = get_track_configuration("kish")  # 276 Long
    b = get_track_configuration("tehran")  # 278 Long
    c = get_track_configuration("yazd")  # 138 Short
    assert comparable_on_straight(a, b) is True
    assert comparable_on_straight(a, c) is False
