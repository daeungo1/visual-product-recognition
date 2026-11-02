from io import BytesIO

import pytest
from PIL import Image

from visual_guide.contracts import PixelBox, PixelPoint, RegionProposal, RegionStatus
from visual_guide.crops import crop_image, remap_proposal
from visual_guide.images import decode_image
from visual_guide.registry import ComponentSpec


def _image(width: int = 1000, height: int = 800):
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return decode_image(output.getvalue(), "image/png")


def _component(relative_region: str) -> ComponentSpec:
    return ComponentSpec(
        component_id="target",
        canonical_name="target",
        aliases=("target",),
        relative_region=relative_region,
    )


def test_crop_image_uses_reviewed_upper_left_and_upper_right_priors():
    root = _image()

    left = crop_image(root, _component("upper_left"))
    right = crop_image(root, _component("upper_right"))

    assert (left.window.x0, left.window.y0, left.window.x1, left.window.y1) == (
        0,
        0,
        600,
        440,
    )
    assert (right.window.x0, right.window.y0, right.window.x1, right.window.y1) == (
        400,
        0,
        1000,
        440,
    )


def test_crop_image_clips_to_root_bounds_without_upscaling():
    root = _image(101, 99)

    cropped = crop_image(root, _component("lower_front"))

    assert cropped.window.x0 >= 0
    assert cropped.window.y0 >= 0
    assert cropped.window.x1 <= root.width
    assert cropped.window.y1 <= root.height
    assert cropped.image.width <= root.width
    assert cropped.image.height <= root.height
    assert (cropped.image.width, cropped.image.height) == (
        cropped.window.width,
        cropped.window.height,
    )


def test_remap_proposal_returns_root_image_coordinates():
    root = _image()
    cropped = crop_image(root, _component("upper_right"))
    proposal = RegionProposal(
        status=RegionStatus.LOCATED,
        step_id="locate-target",
        component="target",
        image_width=cropped.image.width,
        image_height=cropped.image.height,
        point=PixelPoint(x=200, y=200),
        box=PixelBox(x1=100, y1=100, x2=300, y2=300),
        evidence="visible",
    )

    remapped = remap_proposal(proposal, cropped)

    assert remapped.image_width == root.width
    assert remapped.image_height == root.height
    assert remapped.point == PixelPoint(x=600, y=200)
    assert remapped.box == PixelBox(x1=500, y1=100, x2=700, y2=300)


def test_remap_proposal_rejects_mismatched_crop_dimensions():
    root = _image()
    cropped = crop_image(root, _component("upper_right"))
    proposal = RegionProposal(
        status=RegionStatus.NOT_VISIBLE,
        step_id="locate-target",
        component="target",
        image_width=cropped.image.width - 1,
        image_height=cropped.image.height,
        point=None,
        box=None,
        evidence="not visible",
    )

    with pytest.raises(ValueError, match="dimensions"):
        remap_proposal(proposal, cropped)
