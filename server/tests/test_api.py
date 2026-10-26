"""API contract and local persistence tests; run with `uv run pytest`."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from guide_api.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(tmp_path / "state.sqlite3")) as test_client:
        yield test_client


def start_session(client: TestClient) -> dict:
    response = client.post("/sessions", json={"guide_id": "demo-aircon"})
    assert response.status_code == 201
    return response.json()


def test_catalog_and_guide_are_honestly_demo(client: TestClient):
    catalog = client.get("/catalog").json()
    assert catalog["demo"] is True
    assert catalog["real_product_assets_registered"] is False
    guide = client.get("/guides/demo-aircon").json()
    assert guide["demo"] is True
    assert [step["id"] for step in guide["steps"]] == ["power", "mode", "temperature"]
    assert guide["target_id"] == "original-demo-remote-v1"
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_order_and_unknown_identifiers(client: TestClient):
    assert client.get("/guides/missing").status_code == 404
    assert client.get("/models/samsung-unknown").status_code == 404
    assert client.post("/sessions", json={"guide_id": "missing"}).status_code == 404
    session = start_session(client)
    event = {"event_id": "event-001", "step_id": "temperature", "source": "manual"}
    assert client.post(f"/sessions/{session['id']}/events", json=event).status_code == 409
    assert client.get(f"/sessions/{session['id']}").json()["step_index"] == 0


def test_duplicate_event_is_idempotent_and_collision_rejected(client: TestClient):
    session = start_session(client)
    url = f"/sessions/{session['id']}/events"
    event = {"event_id": "event-001", "step_id": "power", "source": "manual"}
    first = client.post(url, json=event)
    second = client.post(url, json=event)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    conflict = {**event, "step_id": "mode"}
    assert client.post(url, json=conflict).status_code == 409
    assert client.get(f"/sessions/{session['id']}").json()["step_index"] == 1


def test_local_persistence_survives_app_recreation(tmp_path: Path):
    database = tmp_path / "persistent.sqlite3"
    with TestClient(create_app(database)) as first:
        session = start_session(first)
        first.post(
            f"/sessions/{session['id']}/events",
            json={"event_id": "saved-001", "step_id": "power", "source": "manual"},
        )
    with TestClient(create_app(database)) as second:
        assert second.get(f"/sessions/{session['id']}").json()["step_index"] == 1


def test_finished_session_cannot_advance(client: TestClient):
    session = start_session(client)
    url = f"/sessions/{session['id']}/events"
    for index, step in enumerate(("power", "mode", "temperature")):
        result = client.post(
            url, json={"event_id": f"finish-{index}", "step_id": step, "source": "manual"}
        )
        assert result.status_code == 200
    assert result.json()["finished"] is True
    assert client.post(
        url, json={"event_id": "extra-001", "step_id": "temperature", "source": "manual"}
    ).status_code == 409


def test_parallel_retries_do_not_skip(client: TestClient):
    session = start_session(client)
    url = f"/sessions/{session['id']}/events"
    event = {"event_id": "parallel-001", "step_id": "power", "source": "manual"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(url, json=event), range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert client.get(f"/sessions/{session['id']}").json()["step_index"] == 1


def test_ai_is_unavailable_and_input_is_bounded(client: TestClient):
    assert client.post("/ai/recognize", json={"model_id": "samsung-unknown"}).status_code == 503
    assert client.post("/ai/verify", json={}).status_code == 503
    session = start_session(client)
    assert client.post(
        f"/sessions/{session['id']}/events",
        json={"event_id": "bad-source", "step_id": "power", "source": "stable_ocr"},
    ).status_code == 422
    assert client.post("/sessions", json={"guide_id": "x" * 200}).status_code == 422
    assert client.post(
        "/sessions", content="x" * 9000, headers={"Content-Type": "application/json"}
    ).status_code == 413
