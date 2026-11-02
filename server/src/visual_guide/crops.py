"""Reviewed-prior crop planning and deterministic coordinate remapping."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from visual_guide.contracts import PixelBox, PixelPoint, RegionProposal
from visual_guide.images import ImageInput
from visual_guide.registry import ComponentSpec

REGION_RATIOS = {
    "upper_left": (0.0, 0.0, 0.6, 0.55),
    "upper_center": (0.15, 0.0, 0.85, 0.5),
    "upper_right": (0.4, 0.0, 1.0, 0.55),
    "lower_front": (0.0, 0.55, 1.0, 1.0),
    "full_front": (0.0, 0.0, 1.0, 1.0),
}


@dataclass(frozen=True)
class CropWindow:
    """Root-image crop bounds using half-open pixel coordinates."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0


@dataclass(frozen=True)
class CroppedImage:
    """Cropped model input and its root-image transform."""

    image: ImageInput
    window: CropWindow
    root_width: int
    root_height: int


def crop_image(image: ImageInput, component: ComponentSpec) -> CroppedImage:
    """Crop one reviewed relative region without resizing its pixels."""
    left, top, right, bottom = REGION_RATIOS[component.relative_region]
    window = CropWindow(
        x0=max(0, min(image.width - 1, int(image.width * left))),
        y0=max(0, min(image.height - 1, int(image.height * top))),
        x1=max(1, min(image.width, int(image.width * right))),
        y1=max(1, min(image.height, int(image.height * bottom))),
    )
    with Image.open(BytesIO(image.data)) as source:
        cropped = source.crop((window.x0, window.y0, window.x1, window.y1))
        output = BytesIO()
        if image.mime == "image/png":
            cropped.save(output, format="PNG")
        else:
            cropped.convert("RGB").save(output, format="JPEG", quality=95)
    return CroppedImage(
        image=ImageInput(
            data=output.getvalue(),
            mime=image.mime,
            width=window.width,
            height=window.height,
        ),
        window=window,
        root_width=image.width,
        root_height=image.height,
    )


def remap_proposal(
    proposal: RegionProposal,
    cropped: CroppedImage,
) -> RegionProposal:
    """Map crop-relative proposal geometry into root-image pixels."""
    if (
        proposal.image_width != cropped.image.width
        or proposal.image_height != cropped.image.height
    ):
        raise ValueError("Proposal dimensions do not match the crop.")
    point = (
        PixelPoint(
            x=proposal.point.x + cropped.window.x0,
            y=proposal.point.y + cropped.window.y0,
        )
        if proposal.point is not None
        else None
    )
    box = (
        PixelBox(
            x1=proposal.box.x1 + cropped.window.x0,
            y1=proposal.box.y1 + cropped.window.y0,
            x2=proposal.box.x2 + cropped.window.x0,
            y2=proposal.box.y2 + cropped.window.y0,
        )
        if proposal.box is not None
        else None
    )
    return RegionProposal(
        status=proposal.status,
        step_id=proposal.step_id,
        component=proposal.component,
        image_width=cropped.root_width,
        image_height=cropped.root_height,
        point=point,
        box=box,
        evidence=proposal.evidence,
    )
