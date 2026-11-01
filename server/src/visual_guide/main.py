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
from typing import Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from visual_guide.contracts import RegionProposal
from visual_guide.demo import DEMO_LOGIN_HTML, MOBILE_DEMO_HTML
from visual_guide.images import decode_image
from visual_guide.model_gateway import RegionRequest, build_foundry_gateway


class ReadyModelGateway(Protocol):
    """Model dependency required by readiness checks."""

    def ready(self) -> bool: ...

    def propose(self, request: RegionRequest, image) -> RegionProposal: ...


class RegionBody(BaseModel):
    """Authenticated step-scoped image request."""

    step_id: str = Field(min_length=1, max_length=128)
    component: str = Field(min_length=1, max_length=128)
    instruction: str = Field(min_length=1, max_length=500)
    image_mime: str
    image_base64: str = Field(min_length=1, max_length=14_000_000)


class DemoLoginBody(BaseModel):
    """Access code submitted in a request body, never in the URL."""

    code: str = Field(min_length=16, max_length=256)


def create_app(
    *,
    model_gateway: ReadyModelGateway | None,
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

    def run_proposal(body: RegionBody) -> RegionProposal:
        if model_gateway is None:
            raise HTTPException(503, "Model gateway unavailable.")
        try:
            encoded = base64.b64decode(body.image_base64, validate=True)
            image = decode_image(encoded, body.image_mime)
        except (binascii.Error, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        return model_gateway.propose(
            RegionRequest(
                step_id=body.step_id,
                component=body.component,
                instruction=body.instruction,
            ),
            image,
        )

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

    return app


def create_configured_app() -> FastAPI:
    """Create the environment-configured production application."""
    endpoint = os.getenv("FOUNDRY_ENDPOINT")
    deployment = os.getenv("FOUNDRY_DEPLOYMENT", "gpt-6-1-terra")
    gateway = build_foundry_gateway(endpoint, deployment) if endpoint else None
    return create_app(
        model_gateway=gateway,
        bearer_token=os.getenv("API_BEARER_TOKEN"),
        demo_access_code=os.getenv("DEMO_ACCESS_CODE"),
        demo_session_secret=os.getenv("DEMO_SESSION_SECRET"),
    )


app = create_configured_app()
