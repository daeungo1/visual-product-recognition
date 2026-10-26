#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
"""Generate owned multiscale reference texture with ``--output PATH``."""

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont


def create_texture(seed: int = 20261021) -> Image.Image:
    """Return unique grayscale features at camera-visible scales, without repeated tiles."""
    random_source = random.Random(seed)
    canvas = Image.new("L", (400, 640), 128)
    for scale in (64, 32, 16, 8):
        size = (400 // scale + 1, 640 // scale + 1)
        noise = Image.frombytes(
            "L", size, bytes(random_source.randrange(256) for _ in range(size[0] * size[1])),
        )
        canvas = Image.blend(canvas, noise.resize((400, 640), Image.Resampling.BICUBIC), 0.55)
    return ImageEnhance.Contrast(canvas).enhance(3).convert("RGB")


def create_reference(panel: dict) -> Image.Image:
    """Render the owned Windows demo with the same normalized panel geometry."""
    if (panel["width_pixels"], panel["height_pixels"]) != (400, 640):
        raise ValueError("The dedicated demo layout requires a 400 by 640 panel map.")
    image = create_texture()
    draw = ImageDraw.Draw(image)
    font_path = str(Path(r"C:\Windows\Fonts\arialbd.ttf"))
    font = ImageFont.truetype(font_path, 23)
    title_font = ImageFont.truetype(font_path, 24)
    draw.rectangle((45, 18, 354, 60), fill="white")
    draw.text((77, 24), "ORIGINAL DEMO", font=title_font, fill="black")
    left, top, right, bottom = panel["display"]
    draw.rectangle((left * 400, top * 640, right * 400 - 1, bottom * 640), fill="white")
    draw.multiline_text(
        (66, 101), "POWER OFF\nMODE FAN\nTEMP 26", font=font, fill="black", spacing=4,
    )
    for button_id, label in (
        ("power", "1  POWER"), ("mode", "2  MODE"), ("temperature", "3  TEMP"),
    ):
        left, top, right, bottom = panel["buttons"][button_id]
        draw.rectangle(
            (left * 400, top * 640, right * 400 - 1, bottom * 640 - 1),
            fill="white", outline="black", width=1,
        )
        draw.text((int(left * 400) + 45, int(top * 640) + 18), label, font=font, fill="black")
    draw.rectangle((32, 583, 367, 614), fill="white")
    draw.text((43, 585), "NOT A REAL PRODUCT", font=font, fill="black")
    return image


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--panel-map", type=Path, required=True)
    arguments = parser.parse_args()
    with create_reference(json.loads(arguments.panel_map.read_text(encoding="utf-8"))) as texture:
        texture.save(arguments.output, format="PNG")
