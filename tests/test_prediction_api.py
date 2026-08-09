"""API tests for freeze-backed prediction HTTP layer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURE_DIR = Path("tests/fixtures/prediction_api")
FIXTURE_DS = FIXTURE_DIR / "observations_fixture.jsonl.gz"
IDS = json.loads((FIXTURE_DIR / "ids.json").read_text(encoding="utf-8"))


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(FIXTURE_DS.resolve()))
    monkeypatch.setenv("PREDICTION_FREEZE_PATH", "data/prediction_foundation/freezes/LATEST.json")
    monkeypatch.setenv("PREDICTION_VERIFY_FREEZE", "false")
    monkeypatch.setenv("PREDICTION_DEFAULT_BASELINE", "A")
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
