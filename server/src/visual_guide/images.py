"""Bound and decode user-consented image snapshots."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 8_000_000
SUPPORTED_MIME = {"image/jpeg", "image/png"}


@dataclass(frozen=True)
class ImageInput:
    """Validated encoded image and its sent pixel dimensions."""

    data: bytes
    mime: str
    width: int
    height: int


def decode_image(data: bytes, mime: str) -> ImageInput:
    """Validate a bounded JPEG or PNG without retaining decoded pixels."""
    if mime not in SUPPORTED_MIME:
        raise ValueError("Only JPEG and PNG images are accepted.")
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Image exceeds the encoded byte limit.")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("Content is not a valid image.") from error
    if width * height > MAX_PIXELS:
        raise ValueError("Image exceeds the megapixels limit.")
    return ImageInput(data=data, mime=mime, width=width, height=height)
