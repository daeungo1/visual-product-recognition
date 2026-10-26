"""Cloud contract tests with explicit in-memory adapters, not real-cloud evidence."""

import base64
import copy
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from guide_api.catalog import DEMO_GUIDE
from guide_api.cloud import CloudService, Conflict, NotFound, token_hash
from guide_api.main import create_app

ROOT = Path(__file__).resolve().parents[2]
IMAGE = base64.b64encode((ROOT / "assets" / "demo-target.png").read_bytes()).decode()


class MemoryDocuments:
    def __init__(self):
        self.items = {}
        self.lock = threading.Lock()
        self.replacements = 0
        self.force_conflict = False

    def read(self, container, item_id):
        with self.lock:
            if (container, item_id) not in self.items:
                raise NotFound
            return copy.deepcopy(self.items[container, item_id])

    def create(self, container, document):
        with self.lock:
            key = container, document["id"]
            if key in self.items:
                raise Conflict
            self.items[key] = {**copy.deepcopy(document), "_etag": "1"}

    def replace(self, container, document, etag):
        with self.lock:
            key = container, document["id"]
            if self.force_conflict or self.items[key]["_etag"] != etag:
                raise Conflict
            self.replacements += 1
            self.items[key] = {
                **copy.deepcopy(document),
                "_etag": str(int(etag) + 1),
            }

    def delete(self, container, item_id, etag):
        with self.lock:
            key = container, item_id
            if key not in self.items or self.items[key]["_etag"] != etag:
                raise Conflict
            del self.items[key]

    def list(self, container, kind):
        with self.lock:
            return [
                copy.deepcopy(value)
                for (name, _), value in self.items.items()
                if name == container and value.get("kind") == kind
            ]

    def ready(self):
        return {"document_count": 0}


class FakeAssets:
    def read(self, name):
        return (ROOT / "assets" / "demo-target.png").read_bytes()


class FakeEmbedder:
    dimensions = 768
    version = "google/siglip2-base-patch16-224@75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"

    def load(self):
        return None

    def embed(self, image):
        return [1.0] + [0.0] * 767


class FakeSearch:
    def __init__(self):
        self.results = []
        self.uploaded = []

    def ready(self):
        return {"document_count": 0}

    def query(self, vector, category, target_kind):
        return self.results

    def upload(self, documents):
        self.uploaded.extend(documents)


class FakeAI:
    def __init__(self):
        self.status = "pass"
        self.matches = []
        self.expected = None
        self.unavailable = False

    def verify(self, image, expected):
        if self.unavailable:
            raise HTTPException(503, "AI unavailable.")
        self.expected = expected
        return {"status": self.status, "reason": "Test double result."}

    def identify(self, image, references):
        if self.unavailable:
            raise HTTPException(503, "AI unavailable.")
        return self.matches

    def draft(self, body):
        return {"title": "Draft", "steps": [], "review_status": "published"}


@pytest.fixture
def setup_cloud():
    documents = MemoryDocuments()
    guide = DEMO_GUIDE.model_dump()
    documents.create(
        "catalog",
        {
            "id": f"guide:{guide['id']}",
            "kind": "guide",
            "guide": guide,
            "review_status": "reviewed",
        },
    )
    documents.create(
        "catalog",
        {
            "id": "target:original-demo-remote-v1",
            "kind": "target",
            "target_id": "original-demo-remote-v1",
            "product_id": "demo-aircon",
            "model": "Original synthetic demo",
            "category": "aircon",
            "target_kind": "remote",
            "demo": True,
            "review_status": "reviewed",
            "source_url": None,
            "reference_blob": "references/demo.png",
            "guide_ids": ["demo-aircon"],
            "panel_map": {
                "target_id": "original-demo-remote-v1",
                "width_pixels": 400,
                "height_pixels": 640,
                "physical_width_meters": 0.16,
                "display": [0.13, 0.14, 0.87, 0.38],
                "buttons": {
                    "power": [0.18, 0.45, 0.82, 0.55],
                    "mode": [0.18, 0.61, 0.82, 0.71],
                    "temperature": [0.18, 0.77, 0.82, 0.87],
                },
            },
        },
    )
    clock = [1000.0]
    ai, search = FakeAI(), FakeSearch()
    service = CloudService(
        documents,
        FakeAssets(),
        search,
        FakeEmbedder(),
        ai,
        clock=lambda: clock[0],
    )
    with TestClient(create_app(mode="cloud", cloud=service)) as client:
        yield client, service, documents, clock, ai, search


def issue(setup_cloud, code="pairing-code-for-unit-test", scope="device"):
    _, _, documents, clock, _, _ = setup_cloud
    documents.create(
        "invites",
        {
            "id": token_hash(code),
            "kind": "invite",
            "scope": scope,
            "expires_at": clock[0] + 100,
            "ttl": 100,
        },
    )
    return code


def pair(setup_cloud, code="pairing-code-for-unit-test", scope="device"):
    client = setup_cloud[0]
    response = client.post("/v1/pair", json={"code": issue(setup_cloud, code, scope)})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def session(setup_cloud, headers):
    response = setup_cloud[0].post(
        "/v1/sessions",
        json={"guide_id": "demo-aircon"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_pair_hashes_tokens_and_atomically_consumes_code(setup_cloud):
    client, _, documents, _, _, _ = setup_cloud
    code = issue(setup_cloud)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/v1/pair", json={"code": code}), range(2)))
    assert sorted(result.status_code for result in results) == [200, 401]
    success = next(result.json() for result in results if result.status_code == 200)
    assert success["expires_in"] == 86400
    assert success["scope"] == "device"
    assert success["access_token"] not in str(documents.items)
    assert code not in str(documents.items)


def test_auth_expiry_and_admin_scope(setup_cloud):
    client, _, _, clock, _, _ = setup_cloud
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert client.get("/readyz").json()["search_document_count"] == 0
    assert client.get("/v1/catalog").status_code == 401
    headers = pair(setup_cloud)
    assert client.get("/v1/catalog", headers=headers).status_code == 200
    assert client.post("/v1/admin/reindex", headers=headers).status_code == 403
    clock[0] += 86401
    assert client.get("/v1/catalog", headers=headers).status_code == 401


def test_expired_pair_and_rate_limit(setup_cloud):
    client, _, _, clock, _, _ = setup_cloud
    code = issue(setup_cloud)
    clock[0] += 101
    assert client.post("/v1/pair", json={"code": code}).status_code == 401
    responses = [client.post("/v1/pair", json={"code": "incorrect-code"}) for _ in range(12)]
    assert responses[-1].status_code == 429


def test_model_geometry_and_authenticated_reference(setup_cloud):
    client = setup_cloud[0]
    headers = pair(setup_cloud)
    result = client.get("/v1/models/original-demo-remote-v1", headers=headers).json()
    assert result["image_width"] == 400 and result["image_height"] == 640
    assert result["display"] == {"left": 0.13, "top": 0.14, "right": 0.87, "bottom": 0.38}
    assert result["buttons"]["power"]["top"] == 0.45
    assert result["reference_image_url"] == "/v1/models/original-demo-remote-v1/reference"
    assert client.get(result["reference_image_url"]).status_code == 401
    response = client.get(result["reference_image_url"], headers=headers)
    assert response.content == base64.b64decode(IMAGE)


def test_sessions_are_owner_scoped_and_event_replay_is_exact(setup_cloud):
    client = setup_cloud[0]
    owner = pair(setup_cloud)
    other = pair(setup_cloud, "another-pairing-test-code")
    sid = session(setup_cloud, owner)
    url = f"/v1/sessions/{sid}"
    assert client.get(url, headers=other).status_code == 404
    event = {"event_id": "event-0001", "step_id": "power", "source": "manual"}
    assert client.post(url + "/events", json=event, headers=other).status_code == 404
    first = client.post(url + "/events", json=event, headers=owner).json()
    client.post(
        url + "/events", headers=owner, json={**event, "event_id": "event-0002", "step_id": "mode"}
    )
    assert client.post(url + "/events", json=event, headers=owner).json() == first
    assert (
        client.post(
            url + "/events",
            headers=owner,
            json={**event, "source": "ocr", "observed_text": "POWER ON"},
        ).status_code
        == 409
    )


def test_parallel_events_use_conditional_write(setup_cloud):
    client, _, documents, _, _, _ = setup_cloud
    headers = pair(setup_cloud)
    sid = session(setup_cloud, headers)
    event = {"event_id": "parallel-event", "step_id": "power", "source": "manual"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    f"/v1/sessions/{sid}/events",
                    json=event,
                    headers=headers,
                ),
                range(4),
            )
        )
    assert all(response.status_code == 200 for response in responses)
    assert documents.replacements == 1
    documents.force_conflict = True
    assert (
        client.post(
            f"/v1/sessions/{sid}/events",
            headers=headers,
            json={
                **event,
                "event_id": "conflict-event",
                "step_id": "mode",
            },
        ).status_code
        == 409
    )


def test_verify_proof_is_step_scoped_consumed_and_expiring(setup_cloud):
    client, _, _, clock, ai, _ = setup_cloud
    headers = pair(setup_cloud)
    sid = session(setup_cloud, headers)
    url = f"/v1/sessions/{sid}"
    result = client.post(
        url + "/verify", headers=headers, json={"step_id": "power", "image_base64": IMAGE}
    )
    assert result.status_code == 200
    proof = result.json()
    assert ai.expected == "POWER ON"
    assert proof["status"] == "pass" and proof["expires_in"] == 30
    assert client.get(url, headers=headers).json()["step_index"] == 0
    event = {
        "event_id": "proof-event1",
        "step_id": "power",
        "source": "vlm",
        "verification_id": proof["verification_id"],
    }
    assert client.post(url + "/events", headers=headers, json=event).json()["last_source"] == "vlm"
    assert (
        client.post(
            url + "/events",
            headers=headers,
            json={
                **event,
                "event_id": "proof-event2",
                "step_id": "mode",
            },
        ).status_code
        == 409
    )
    second = client.post(
        url + "/verify", headers=headers, json={"step_id": "mode", "image_base64": IMAGE}
    ).json()
    clock[0] += 31
    assert (
        client.post(
            url + "/events",
            headers=headers,
            json={
                **event,
                "event_id": "expired-proof",
                "step_id": "mode",
                "verification_id": second["verification_id"],
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize("verdict", ["fail", "unsure"])
def test_no_proof_for_uncertain_or_failed_verification(setup_cloud, verdict):
    client, _, _, _, ai, _ = setup_cloud
    ai.status = verdict
    headers = pair(setup_cloud)
    sid = session(setup_cloud, headers)
    result = client.post(
        f"/v1/sessions/{sid}/verify",
        headers=headers,
        json={"step_id": "power", "image_base64": IMAGE},
    ).json()
    assert result["status"] == verdict
    assert result["verification_id"] is None


def test_ocr_numeric_boundaries_and_current_step(setup_cloud):
    client = setup_cloud[0]
    headers = pair(setup_cloud)
    sid = session(setup_cloud, headers)
    url = f"/v1/sessions/{sid}/events"
    for index, step in enumerate(("power", "mode")):
        assert (
            client.post(
                url,
                headers=headers,
                json={
                    "event_id": f"manual-{index}",
                    "step_id": step,
                    "source": "manual",
                },
            ).status_code
            == 200
        )
    event = {"event_id": "ocr-temperature", "step_id": "temperature", "source": "ocr"}
    for text in ("TEMP 240", "TEMP 124", "TEMP 24.5", "TEMP -24", "not visible"):
        assert (
            client.post(
                url,
                headers=headers,
                json={
                    **event,
                    "observed_text": text,
                },
            ).status_code
            == 409
        )
    result = client.post(url, headers=headers, json={**event, "observed_text": "TEMP 24"})
    assert result.status_code == 200 and result.json()["finished"] is True
    assert result.json()["last_source"] == "ocr"


def test_identify_filters_registered_candidates_and_never_falls_back(setup_cloud):
    client, _, _, _, ai, search = setup_cloud
    headers = pair(setup_cloud)
    body = {"category": "aircon", "target_kind": "remote", "image_base64": IMAGE}
    search.results = [
        {"target_id": "unregistered", "score": 1.0},
        {"target_id": "original-demo-remote-v1", "score": 0.9},
        {"target_id": "original-demo-remote-v1", "score": 0.8},
    ]
    ai.matches = ["invented-model"]
    assert client.post("/v1/identify", headers=headers, json=body).json()["status"] == "unknown"
    ai.matches = ["original-demo-remote-v1"]
    result = client.post("/v1/identify", headers=headers, json=body).json()
    assert result["requires_confirmation"] is True
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["search_score"] == 0.9
    ai.unavailable = True
    assert client.post("/v1/identify", headers=headers, json=body).status_code == 503


def test_image_bounds_and_unavailable_ai(setup_cloud):
    client, _, _, _, ai, _ = setup_cloud
    headers = pair(setup_cloud)
    sid = session(setup_cloud, headers)
    url = f"/v1/sessions/{sid}/verify"
    for content in ("!!!!", base64.b64encode(b"not an image").decode()):
        assert (
            client.post(
                url,
                headers=headers,
                json={
                    "step_id": "power",
                    "image_base64": content,
                },
            ).status_code
            == 422
        )
    assert (
        client.post(
            url,
            headers=headers,
            json={
                "step_id": "power",
                "image_base64": "A" * 2_800_000,
            },
        ).status_code
        == 413
    )
    ai.unavailable = True
    assert (
        client.post(
            url,
            headers=headers,
            json={
                "step_id": "power",
                "image_base64": IMAGE,
            },
        ).status_code
        == 503
    )


def test_admin_reindex_and_draft_cannot_publish(setup_cloud):
    client, _, _, _, _, search = setup_cloud
    headers = pair(setup_cloud, scope="admin")
    response = client.post("/v1/admin/reindex", headers=headers)
    assert response.status_code == 200
    assert response.json()["indexed"] == 1 and response.json()["dimensions"] == 768
    assert len(search.uploaded[0]["embedding"]) == 768
    draft = client.post(
        "/v1/admin/draft-guide",
        headers=headers,
        json={
            "source_url": "https://example.org/manual",
            "source_text": "Owner-provided manual",
            "model": "Owner-provided model",
        },
    )
    assert draft.status_code == 200 and draft.json()["review_status"] == "draft"


def test_pixel_and_image_format_limits(setup_cloud):
    client = setup_cloud[0]
    headers = pair(setup_cloud)
    for size, image_format, expected in (
        ((3000, 3000), "PNG", 413),
        ((10, 10), "GIF", 422),
    ):
        buffer = io.BytesIO()
        Image.new("RGB", size).save(buffer, format=image_format)
        response = client.post(
            "/v1/identify",
            headers=headers,
            json={
                "category": "aircon",
                "target_kind": "remote",
                "image_base64": base64.b64encode(buffer.getvalue()).decode(),
            },
        )
        assert response.status_code == expected


def test_ai_deadline_keeps_worker_bounded_until_background_call_finishes(setup_cloud):
    service = setup_cloud[1]
    blocked = threading.Event()
    try:
        with pytest.raises(HTTPException) as timeout:
            service.run_work(lambda: blocked.wait(5), timeout=0.01)
        assert timeout.value.status_code == 504
        with pytest.raises(HTTPException) as busy:
            service.run_work(lambda: None)
        assert busy.value.status_code == 429
    finally:
        blocked.set()


def test_vlm_network_wait_does_not_hold_model_gate(setup_cloud):
    service = setup_cloud[1]
    started, release = threading.Event(), threading.Event()

    def network():
        started.set()
        release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: service.run_ai(network))
        assert started.wait(2)
        try:
            assert service.run_work(lambda: "model-admission-is-free") == "model-admission-is-free"
        finally:
            release.set()
        future.result()


def test_delayed_verify_cannot_issue_previous_step_proof(setup_cloud):
    client, _, _, _, ai, _ = setup_cloud
    headers = pair(setup_cloud)
    sid = session(setup_cloud, headers)
    started, release = threading.Event(), threading.Event()

    def network(image, expected):
        started.set()
        release.wait(5)
        return {"status": "pass", "reason": "Delayed response"}

    ai.verify = network
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            lambda: client.post(
                f"/v1/sessions/{sid}/verify",
                headers=headers,
                json={"step_id": "power", "image_base64": IMAGE},
            )
        )
        assert started.wait(2)
        try:
            assert (
                client.post(
                    f"/v1/sessions/{sid}/events",
                    headers=headers,
                    json={
                        "event_id": "manual-before-proof",
                        "step_id": "power",
                        "source": "manual",
                    },
                ).status_code
                == 200
            )
        finally:
            release.set()
        assert future.result().status_code == 409
    assert client.get(f"/v1/sessions/{sid}", headers=headers).json()["step_index"] == 1


def test_validation_does_not_echo_sensitive_request_input(setup_cloud):
    client = setup_cloud[0]
    sensitive = "never-echo-this-code-" + "X" * 300
    response = client.post("/v1/pair", json={"code": sensitive})
    assert response.status_code == 422 and sensitive not in response.text
    assert all("input" not in error for error in response.json()["detail"])
    assert len(response.content) < 8192


def test_cloud_does_not_fall_back_when_unconfigured(monkeypatch):
    for name in (
        "COSMOS_ENDPOINT",
        "AZURE_STORAGE_ACCOUNT_URL",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_OPENAI_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app(mode="cloud")) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 503
        assert client.get("/v1/catalog").status_code == 401
        assert client.get("/catalog").status_code == 404
