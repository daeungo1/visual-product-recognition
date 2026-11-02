import base64
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from visual_guide import main as main_module
from visual_guide.contracts import (
    GroundedTarget,
    MultiTargetRegionResponse,
    PixelBox,
    PixelPoint,
    RegionProposal,
    RegionStatus,
)
from visual_guide.main import create_app


class FakeGateway:
    def ready(self):
        return True

    def propose(self, request, image):
        return RegionProposal(
            status=RegionStatus.LOCATED,
            step_id=request.step_id,
            component=request.component,
            image_width=image.width,
            image_height=image.height,
            point=PixelPoint(x=50, y=40),
            box=PixelBox(x1=10, y1=10, x2=90, y2=70),
            evidence="visible",
        )


class FakeGroundingService:
    def ground(self, request, image):
        if "unknown_part" in request.target_ids:
            raise ValueError("Unknown target: unknown_part")
        return MultiTargetRegionResponse(
            product_id="samsung-wd80h25bhs",
            guide_id=request.guide_id,
            step_id=request.step_id,
            image_width=image.width,
            image_height=image.height,
            targets=tuple(
                GroundedTarget(
                    target_id=target_id,
                    component=target_id,
                    status=RegionStatus.LOCATED,
                    point=PixelPoint(x=50, y=40),
                    box=PixelBox(x1=10, y1=10, x2=90, y2=70),
                    evidence="visible",
                    attempts=1,
                    retake_instruction=None,
                )
                for target_id in request.target_ids
            ),
            partial_success=False,
        )


def encoded_png() -> str:
    output = BytesIO()
    Image.new("RGB", (100, 80), "white").save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode()


def test_health_and_readiness_are_separate():
    client = TestClient(create_app(model_gateway=None))

    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["dependency"] == "model_gateway"


def test_region_endpoint_requires_bearer_token():
    client = TestClient(create_app(model_gateway=None, bearer_token="expected-token"))

    response = client.post("/v1/regions/propose", json={})

    assert response.status_code == 401


def test_region_endpoint_returns_validated_model_proposal():
    client = TestClient(create_app(model_gateway=FakeGateway(), bearer_token="expected-token"))

    response = client.post(
        "/v1/regions/propose",
        headers={"Authorization": "Bearer expected-token"},
        json={
            "step_id": "open-filter-cover",
            "component": "top-filter-cover",
            "instruction": "Locate the top filter cover.",
            "image_mime": "image/png",
            "image_base64": encoded_png(),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "located"
    assert response.json()["point"] == {"x": 50, "y": 40}


def test_multi_target_grounding_endpoint_keeps_targets_independent():
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            guide_grounding_service=FakeGroundingService(),
            bearer_token="expected-token",
        )
    )

    response = client.post(
        "/v1/guides/ground",
        headers={"Authorization": "Bearer " + "expected-token"},
        json={
            "model_code": "WD80H25BHS",
            "guide_id": "detergent-and-controls",
            "step_id": "locate-detergent-and-controls",
            "target_ids": ["detergent_dispenser", "control_panel"],
            "image_mime": "image/png",
            "image_base64": encoded_png(),
        },
    )

    assert response.status_code == 200
    assert [target["target_id"] for target in response.json()["targets"]] == [
        "detergent_dispenser",
        "control_panel",
    ]


def test_multi_target_grounding_endpoint_rejects_unknown_target():
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            guide_grounding_service=FakeGroundingService(),
            bearer_token="expected-token",
        )
    )

    response = client.post(
        "/v1/guides/ground",
        headers={"Authorization": "Bearer " + "expected-token"},
        json={
            "model_code": "WD80H25BHS",
            "guide_id": "detergent-and-controls",
            "step_id": "locate-detergent-and-controls",
            "target_ids": ["unknown_part"],
            "image_mime": "image/png",
            "image_base64": encoded_png(),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown target: unknown_part"


def test_mobile_demo_uses_login_cookie_without_exposing_api_token():
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            bearer_token="expected-token",
            demo_access_code="one-time-demo-code",
            demo_session_secret="dedicated-session-secret",
        ),
        base_url="https://testserver",
    )

    unauthorized = client.get("/demo")
    login_page = client.get("/demo/login")
    bad_login = client.post(
        "/demo/login",
        json={"code": "wrong-code-value"},
        follow_redirects=False,
    )
    login = client.post(
        "/demo/login",
        json={"code": "one-time-demo-code"},
        follow_redirects=False,
    )
    page = client.get("/demo")

    assert unauthorized.status_code == 401
    assert login_page.status_code == 200
    assert 'type="password"' in login_page.text
    assert bad_login.status_code == 401
    assert login.status_code == 303
    assert "one-time-demo-code" not in login.headers["location"]
    assert "expected-token" not in login.headers.get("set-cookie", "")
    assert login.headers["cache-control"] == "no-store"
    assert page.status_code == 200
    assert 'capture="environment"' in page.text
    assert "MAX_PIXELS" in page.text
    assert "canvas.toBlob" in page.text
    assert "expected-token" not in page.text
    assert "WD80H25BHS" in page.text
    assert "detergent_dispenser" in page.text
    assert "control_panel" in page.text
    assert 'id="component"' not in page.text
    assert 'id="instruction"' not in page.text
    assert "result.targets" in page.text
    assert "partial_success" in page.text
    assert "retake_instruction" in page.text


def test_mobile_demo_cookie_can_call_proposal_without_bearer_header():
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            bearer_token="expected-token",
            demo_access_code="one-time-demo-code",
            demo_session_secret="dedicated-session-secret",
        ),
        base_url="https://testserver",
    )
    client.post("/demo/login", json={"code": "one-time-demo-code"})

    response = client.post(
        "/demo/propose",
        json={
            "step_id": "locate-filter-cover",
            "component": "filter cover",
            "instruction": "Locate the visible filter cover only.",
            "image_mime": "image/png",
            "image_base64": encoded_png(),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "located"


def test_mobile_demo_cookie_can_call_reviewed_multi_target_grounding():
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            guide_grounding_service=FakeGroundingService(),
            bearer_token="expected-token",
            demo_access_code="one-time-demo-code",
            demo_session_secret="dedicated-session-secret",
        ),
        base_url="https://testserver",
    )
    client.post("/demo/login", json={"code": "one-time-demo-code"})

    response = client.post(
        "/demo/ground",
        json={
            "model_code": "WD80H25BHS",
            "guide_id": "detergent-and-controls",
            "step_id": "locate-detergent-and-controls",
            "target_ids": ["detergent_dispenser", "control_panel"],
            "image_mime": "image/png",
            "image_base64": encoded_png(),
        },
    )

    assert response.status_code == 200
    assert len(response.json()["targets"]) == 2


def test_configured_app_wires_reviewed_grounding_service(monkeypatch):
    monkeypatch.setenv("FOUNDRY_ENDPOINT", "https://foundry.example.test")
    monkeypatch.setenv("FOUNDRY_DEPLOYMENT", "gpt-6-1-terra")
    monkeypatch.setenv("REVIEWED_MANUAL_PATH", "/app/data/WD80H25BHS.pdf")
    monkeypatch.setenv("API_BEARER_TOKEN", "expected-token")
    monkeypatch.setenv("DEMO_ACCESS_CODE", "one-time-demo-code")
    monkeypatch.setenv("DEMO_SESSION_SECRET", "dedicated-session-secret")
    monkeypatch.setattr(
        main_module,
        "build_foundry_gateway",
        lambda _endpoint, _deployment: FakeGateway(),
    )
    monkeypatch.setattr(main_module, "load_reviewed_registry", lambda _root: object())
    monkeypatch.setattr(
        main_module,
        "GuideGroundingService",
        lambda **_kwargs: FakeGroundingService(),
    )
    client = TestClient(main_module.create_configured_app(), base_url="https://testserver")
    client.post("/demo/login", json={"code": "one-time-demo-code"})

    response = client.post(
        "/demo/ground",
        json={
            "model_code": "WD80H25BHS",
            "guide_id": "detergent-and-controls",
            "step_id": "locate-detergent-and-controls",
            "target_ids": ["control_panel"],
            "image_mime": "image/png",
            "image_base64": encoded_png(),
        },
    )

    assert response.status_code == 200
    assert response.json()["targets"][0]["target_id"] == "control_panel"


def test_rotating_demo_access_code_invalidates_existing_cookie():
    first = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            bearer_token="expected-token",
            demo_access_code="first-code",
            demo_session_secret="dedicated-session-secret",
        ),
        base_url="https://testserver",
    )
    first.post("/demo/login", json={"code": "first-code"})
    old_cookie = first.cookies.get("visual_guide_demo")
    rotated = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            bearer_token="expected-token",
            demo_access_code="second-code",
            demo_session_secret="dedicated-session-secret",
        ),
        base_url="https://testserver",
        cookies={"visual_guide_demo": old_cookie},
    )

    assert rotated.get("/demo").status_code == 401


def test_demo_cookie_expires_on_the_server():
    now = [1_000.0]
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            bearer_token="expected-token",
            demo_access_code="one-time-demo-code",
            demo_session_secret="dedicated-session-secret",
            clock=lambda: now[0],
        ),
        base_url="https://testserver",
    )
    client.post("/demo/login", json={"code": "one-time-demo-code"})
    now[0] += 8 * 60 * 60 + 1

    assert client.get("/demo").status_code == 401
