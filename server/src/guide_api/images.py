"""Bounded, validated JPEG/PNG inputs shared by HTTP and owner registration."""

import base64
import binascii
import io
import warnings
from dataclasses import dataclass

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 8_000_000
MAX_BASE64_LENGTH = 4 * ((MAX_IMAGE_BYTES + 2) // 3)


@dataclass(frozen=True)
class ImageInput:
    data: bytes
    mime: str
    width: int
    height: int

    def rgb(self) -> Image.Image:
        with Image.open(io.BytesIO(self.data)) as image:
            return image.convert("RGB")

    def data_url(self) -> str:
        return f"data:{self.mime};base64,{base64.b64encode(self.data).decode('ascii')}"


def image_bytes(data: bytes) -> ImageInput:
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Decoded image exceeds 2 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise HTTPException(422, "Only JPEG and PNG images are accepted.")
                width, height = image.size
                if width * height > MAX_IMAGE_PIXELS:
                    raise HTTPException(413, "Image exceeds 8 megapixels.")
                mime = "image/jpeg" if image.format == "JPEG" else "image/png"
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(413, "Image exceeds safe dimensions.") from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise HTTPException(422, "Invalid JPEG or PNG image.") from error
    return ImageInput(data, mime, width, height)


def decode_image(encoded: str) -> ImageInput:
    if len(encoded) > MAX_BASE64_LENGTH:
        raise HTTPException(413, "Base64 image exceeds 2 MiB decoded limit.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(422, "Invalid raw base64 image.") from error
    return image_bytes(raw)
