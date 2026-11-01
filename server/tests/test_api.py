import base64
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from visual_guide.contracts import PixelBox, PixelPoint, RegionProposal, RegionStatus
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
