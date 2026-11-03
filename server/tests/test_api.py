import base64
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openai import OpenAIError
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
from visual_guide.issue_contracts import (
    ConfidenceBand,
    DynamicTargetSpec,
    GroundedIssueTarget,
    IssueGroundingResponse,
    IssueResolution,
    ProductCandidate,
    ProductStatus,
    SupportMode,
    TargetSource,
)
from visual_guide.main import create_app


class FakeGateway:
    client = object()

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


def _dynamic_target():
    return DynamicTargetSpec(
        target_id="detergent_dispenser",
        display_name="세제 넣는 곳",
        canonical_name="세제함 전면 덮개",
        aliases=("세제함",),
        purpose="locate",
        relative_region="lower_front",
        source=TargetSource.REGISTRY,
        registry_component_id="detergent_dispenser",
        manual_evidence="manual:page:22",
    )


def _issue_resolution(status=ProductStatus.REGISTERED):
    registered = status is ProductStatus.REGISTERED
    candidate = ProductCandidate(
        product_id="samsung-wd80h25bhs",
        manufacturer="Samsung",
        display_name="Bespoke AI Combo",
        exact_model_codes=("WD80H25BHS",),
        evidence_source="model_code" if registered else "product_hint",
        confidence_band=(
            ConfidenceBand.HIGH if registered else ConfidenceBand.MEDIUM
        ),
        confirmed_model_code="WD80H25BHS" if registered else None,
    )
    return IssueResolution(
        product_status=status,
        support_mode=(
            SupportMode.REVIEWED_GUIDE
            if registered
            else SupportMode.ZERO_SHOT_LOCATE_ONLY
        ),
        product_candidates=() if status is ProductStatus.UNKNOWN else (candidate,),
        issue_intent="detergent_loading",
        targets=(_dynamic_target(),),
        guide_candidates=(),
        requires_product_confirmation=status is ProductStatus.CANDIDATE,
        requires_target_confirmation=True,
        next_capture_instruction="제품 전면을 촬영하세요.",
        truncation_reason=None,
    )


class FakeIssueResolutionService:
    def resolve(self, request, image):
        if request.model_code == "UNSUPPORTED":
            raise LookupError("unsupported exact model")
        if request.user_issue == "provider down":
            raise OpenAIError("provider unavailable")
        if request.user_issue == "unknown":
            return _issue_resolution(ProductStatus.UNKNOWN)
        if request.user_issue == "candidate":
            return _issue_resolution(ProductStatus.CANDIDATE)
        return _issue_resolution()


class FakeIssueGroundingService:
    def ground(self, request, image):
        if request.confirmed_guide_id == "wrong-guide":
            raise ValueError("inapplicable guide")
        target = request.confirmed_targets[0]
        grounding = GroundedTarget(
            target_id=target.target_id,
            component=target.canonical_name,
            status=RegionStatus.LOCATED,
            point=PixelPoint(x=50, y=40),
            box=PixelBox(x1=10, y1=10, x2=90, y2=70),
            evidence="visible",
            attempts=1,
            retake_instruction=None,
        )
        return IssueGroundingResponse(
            product_status=request.resolution.product_status,
            support_mode=request.resolution.support_mode,
            product_id=request.confirmed_product_id,
            model_code=request.confirmed_model_code,
            guide_id=request.confirmed_guide_id,
            step_id=request.confirmed_step_id,
            image_width=image.width,
            image_height=image.height,
            targets=(
                GroundedIssueTarget(
                    target=target,
                    grounding=grounding,
                    instruction="세제함 위치를 확인하세요.",
                    source_reference="manual:page:22",
                ),
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
    assert "WD80H25BHS" not in page.text
    assert "detergent_dispenser" not in page.text
    assert "control_panel" not in page.text
    assert 'id="productHint"' in page.text
    assert 'id="modelCode"' in page.text
    assert 'id="userIssue"' in page.text
    assert 'id="userIssue"' in page.text and "required" in page.text
    assert 'id="currentState"' in page.text
    assert "MAX_TARGETS = 3" in page.text
    assert "/demo/issues/resolve" in page.text
    assert "/demo/issues/ground" in page.text
    assert "issueResolution" in page.text
    assert "renderTargetChips" in page.text
    assert "addTarget" in page.text
    assert "requires_product_confirmation" in page.text
    assert "reviewed_guide" in page.text
    assert "zero_shot_locate_only" in page.text
    assert "source_reference" in page.text
    assert "selectedFile" in page.text
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
    class ConfigRegistry:
        def model_manual_paths(self, _provider):
            return {"WD80H25BHS": Path("/app/data/WD80H25BHS.pdf")}

    monkeypatch.setattr(
        main_module,
        "load_reviewed_registry",
        lambda _root: ConfigRegistry(),
    )
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


@pytest.mark.parametrize(
    ("user_issue", "expected_status"),
    [
        ("세제를 어디에 넣어?", "registered"),
        ("candidate", "candidate"),
        ("unknown", "unknown"),
    ],
)
def test_issue_resolution_endpoint_returns_explicit_product_status(
    user_issue,
    expected_status,
):
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            issue_resolution_service=FakeIssueResolutionService(),
            bearer_token="expected-token",
        )
    )

    response = client.post(
        "/v1/issues/resolve",
        headers={"Authorization": "Bearer " + "expected-token"},
        json={
            "product_hint": "삼성 세탁건조기",
            "model_code": "WD80H25BHS",
            "user_issue": user_issue,
            "current_state": "제품 전면",
            "image_mime": None,
            "image_base64": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["product_status"] == expected_status


def test_issue_resolution_endpoint_requires_bearer_token():
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            issue_resolution_service=FakeIssueResolutionService(),
            bearer_token="expected-token",
        )
    )

    assert client.post("/v1/issues/resolve", json={}).status_code == 401


def test_issue_resolution_rejects_incomplete_optional_image():
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            issue_resolution_service=FakeIssueResolutionService(),
            bearer_token="expected-token",
        )
    )

    response = client.post(
        "/v1/issues/resolve",
        headers={"Authorization": "Bearer " + "expected-token"},
        json={
            "product_hint": None,
            "model_code": None,
            "user_issue": "버튼을 찾아줘",
            "current_state": None,
            "image_mime": "image/png",
            "image_base64": None,
        },
    )

    assert response.status_code == 422


def test_issue_resolution_maps_expected_and_provider_errors():
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            issue_resolution_service=FakeIssueResolutionService(),
            bearer_token="expected-token",
        )
    )
    headers = {"Authorization": "Bearer " + "expected-token"}
    base = {
        "product_hint": None,
        "current_state": None,
        "image_mime": None,
        "image_base64": None,
    }

    unsupported = client.post(
        "/v1/issues/resolve",
        headers=headers,
        json={**base, "model_code": "UNSUPPORTED", "user_issue": "버튼"},
    )
    unavailable = client.post(
        "/v1/issues/resolve",
        headers=headers,
        json={**base, "model_code": None, "user_issue": "provider down"},
    )

    assert unsupported.status_code == 422
    assert unavailable.status_code == 503


def test_issue_ground_endpoint_returns_422_for_inapplicable_guide():
    resolution = _issue_resolution()
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            issue_grounding_service=FakeIssueGroundingService(),
            bearer_token="expected-token",
        )
    )

    response = client.post(
        "/v1/issues/ground",
        headers={"Authorization": "Bearer " + "expected-token"},
        json={
            "request": {
                "resolution": resolution.model_dump(mode="json"),
                "confirmed_product_id": "samsung-wd80h25bhs",
                "confirmed_model_code": "WD80H25BHS",
                "confirmed_guide_id": "wrong-guide",
                "confirmed_step_id": "locate-parts",
                "confirmed_targets": [
                    target.model_dump(mode="json") for target in resolution.targets
                ],
            },
            "image_mime": "image/png",
            "image_base64": encoded_png(),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "inapplicable guide"


def test_demo_cookie_can_resolve_and_ground_issue():
    resolution = _issue_resolution()
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            issue_resolution_service=FakeIssueResolutionService(),
            issue_grounding_service=FakeIssueGroundingService(),
            demo_access_code="one-time-demo-code",
            demo_session_secret="dedicated-session-secret",
        ),
        base_url="https://testserver",
    )
    client.post("/demo/login", json={"code": "one-time-demo-code"})

    resolved = client.post(
        "/demo/issues/resolve",
        json={
            "product_hint": "삼성 세탁건조기",
            "model_code": "WD80H25BHS",
            "user_issue": "세제를 어디에 넣어?",
            "current_state": "제품 전면",
            "image_mime": None,
            "image_base64": None,
        },
    )
    grounded = client.post(
        "/demo/issues/ground",
        json={
            "request": {
                "resolution": resolution.model_dump(mode="json"),
                "confirmed_product_id": "samsung-wd80h25bhs",
                "confirmed_model_code": "WD80H25BHS",
                "confirmed_guide_id": "detergent-and-controls",
                "confirmed_step_id": "locate-detergent-and-controls",
                "confirmed_targets": [
                    target.model_dump(mode="json") for target in resolution.targets
                ],
            },
            "image_mime": "image/png",
            "image_base64": encoded_png(),
        },
    )

    assert resolved.status_code == 200
    assert grounded.status_code == 200
    assert grounded.json()["targets"][0]["grounding"]["status"] == "located"


def test_issue_endpoints_return_503_when_services_are_unavailable():
    client = TestClient(
        create_app(
            model_gateway=FakeGateway(),
            bearer_token="expected-token",
        )
    )
    headers = {"Authorization": "Bearer " + "expected-token"}

    response = client.post(
        "/v1/issues/resolve",
        headers=headers,
        json={
            "product_hint": None,
            "model_code": None,
            "user_issue": "버튼을 찾아줘",
            "current_state": None,
            "image_mime": None,
            "image_base64": None,
        },
    )

    assert response.status_code == 503
