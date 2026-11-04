"""FastAPI application factory."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from openai import OpenAIError
from pydantic import BaseModel, Field, model_validator

from visual_guide.contracts import (
    MultiTargetRegionRequest,
    MultiTargetRegionResponse,
    RegionProposal,
)
from visual_guide.demo import DEMO_LOGIN_HTML, MOBILE_DEMO_HTML
from visual_guide.images import decode_image
from visual_guide.issue_contracts import (
    IssueGroundingRequest,
    IssueGroundingResponse,
    IssueResolution,
    IssueResolutionRequest,
)
from visual_guide.issue_grounding import (
    IssueGroundingProviderError,
    IssueGroundingService,
)
from visual_guide.issue_planner import FoundryIssuePlanner
from visual_guide.issue_service import IssueResolutionService, ResolutionSigner
from visual_guide.manual_assets import ManualAssetProvider
from visual_guide.model_gateway import RegionRequest, build_foundry_gateway
from visual_guide.orchestrator import (
    GroundingProviderError,
    GuideGroundingService,
    TargetGrounder,
)
from visual_guide.registry import load_reviewed_registry


class ReadyModelGateway(Protocol):
    """Model dependency required by readiness checks."""

    def ready(self) -> bool: ...

    def propose(self, request: RegionRequest, image) -> RegionProposal: ...


class GuideGrounding(Protocol):
    """Reviewed multi-target grounding dependency."""

    def ground(
        self,
        request: MultiTargetRegionRequest,
        image,
    ) -> MultiTargetRegionResponse: ...


class IssueResolver(Protocol):
    """Hybrid issue resolution dependency."""

    def resolve(self, request: IssueResolutionRequest, image) -> IssueResolution: ...


class IssueGrounder(Protocol):
    """Hybrid dynamic target grounding dependency."""

    def ground(
        self,
        request: IssueGroundingRequest,
        image,
    ) -> IssueGroundingResponse: ...


class RegionBody(BaseModel):
    """Authenticated step-scoped image request."""

    step_id: str = Field(min_length=1, max_length=128)
    component: str = Field(min_length=1, max_length=128)
    instruction: str = Field(min_length=1, max_length=500)
    image_mime: str
    image_base64: str = Field(min_length=1, max_length=14_000_000)


class GuideGroundBody(BaseModel):
    """Authenticated reviewed-guide image request."""

    model_code: str = Field(min_length=1, max_length=128)
    guide_id: str = Field(min_length=1, max_length=128)
    step_id: str = Field(min_length=1, max_length=128)
    target_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    image_mime: str
    image_base64: str = Field(min_length=1, max_length=14_000_000)


class IssueResolveBody(BaseModel):
    """Free-form issue with an optional validated image."""

    product_hint: str | None = Field(default=None, max_length=256)
    model_code: str | None = Field(default=None, max_length=128)
    user_issue: str = Field(min_length=1, max_length=1000)
    current_state: str | None = Field(default=None, max_length=500)
    image_mime: str | None = None
    image_base64: str | None = Field(default=None, max_length=14_000_000)

    @model_validator(mode="after")
    def complete_optional_image(self) -> "IssueResolveBody":
        if (self.image_mime is None) != (self.image_base64 is None):
            raise ValueError("image_mime and image_base64 must be supplied together")
        return self


class IssueGroundBody(BaseModel):
    """Confirmed issue targets and required image."""

    request: IssueGroundingRequest
    image_mime: str
    image_base64: str = Field(min_length=1, max_length=14_000_000)


class DemoLoginBody(BaseModel):
    """Access code submitted in a request body, never in the URL."""

    code: str = Field(min_length=16, max_length=256)


def create_app(
    *,
    model_gateway: ReadyModelGateway | None,
    guide_grounding_service: GuideGrounding | None = None,
    issue_resolution_service: IssueResolver | None = None,
    issue_grounding_service: IssueGrounder | None = None,
    bearer_token: str | None = None,
    demo_access_code: str | None = None,
    demo_session_secret: str | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    """Create the visual guide API without silent model fallbacks."""
    app = FastAPI(title="Visual Product Guide")

    def authorize(authorization: str | None = Header(default=None)) -> None:
        if bearer_token is None:
            raise HTTPException(503, "API authentication is not configured.")
        if authorization != f"Bearer {bearer_token}":
            raise HTTPException(401, "Bearer token required.")

    def demo_cookie_value() -> str:
        if demo_access_code is None or demo_session_secret is None:
            raise HTTPException(503, "Demo authentication is not configured.")
        payload = json.dumps(
            {
                "exp": int(clock()) + 8 * 60 * 60,
                "generation": hashlib.sha256(demo_access_code.encode()).hexdigest()[:16],
                "nonce": secrets.token_urlsafe(16),
            },
            separators=(",", ":"),
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(
            demo_session_secret.encode(),
            encoded.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{encoded}.{signature}"

    def authorize_demo(request: Request) -> None:
        supplied = request.cookies.get("visual_guide_demo", "")
        try:
            encoded, supplied_signature = supplied.split(".", 1)
            expected_signature = hmac.new(
                (demo_session_secret or "").encode(),
                encoded.encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise ValueError("invalid signature")
            padding = "=" * (-len(encoded) % 4)
            payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
            generation = hashlib.sha256((demo_access_code or "").encode()).hexdigest()[:16]
            if payload["exp"] < int(clock()) or payload["generation"] != generation:
                raise ValueError("expired or rotated")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(401, "Demo login required.") from None

    def decode_body_image(image_mime: str, image_base64: str):
        try:
            encoded = base64.b64decode(image_base64, validate=True)
            return decode_image(encoded, image_mime)
        except (binascii.Error, ValueError) as error:
            raise HTTPException(422, str(error)) from error

    def run_proposal(body: RegionBody) -> RegionProposal:
        if model_gateway is None:
            raise HTTPException(503, "Model gateway unavailable.")
        image = decode_body_image(body.image_mime, body.image_base64)
        return model_gateway.propose(
            RegionRequest(
                step_id=body.step_id,
                component=body.component,
                instruction=body.instruction,
            ),
            image,
        )

    def run_grounding(body: GuideGroundBody) -> MultiTargetRegionResponse:
        if guide_grounding_service is None:
            raise HTTPException(503, "Guide grounding service unavailable.")
        image = decode_body_image(body.image_mime, body.image_base64)
        try:
            return guide_grounding_service.ground(
                MultiTargetRegionRequest(
                    model_code=body.model_code,
                    guide_id=body.guide_id,
                    step_id=body.step_id,
                    target_ids=body.target_ids,
                ),
                image,
            )
        except GroundingProviderError as error:
            raise HTTPException(
                503,
                {
                    "message": "Grounding provider unavailable.",
                    "failed_target_id": error.failed_target_id,
                    "completed_targets": [
                        target.model_dump(mode="json")
                        for target in error.completed_targets
                    ],
                },
            ) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    def run_issue_resolution(body: IssueResolveBody) -> IssueResolution:
        if issue_resolution_service is None:
            raise HTTPException(503, "Issue resolution service unavailable.")
        image = (
            decode_body_image(body.image_mime, body.image_base64)
            if body.image_mime is not None and body.image_base64 is not None
            else None
        )
        try:
            return issue_resolution_service.resolve(
                IssueResolutionRequest(
                    product_hint=body.product_hint,
                    model_code=body.model_code,
                    user_issue=body.user_issue,
                    current_state=body.current_state,
                ),
                image,
            )
        except (LookupError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        except (OpenAIError, TimeoutError, ConnectionError, RuntimeError) as error:
            raise HTTPException(503, "Issue planner unavailable.") from error

    def run_issue_grounding(body: IssueGroundBody) -> IssueGroundingResponse:
        if issue_grounding_service is None:
            raise HTTPException(503, "Issue grounding service unavailable.")
        image = decode_body_image(body.image_mime, body.image_base64)
        try:
            return issue_grounding_service.ground(body.request, image)
        except IssueGroundingProviderError as error:
            raise HTTPException(
                503,
                {
                    "message": "Issue grounding provider unavailable.",
                    "failed_target_id": error.failed_target_id,
                    "completed_targets": [
                        target.model_dump(mode="json")
                        for target in error.completed_targets
                    ],
                },
            ) from error
        except (LookupError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        except (OpenAIError, TimeoutError, ConnectionError, RuntimeError) as error:
            raise HTTPException(503, "Issue grounding provider unavailable.") from error

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        if model_gateway is None or not model_gateway.ready():
            return JSONResponse(
                {"status": "not_ready", "dependency": "model_gateway"},
                status_code=503,
            )
        return {"status": "ready"}

    @app.post(
        "/v1/regions/propose",
        dependencies=[Depends(authorize)],
        response_model=RegionProposal,
    )
    def propose(body: RegionBody) -> RegionProposal:
        return run_proposal(body)

    @app.post(
        "/v1/guides/ground",
        dependencies=[Depends(authorize)],
        response_model=MultiTargetRegionResponse,
    )
    def ground_guide(body: GuideGroundBody) -> MultiTargetRegionResponse:
        return run_grounding(body)

    @app.post(
        "/v1/issues/resolve",
        dependencies=[Depends(authorize)],
        response_model=IssueResolution,
    )
    def resolve_issue(body: IssueResolveBody) -> IssueResolution:
        return run_issue_resolution(body)

    @app.post(
        "/v1/issues/ground",
        dependencies=[Depends(authorize)],
        response_model=IssueGroundingResponse,
    )
    def ground_issue(body: IssueGroundBody) -> IssueGroundingResponse:
        return run_issue_grounding(body)

    @app.get("/demo/login", response_class=HTMLResponse)
    def demo_login_page() -> HTMLResponse:
        return HTMLResponse(DEMO_LOGIN_HTML, headers={"Cache-Control": "no-store"})

    @app.post("/demo/login")
    def demo_login(body: DemoLoginBody) -> RedirectResponse:
        if demo_access_code is None or not hmac.compare_digest(body.code, demo_access_code):
            raise HTTPException(401, "Invalid demo access code.")
        response = RedirectResponse("/demo", status_code=303)
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            "visual_guide_demo",
            demo_cookie_value(),
            max_age=8 * 60 * 60,
            secure=True,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.get("/demo", response_class=HTMLResponse, dependencies=[Depends(authorize_demo)])
    def demo() -> HTMLResponse:
        return HTMLResponse(MOBILE_DEMO_HTML, headers={"Cache-Control": "no-store"})

    @app.post(
        "/demo/propose",
        response_model=RegionProposal,
        dependencies=[Depends(authorize_demo)],
    )
    def demo_propose(body: RegionBody) -> RegionProposal:
        return run_proposal(body)

    @app.post(
        "/demo/ground",
        response_model=MultiTargetRegionResponse,
        dependencies=[Depends(authorize_demo)],
    )
    def demo_ground(body: GuideGroundBody) -> MultiTargetRegionResponse:
        return run_grounding(body)

    @app.post(
        "/demo/issues/resolve",
        response_model=IssueResolution,
        dependencies=[Depends(authorize_demo)],
    )
    def demo_resolve_issue(body: IssueResolveBody) -> IssueResolution:
        return run_issue_resolution(body)

    @app.post(
        "/demo/issues/ground",
        response_model=IssueGroundingResponse,
        dependencies=[Depends(authorize_demo)],
    )
    def demo_ground_issue(body: IssueGroundBody) -> IssueGroundingResponse:
        return run_issue_grounding(body)

    return app


def create_configured_app() -> FastAPI:
    """Create the environment-configured production application."""
    endpoint = os.getenv("FOUNDRY_ENDPOINT")
    deployment = os.getenv("FOUNDRY_DEPLOYMENT", "gpt-6-1-terra")
    gateway = build_foundry_gateway(endpoint, deployment) if endpoint else None
    manual_path = os.getenv("REVIEWED_MANUAL_PATH")
    grounding_service = None
    issue_resolution_service = None
    issue_grounding_service = None
    resolution_secret = os.getenv("ISSUE_RESOLUTION_SECRET") or os.getenv(
        "DEMO_SESSION_SECRET"
    )
    if gateway is not None and manual_path and resolution_secret:
        registry = load_reviewed_registry(Path(__file__).parent / "references")
        manual_provider = ManualAssetProvider(Path(manual_path).parent)
        signer = ResolutionSigner(resolution_secret)
        grounding_service = GuideGroundingService(
            registry=registry,
            gateway=gateway,
            manual_paths=registry.model_manual_paths(manual_provider),
        )
        issue_resolution_service = IssueResolutionService(
            planner=FoundryIssuePlanner(
                client=gateway.client,
                deployment=deployment,
            ),
            registry=registry,
            signer=signer,
        )
        issue_grounding_service = IssueGroundingService(
            registry=registry,
            manual_provider=manual_provider,
            target_grounder=TargetGrounder(gateway),
            signer=signer,
        )
    return create_app(
        model_gateway=gateway,
        guide_grounding_service=grounding_service,
        issue_resolution_service=issue_resolution_service,
        issue_grounding_service=issue_grounding_service,
        bearer_token=os.getenv("API_BEARER_TOKEN"),
        demo_access_code=os.getenv("DEMO_ACCESS_CODE"),
        demo_session_secret=os.getenv("DEMO_SESSION_SECRET"),
    )


app = create_configured_app()
