from io import BytesIO

import pytest
from PIL import Image

from visual_guide.images import ImageInput, decode_image


def png(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), color="white").save(output, format="PNG")
    return output.getvalue()


def test_decode_image_preserves_sent_pixel_dimensions():
    image = decode_image(png(1200, 1600), "image/png")

    assert image == ImageInput(data=png(1200, 1600), mime="image/png", width=1200, height=1600)


@pytest.mark.parametrize("mime", ["image/gif", "image/svg+xml"])
def test_decode_image_rejects_unsupported_media(mime):
    with pytest.raises(ValueError, match="JPEG and PNG"):
        decode_image(png(10, 10), mime)


def test_decode_image_rejects_too_many_pixels():
    with pytest.raises(ValueError, match="megapixels"):
        decode_image(png(3000, 3000), "image/png")


def test_decode_image_rejects_corrupt_content():
    with pytest.raises(ValueError, match="valid image"):
        decode_image(b"not-an-image", "image/png")
