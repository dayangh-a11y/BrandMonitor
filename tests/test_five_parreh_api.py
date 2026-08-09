"""HTTP tests for Five-Parreh combinations endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURE_DS = Path("tests/fixtures/prediction_api/observations_fixture.jsonl.gz")


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # App lifespan still validates prediction dataset settings.
    monkeypatch.setenv("PREDICTION_DATASET_PATH", str(FIXTURE_DS.resolve()))
    monkeypatch.setenv("PREDICTION_FREEZE_PATH", "data/prediction_foundation/freezes/LATEST.json")
    monkeypatch.setenv("PREDICTION_VERIFY_FREEZE", "false")

    from src.api import deps
    from src.api.main import app

    deps.clear_engine_cache()
    with TestClient(app) as c:
        yield c
    deps.clear_engine_cache()


def _body(counts: list[int], **extra):
    races = []
    n = 0
    for i, c in enumerate(counts, start=1):
        horses = [f"H{n + j}" for j in range(c)]
        n += c
        races.append({"race_id": f"R{i}", "horses": horses})
    payload = {"races": races, "price_per_combination": 10_000}
    payload.update(extra)
    return payload


def test_post_combinations_3x3(client: TestClient) -> None:
    r = client.post("/five-parreh/combinations", json=_body([3, 3, 3, 3, 3]))
    assert r.status_code == 200
    body = r.json()
    assert body["total_combinations"] == 243
    assert body["total_cost"] == 2_430_000
    assert body["selections_per_race"] == [3, 3, 3, 3, 3]
    assert len(body["combinations"]) == 243


def test_post_combinations_validation(client: TestClient) -> None:
    bad = _body([2, 2, 2, 2, 2])
    bad["races"] = bad["races"][:4]
    r = client.post("/five-parreh/combinations", json=bad)
    assert r.status_code == 422


def test_post_combinations_omits_when_over_cap(client: TestClient) -> None:
    r = client.post(
        "/five-parreh/combinations",
        json=_body([3, 3, 3, 3, 3], max_combinations_in_response=10),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_combinations"] == 243
    assert body["total_cost"] == 2_430_000
    assert body["combinations"] is None
    assert body["combinations_omitted"] is True
