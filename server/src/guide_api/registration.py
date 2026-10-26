"""Owner-reviewed registration validation, shared with the offline provisioning CLI."""

import hashlib
import math

from pydantic import TypeAdapter

from guide_api.cloud import Conflict, Documents, NotFound
from guide_api.cloud_contracts import Category, CloudGuide, TargetKind
from guide_api.images import ImageInput, image_bytes
from guide_api.models import Identifier


def registration_documents(
    *,
    guide: dict,
    panel: dict,
    reference: bytes,
    product_id: str,
    model: str,
    category: str,
    target_kind: str,
    source_url: str | None,
    reviewed: bool,
) -> tuple[dict, dict, ImageInput]:
    """Validate reviewed guide/button geometry against the exact reference bytes."""
    validated = CloudGuide.model_validate(guide)
    image = image_bytes(reference)
    TypeAdapter(Identifier).validate_python(product_id)
    TypeAdapter(Category).validate_python(category)
    TypeAdapter(TargetKind).validate_python(target_kind)
    if not reviewed or not model.strip():
        raise ValueError("Human review and an applicable model name are required.")
    if not validated.demo:
        from pydantic import HttpUrl

        if not source_url or panel.get("demo") is not False:
            raise ValueError("Real products require an official source and a non-demo panel map.")
        TypeAdapter(HttpUrl).validate_python(source_url)
        if validated.target_id.startswith("original-demo-"):
            raise ValueError("Real products cannot replace the original synthetic demo.")
    elif panel.get("demo") is not True:
        raise ValueError("Synthetic guide and panel demo labels must agree.")
    if panel.get("target_id") != validated.target_id:
        raise ValueError("Panel target_id must match the guide.")
    if (panel.get("width_pixels"), panel.get("height_pixels")) != (image.width, image.height):
        raise ValueError("Panel dimensions must match the actual reference image.")
    width = panel.get("physical_width_meters")
    if isinstance(width, bool) or not isinstance(width, int | float) or not 0 < width <= 10:
        raise ValueError("A measured positive physical reference width is required.")

    def rectangle(values):
        if not isinstance(values, list) or len(values) != 4:
            raise ValueError("Rectangles require four normalized coordinates.")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in values
        ):
            raise ValueError("Rectangles must be finite normalized coordinates.")
        left, top, right, bottom = values
        if left >= right or top >= bottom:
            raise ValueError("Rectangles must have positive area.")

    rectangle(panel.get("display"))
    buttons = panel.get("buttons")
    if not isinstance(buttons, dict) or not buttons:
        raise ValueError("Panel buttons are required.")
    for button_id, coordinates in buttons.items():
        TypeAdapter(Identifier).validate_python(button_id)
        rectangle(coordinates)
    for step in validated.steps:
        if step.button_id not in buttons:
            raise ValueError(f"Unmapped guide button: {step.button_id}")
        if not step.instruction.strip() or not step.expected_display.strip():
            raise ValueError("Every step needs source-supported instructions and expected display.")
    digest = hashlib.sha256(reference).hexdigest()
    extension = "png" if image.mime == "image/png" else "jpg"
    metadata = {
        "demo": validated.demo,
        "model": model.strip(),
        "source_url": source_url,
        "review_status": "reviewed",
    }
    target = {
        "id": f"target:{validated.target_id}",
        "kind": "target",
        "target_id": validated.target_id,
        "product_id": product_id,
        "category": category,
        "target_kind": target_kind,
        **metadata,
        "guide_ids": [validated.id],
        "panel_map": panel,
        "reference_blob": f"references/{validated.target_id}/{digest}.{extension}",
        "reference_sha256": digest,
    }
    guide_document = {
        "id": f"guide:{validated.id}",
        "kind": "guide",
        "guide": validated.model_dump(),
        **metadata,
    }
    return target, guide_document, image


def check_registration(documents: Documents, *items: dict) -> None:
    for document in items:
        try:
            existing = documents.read("catalog", document["id"])
        except NotFound:
            continue
        comparable = {key: value for key, value in existing.items() if not key.startswith("_")}
        if comparable != document:
            raise ValueError(
                "Registered asset differs. Use a new versioned target/guide ID; do not overwrite."
            )


def store_registration(documents: Documents, *items: dict) -> None:
    check_registration(documents, *items)
    for document in items:
        try:
            documents.create("catalog", document)
        except Conflict:
            check_registration(documents, document)
