"""Authenticated /v1 router; deliberately separate from unauthenticated local demo routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response

from guide_api.cloud import CloudService
from guide_api.cloud_contracts import (
    CloudEvent,
    DraftRequest,
    IdentifyRequest,
    PairRequest,
    VerifyRequest,
)
from guide_api.models import Identifier, StartSession

router = APIRouter(prefix="/v1")


def service(request: Request) -> CloudService:
    if request.url.path != "/v1/pair" and not request.headers.get("authorization"):
        raise HTTPException(401, "Bearer token required.")
    value = request.app.state.cloud
    if value is None:
        raise HTTPException(
            request.app.state.cloud_error_status,
            "Cloud configuration or dependencies unavailable.",
        )
    return value


def device(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    # Missing authentication remains 401 even while cloud dependencies are unconfigured.
    if not authorization:
        raise HTTPException(401, "Bearer token required.")
    return service(request).authenticate(authorization)


def admin(principal: Annotated[dict, Depends(device)]) -> dict:
    if principal["scope"] != "admin":
        raise HTTPException(403, "Admin scope required.")
    return principal


Cloud = Annotated[CloudService, Depends(service)]
Device = Annotated[dict, Depends(device)]


@router.post("/pair")
def pair(body: PairRequest, request: Request, cloud: Cloud):
    address = request.client.host if request.client else "unknown"
    return cloud.pair(body.code, address)


@router.get("/catalog")
def catalog(cloud: Cloud, principal: Device):
    return cloud.catalog()


@router.get("/guides/{guide_id}")
def guide(guide_id: Identifier, cloud: Cloud, principal: Device):
    return cloud.guide(guide_id)


@router.get("/models/{target_id}")
def model(target_id: Identifier, cloud: Cloud, principal: Device):
    return cloud.model(target_id)


@router.get("/models/{target_id}/reference")
def reference(target_id: Identifier, cloud: Cloud, principal: Device):
    image = cloud.reference(target_id)
    return Response(
        image.data,
        media_type=image.mime,
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/identify")
def identify(body: IdentifyRequest, cloud: Cloud, principal: Device):
    return cloud.identify(body)


@router.post("/sessions", status_code=201)
def start(body: StartSession, cloud: Cloud, principal: Device):
    return cloud.start(body.guide_id, principal)


@router.get("/sessions/{session_id}")
def session(session_id: Identifier, cloud: Cloud, principal: Device):
    return cloud.state(cloud.owned(session_id, principal))


@router.post("/sessions/{session_id}/events")
def advance(session_id: Identifier, body: CloudEvent, cloud: Cloud, principal: Device):
    return cloud.advance(session_id, principal, body)


@router.post("/sessions/{session_id}/verify")
def verify(session_id: Identifier, body: VerifyRequest, cloud: Cloud, principal: Device):
    return cloud.verify(session_id, principal, body.step_id, body.image_base64)


@router.post("/admin/reindex", dependencies=[Depends(admin)])
def reindex(cloud: Cloud):
    return cloud.reindex()


@router.post("/admin/draft-guide", dependencies=[Depends(admin)])
def draft(body: DraftRequest, cloud: Cloud):
    return cloud.draft(body)
