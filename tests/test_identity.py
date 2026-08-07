"""Horse Identity Resolution Engine tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.database import init_db, reset_engine, session_scope
from src.identity import (
    HorseQuery,
    build_horse_identity,
    duplicate_merge_report,
    name_similarity,
    normalize_name,
    resolve_horse,
    resolve_horse_id,
)
from src.identity.models import IdHorse, IdHorseLink
from src.identity.normalize import normalize_persian_text, normalize_sex
from src.identity.profile import HorseProfile
from src.identity.score import score_profiles
from src.warehouse.models import WhHorse, WhOwner, WhRace, WhRaceResult, WhTrainer


@pytest.fixture()
def db_url(tmp_path) -> str:
    reset_engine()
    url = f"sqlite:///{tmp_path / 'identity.db'}"
    init_db(url=url)
    yield url
    reset_engine()


def test_persian_normalization_zw_and_arabic_letters() -> None:
    a = normalize_name("باد\u200cپا")
    b = normalize_name("بادپا")
    assert a == b == "بادپا"

    assert normalize_name("علي") == normalize_name("علی")
    assert "  " not in normalize_persian_text("a   b")
    assert name_similarity("هج لایک", "هج‌لایک") >= 0.99
    assert normalize_sex("نر") == "male"
    assert normalize_sex("ماده") == "female"
    assert normalize_sex("اخته") == "gelding"


def test_never_exact_raw_string_required_for_match() -> None:
    left = HorseProfile(
        warehouse_horse_id=1,
        name="پرنس آف اسپید",
        sex="نر",
        age_years=3,
        sire="وان من باند",
        dam="سرخان هج",
        owners=["باشگاه اسب صدر"],
        trainers=["محمد اعظمی"],
    )
    right = HorseProfile(
        warehouse_horse_id=2,
        name="پرنس‌آف‌اسپيد",  # ZWNJ + Arabic yeh
        sex="نر",
        age_years=3,
        sire="وان من باند",
        dam="سرخان هج",
        owners=["باشگاه اسب صدر"],
        trainers=["محمد اعظمی"],
    )
    result = score_profiles(left, right)
    assert result.total_score >= 0.88
    assert result.decision == "auto_merge"
    assert left.name != right.name


def test_sex_conflict_suppresses_merge() -> None:
    left = HorseProfile(warehouse_horse_id=1, name="بادپا", sex="نر", age_years=3)
    right = HorseProfile(warehouse_horse_id=2, name="بادپا", sex="ماده", age_years=3)
    result = score_profiles(left, right)
    assert result.decision != "auto_merge"


def test_birth_year_and_continuity_support_cross_city_merge() -> None:
    from datetime import date

    left = HorseProfile(
        warehouse_horse_id=1,
        name="پرنس آف اسپید",
        sex="نر",
        birth_year=2021,
        sire="وان من باند",
        dam="سرخان هج",
        owners=["باشگاه اسب صدر"],
        trainers=["محمد اعظمی"],
        race_dates=[date(2024, 1, 10), date(2024, 2, 5)],
        racecourse_codes=["tehran"],
    )
    right = HorseProfile(
        warehouse_horse_id=2,
        name="پرنس‌آف‌اسپيد",
        sex="نر",
        birth_year=2021,
        sire="وان من باند",
        dam="سرخان هج",
        owners=["باشگاه اسب صدر"],
        trainers=["محمد اعظمی"],
        race_dates=[date(2024, 3, 1), date(2024, 4, 12)],
        racecourse_codes=["gonbad-kavous"],
    )
    result = score_profiles(left, right)
    assert result.decision == "auto_merge"
    signals = {s.signal: s for s in result.signals}
    assert signals["birth_year"].score == 1.0
    assert signals["continuity"].score is not None
    assert signals["continuity"].score >= 0.85


def test_national_continuity_merges_despite_owner_drift() -> None:
    from datetime import date

    left = HorseProfile(
        warehouse_horse_id=1,
        name="پالونیا",
        sex="ماده",
        birth_year=2019,
        owners=["مالک الف"],
        trainers=["مربی الف"],
        race_dates=[date(2024, 1, 10), date(2024, 2, 1)],
        racecourse_codes=["tehran"],
    )
    right = HorseProfile(
        warehouse_horse_id=2,
        name="پالونیا",
        sex="ماده",
        birth_year=2020,  # ±1 year still accepted by national rule
        owners=["مالک ب"],
        trainers=["مربی ب"],
        race_dates=[date(2024, 3, 5), date(2024, 4, 1)],
        racecourse_codes=["gonbad-kavous"],
    )
    result = score_profiles(left, right)
    assert result.decision == "auto_merge"
    assert any(s.signal == "national_continuity_rule" for s in result.signals)

def test_same_day_disjoint_cities_blocks_auto_merge() -> None:
    from datetime import date

    left = HorseProfile(
        warehouse_horse_id=1,
        name="بادپا",
        sex="نر",
        birth_year=2020,
        race_dates=[date(2024, 5, 1)],
        racecourse_codes=["tehran"],
    )
    right = HorseProfile(
        warehouse_horse_id=2,
        name="بادپا",
        sex="نر",
        birth_year=2020,
        race_dates=[date(2024, 5, 1)],
        racecourse_codes=["yazd"],
    )
    result = score_profiles(left, right)
    assert result.decision != "auto_merge"


def test_build_assigns_permanent_ids_and_merges(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        race = WhRace(
            source="test",
            source_race_id="r1",
            name="t",
            track="گنبدکاووس",
            racecourse_code="gonbad-kavous",
        )
        session.add(race)
        session.flush()
        h1 = WhHorse(source="test", source_horse_id="a1", name="تریموف", sex="نر")
        h2 = WhHorse(source="test", source_horse_id="a2", name="تريموف", sex="نر")
        h3 = WhHorse(source="test", source_horse_id="b1", name="دل والی", sex="نر")
        session.add_all([h1, h2, h3])
        session.flush()
        owner = WhOwner(name="گل محمد کلته")
        trainer = WhTrainer(name="بهمن اونق")
        session.add_all([owner, trainer])
        session.flush()
        session.add_all(
            [
                WhRaceResult(
                    race_id=race.id,
                    horse_id=h1.id,
                    owner_id=owner.id,
                    trainer_id=trainer.id,
                    number=1,
                ),
                WhRaceResult(
                    race_id=race.id,
                    horse_id=h2.id,
                    owner_id=owner.id,
                    trainer_id=trainer.id,
                    number=2,
                ),
            ]
        )
        session.flush()
        stats = build_horse_identity(session)
        assert stats["profiles_loaded"] == 3
        assert stats["permanent_horse_ids"] >= 2

        links = list(session.scalars(select(IdHorseLink)).all())
        assert len(links) == 3
        id_by_wh = {lk.warehouse_horse_id: lk.horse_id for lk in links}
        assert set(id_by_wh) == {h1.id, h2.id, h3.id}
        # Arabic/Persian yeh variants should auto-merge
        assert id_by_wh[h1.id] == id_by_wh[h2.id]
        assert id_by_wh[h1.id] != id_by_wh[h3.id]

        hid = resolve_horse_id(
            session,
            name="تریموف",
            sex="نر",
            owner="گل محمد کلته",
            trainer="بهمن اونق",
        )
        assert hid is not None
        assert session.get(IdHorse, hid) is not None

        report = duplicate_merge_report(session)
        assert report["summary"]["permanent_horse_ids"] >= 2
        assert report["summary"]["duplicate_clusters"] >= 1


def test_resolve_returns_horse_id_not_name_key(db_url: str) -> None:
    with session_scope(url=db_url) as session:
        session.add(
            WhRace(
                source="test",
                source_race_id="r2",
                track="گنبدکاووس",
                racecourse_code="gonbad-kavous",
            )
        )
        h = WhHorse(source="test", source_horse_id="x1", name="هج لایک", sex="نر")
        session.add(h)
        session.flush()
        build_horse_identity(session)
        hits = resolve_horse(session, HorseQuery(name="هج‌لايك", sex="نر"), limit=3)
        assert hits
        assert isinstance(hits[0].horse_id, int)
        assert hits[0].horse_id > 0
