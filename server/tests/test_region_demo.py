from fastapi.testclient import TestClient

from guide_api.region_demo import create_app
from guide_api.region_proposal import Region

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def client(proposer, endpoint="https://example.invalid/"):
    return TestClient(create_app(endpoint, "dep", proposer))


def post(c, data=PNG, names="power, dial"):
    return c.post("/propose", params={"components": names}, content=data)


def test_returns_draft_and_missing():
    seen = []

    def proposer(png, names, endpoint, deployment):
        seen.append((names, deployment))
        return [Region("power", (0.5, 0.5), (0.4, 0.4, 0.6, 0.6))]

    body = post(client(proposer)).json()
    assert seen == [(["power", "dial"], "dep")]
    assert body["status"] == "draft_needs_human_review"
    assert body["missing"] == ["dial"]


def test_rejects_bad_input_without_calling_model():
    def never(*args):
        raise AssertionError("model must not be called")

    c = client(never)
    assert post(c, data=b"GIF89a....").status_code == 415
    assert post(c, data=PNG + b"0" * 4_000_000).status_code == 413
    assert post(c, names=" , ").status_code == 422
    assert post(client(never, endpoint="")).status_code == 503


def test_model_failure_is_502_without_detail_leak():
    def boom(*args):
        raise RuntimeError("secret upstream text")

    reply = post(client(boom))
    assert reply.status_code == 502
    assert "secret" not in reply.text
