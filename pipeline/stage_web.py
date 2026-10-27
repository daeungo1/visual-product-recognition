"""Stage only the public static demo files, never the API or arbitrary assets."""

import argparse
import shutil
from pathlib import Path

ENTRY_PAGES = ("ar-demo.html", "photo-demo.html", "product-demo.html")
DEFAULT_ENTRY = "ar-demo.html"

AR_MODULES = (
    "ar/app.js",
    "ar/budget.js",
    "ar/camera.js",
    "ar/features.js",
    "ar/geometry.js",
    "ar/guide.js",
    "ar/image.js",
    "ar/overlay.js",
    "ar/session.js",
    "ar/synthetic.js",
    "ar/tracker.js",
)

PUBLIC_FILES = (
    "ar-demo.html",
    "photo-demo.html",
    "product-demo.html",
    "demo-target.html",
    "demo-target.png",
    "staticwebapp.config.json",
    "products/catalog.json",
    "scenarios/catalog.json",
    "scenarios/aircon.png",
    "scenarios/washer.png",
    "scenarios/refrigerator.png",
    "scenarios/monitor.png",
    *AR_MODULES,
)


def stage_web(assets: Path, output: Path, *, entry: str = DEFAULT_ENTRY) -> None:
    assets = assets.resolve()
    if output.resolve().is_relative_to(assets):
        raise ValueError("The public output must be outside the source assets.")
    if entry not in ENTRY_PAGES:
        raise ValueError("Unknown public home page.")
    for name in PUBLIC_FILES:
        source = assets / name
        if not source.is_file():
            raise FileNotFoundError(source)
        if not source.resolve().is_relative_to(assets):
            raise ValueError(f"Public source is outside the assets: {name}")
    output.mkdir(parents=True, exist_ok=False)
    for name in PUBLIC_FILES:
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(assets / name, destination)
    shutil.copyfile(assets / entry, output / "index.html")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assets", type=Path, default=Path(__file__).resolve().parents[1] / "assets"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--entry", choices=ENTRY_PAGES, default=DEFAULT_ENTRY)
    return parser


def main() -> int:
    args = create_parser().parse_args()
    stage_web(args.assets, args.output, entry=args.entry)
    print(f"Staged {len(PUBLIC_FILES) + 1} public files at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
