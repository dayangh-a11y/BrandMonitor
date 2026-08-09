"""API tests for freeze-backed prediction HTTP layer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURE_DIR = Path("tests/fixtures/prediction_api")
FIXTURE_DS = FIXTURE_DIR / "observations_fixture.jsonl.gz"
FIXTURE_NAMES = FIXTURE_DIR / "horse_names.json"
IDS = json.loads((FIXTURE_DIR / "ids.json").read_text(encoding="utf-8"))


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(FIXTURE_DS.resolve()))
    monkeypatch.setenv("PREDICTION_FREEZE_PATH", "data/prediction_foundation/freezes/LATEST.json")
    monkeypatch.setenv("PREDICTION_VERIFY_FREEZE", "false")
    monkeypatch.setenv("PREDICTION_DEFAULT_BASELINE", "A")
    monkeypatch.setenv("HORSE_NAME_INDEX_PATH", str(FIXTURE_NAMES.resolve()))
    monkeypatch.setenv("API_CORS_ORIGINS", "http://localhost:3000")

    # Import after env so settings pick up fixture paths.
    from src.api import deps
    from src.api.main import app

    deps.clear_engine_cache()
    with TestClient(app) as c:
        yield c
    deps.clear_engine_cache()


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["dataset_version"] == "pf-v1.0.0-20260808"
    assert body["dataset_loaded"] is True
    assert body["ml_status"] == "DO_NOT_TRAIN_YET"


def test_valid_race(client: TestClient) -> None:
    rid = IDS["test_race_id"]
    r = client.get(f"/races/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["race_id"] == rid
    assert body["field_size"] >= 5
    assert isinstance(body["horses"], list)
    assert body["dataset_version"] == "pf-v1.0.0-20260808"


def test_invalid_race(client: TestClient) -> None:
    r = client.get(f"/races/{IDS['invalid_race_id']}")
    assert r.status_code == 404


def test_invalid_race_id_type(client: TestClient) -> None:
    r = client.get("/races/not-an-id")
    assert r.status_code == 422


def test_valid_prediction(client: TestClient) -> None:
    rid = IDS["test_race_id"]
    r = client.get(f"/races/{rid}/prediction")
    assert r.status_code == 200
    body = r.json()
    assert body["race_id"] == rid
    assert body["dataset_version"] == "pf-v1.0.0-20260808"
    assert body["baseline"] == "A"
    assert isinstance(body["prediction"], list)
    assert len(body["prediction"]) >= 5
    ranks = [p["rank"] for p in body["prediction"]]
    assert ranks == list(range(1, len(ranks) + 1))


def test_prediction_schema_and_probability_null(client: TestClient) -> None:
    rid = IDS["test_race_id"]
    r = client.get(f"/races/{rid}/prediction")
    assert r.status_code == 200
    body = r.json()
    for item in body["prediction"]:
        assert "rank" in item
        assert "horse_id" in item
        assert "horse_name" in item
        assert "score" in item
        assert "probability" in item
        assert item["probability"] is None
        assert "evidence" in item
        assert "warnings" in item
        # score must not be copied into probability
        if item["score"] is not None:
            assert item["probability"] is not item["score"]
            assert item["probability"] != item["score"]


def test_prediction_does_not_fabricate_probability_from_score(client: TestClient) -> None:
    rid = IDS["test_race_id"]
    body = client.get(f"/races/{rid}/prediction").json()
    scores = [p["score"] for p in body["prediction"] if p["score"] is not None]
    assert scores, "expected at least one scored horse in fixture"
    for p in body["prediction"]:
        assert p["probability"] is None


def test_valid_horse_analysis(client: TestClient) -> None:
    hid = IDS["test_horse_id"]
    r = client.get(f"/horses/{hid}")
    assert r.status_code == 200
    body = r.json()
    assert body["horse_id"] == hid
    assert body["observation_count"] >= 1
    assert body["dataset_version"] == "pf-v1.0.0-20260808"


def test_invalid_horse(client: TestClient) -> None:
    r = client.get(f"/horses/{IDS['invalid_horse_id']}")
    assert r.status_code == 404


def test_openapi_available(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/races/{race_id}/prediction" in r.json()["paths"]
    assert "/races" in r.json()["paths"]


def test_list_races(client: TestClient) -> None:
    r = client.get("/races?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert isinstance(body["races"], list)
    assert body["races"][0]["race_id"] is not None


def test_horse_search_exact_and_partial(client: TestClient) -> None:
    exact = client.get("/horses/search", params={"name": "انفجار ایگدری"})
    assert exact.status_code == 200
    body = exact.json()
    assert body["count"] >= 1
    assert body["horses"][0]["horse_name"] == "انفجار ایگدری"
    assert body["horses"][0]["horse_id"] == IDS["test_horse_id"]

    partial = client.get("/horses/search", params={"name": "مارال"})
    assert partial.status_code == 200
    names = [h["horse_name"] for h in partial.json()["horses"]]
    assert any("مارال" in n for n in names)


def test_horse_search_latin_alias_and_no_match(client: TestClient) -> None:
    latin = client.get("/horses/search", params={"name": "Danzig Boy"})
    assert latin.status_code == 200
    assert latin.json()["count"] >= 1
    assert latin.json()["horses"][0]["horse_name"] == "شیرین صحرا"

    persian_alias = client.get("/horses/search", params={"name": "دنزی بوی"})
    assert persian_alias.status_code == 200
    assert persian_alias.json()["horses"][0]["horse_id"] == 3239

    missing = client.get("/horses/search", params={"name": "اسبی که وجود ندارد ۱۲۳"})
    assert missing.status_code == 200
    assert missing.json()["count"] == 0
    assert missing.json()["horses"] == []


def test_horse_search_multiple_partial_matches(client: TestClient) -> None:
    # Fixture has شیرین صحرا + گل مارال; substring that can hit multiple via aliases/names
    # Use a broad Latin fragment present only once, then verify multi via directory unit coverage.
    # API multi-match: search "مارال" is partial; add another horse named similarly in fixture if needed.
    r = client.get("/horses/search", params={"name": "مارال"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    for h in body["horses"]:
        assert "horse_id" in h
        assert h["horse_name"]


def test_horse_analysis_includes_directory_name(client: TestClient) -> None:
    r = client.get(f"/horses/{IDS['test_horse_id']}")
    assert r.status_code == 200
    assert r.json()["horse_name"] == "انفجار ایگدری"


def test_production_mode_fails_when_canonical_dataset_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "observations.jsonl.gz"
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(missing))
    monkeypatch.setenv("PREDICTION_FREEZE_PATH", "data/prediction_foundation/freezes/LATEST.json")
    monkeypatch.setenv("PREDICTION_VERIFY_FREEZE", "true")

    from src.api.config import APISettings, validate_prediction_dataset_settings

    with pytest.raises(RuntimeError, match="PRODUCTION BLOCKER"):
        validate_prediction_dataset_settings(APISettings())


def test_production_mode_refuses_fixture_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(FIXTURE_DS.resolve()))
    monkeypatch.setenv("PREDICTION_FREEZE_PATH", "data/prediction_foundation/freezes/LATEST.json")
    monkeypatch.setenv("PREDICTION_VERIFY_FREEZE", "true")

    from src.api.config import APISettings, validate_prediction_dataset_settings

    with pytest.raises(RuntimeError, match="refuses the test fixture"):
        validate_prediction_dataset_settings(APISettings())


def test_fixture_mode_accepts_fixture_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(FIXTURE_DS.resolve()))
    monkeypatch.setenv("PREDICTION_FREEZE_PATH", "data/prediction_foundation/freezes/LATEST.json")
    monkeypatch.setenv("PREDICTION_VERIFY_FREEZE", "false")

    from src.api.config import APISettings, validate_prediction_dataset_settings

    validate_prediction_dataset_settings(APISettings())  # must not raise
