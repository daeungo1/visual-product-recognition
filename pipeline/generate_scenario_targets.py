"""Render owned synthetic appliance panels from the shared demo catalog."""

import argparse
import json
import subprocess
from pathlib import Path

from generate_reference_texture import create_texture
from PIL import Image, ImageDraw, ImageFont

LABELS = {
    "aircon": "SYNTHETIC AIRCON",
    "washer": "SYNTHETIC WASHER",
    "refrigerator": "SYNTHETIC FRIDGE",
    "monitor": "SYNTHETIC MONITOR",
}
SEEDS = {"aircon": 20261026, "washer": 20262035, "refrigerator": 20265001, "monitor": 20265002}


def render(scenario: dict, seed: int) -> Image.Image:
    image = create_texture(seed)
    draw = ImageDraw.Draw(image)
    font_path = Path(r"C:\Windows\Fonts\arialbd.ttf")
    font = (
        ImageFont.truetype(str(font_path), 22)
        if font_path.is_file()
        else ImageFont.load_default(size=22)
    )
    small = (
        ImageFont.truetype(str(font_path), 18)
        if font_path.is_file()
        else ImageFont.load_default(size=18)
    )
    draw.rounded_rectangle((24, 8, 376, 72), radius=12, fill="white", outline="black", width=3)
    draw.text((36, 27), LABELS[scenario["id"]], font=font, fill="black")
    draw.rounded_rectangle((28, 94, 372, 571), radius=18, outline="white", width=5)
    left, top, right, bottom = scenario["display"]
    draw.rectangle((left * 400, top * 640, right * 400 - 1, bottom * 640), fill="white")
    for index, control in enumerate(scenario["controls"]):
        draw.text((48, 120 + index * 36), control["initial"], font=font, fill="black")
        left, top, right, bottom = control["rect"]
        draw.rounded_rectangle(
            (left * 400, top * 640, right * 400 - 1, bottom * 640 - 1),
            radius=10, fill="white", outline="black", width=2,
        )
        draw.text(
            (left * 400 + 25, top * 640 + 18),
            f"{index + 1}  {control['label']}", font=font, fill="black",
        )
    draw.rectangle((22, 591, 378, 627), fill="white")
    draw.text((31, 600), "DEMO - NOT A SAMSUNG PRODUCT", font=small, fill="black")
    return image


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assets", type=Path, default=Path(__file__).resolve().parents[1] / "assets",
    )
    parser.add_argument("--arcoreimg", type=Path)
    return parser


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()
    catalog = json.loads((args.assets / "scenarios" / "catalog.json").read_text(encoding="utf-8"))
    if catalog.get("demo") is not True:
        parser.error("Only the owned synthetic demo catalog may be rendered.")
    for scenario in catalog["scenarios"]:
        if scenario["id"] not in LABELS or scenario["image"] != f"scenarios/{scenario['id']}.png":
            parser.error("Unexpected synthetic scenario image path.")
        destination = args.assets / "scenarios" / f"{scenario['id']}.png"
        with render(scenario, SEEDS[scenario["id"]]) as image:
            image.save(destination, format="PNG")
        if args.arcoreimg:
            result = subprocess.run(
                [str(args.arcoreimg.resolve()), "eval-img", "--input_image_path", str(destination)],
                capture_output=True, text=True, check=True,
            )
            score = int(result.stdout.strip())
            if score < 75:
                raise ValueError(f"Synthetic {scenario['id']} ARCore score {score} is below 75.")
            print(f"Synthetic {scenario['id']}: ARCore reference quality {score}")
        else:
            print(f"Generated synthetic {scenario['id']}; ARCore quality not checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
