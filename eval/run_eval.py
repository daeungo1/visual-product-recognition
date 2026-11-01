#!/usr/bin/env python3
"""Run local-only GPT visual-grounding experiments on authorized images."""

import argparse
import json
import os
import sys
from pathlib import Path

from visual_guide.evaluation import EvaluationCase, evaluate_cases
from visual_guide.model_gateway import build_foundry_gateway


def create_parser() -> argparse.ArgumentParser:
    """Create the evaluation CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("eval/cases.json"))
    parser.add_argument("--images", type=Path, default=Path("images"))
    parser.add_argument("--output", type=Path, default=Path(".test-data/live-eval"))
    parser.add_argument("--endpoint", default=os.getenv("FOUNDRY_ENDPOINT"))
    parser.add_argument(
        "--deployment",
        default=os.getenv("FOUNDRY_DEPLOYMENT", "gpt-6-1-terra"),
    )
    parser.add_argument("--repeats", type=int, default=3)
    return parser


def load_cases(path: Path, images: Path) -> list[EvaluationCase]:
    """Load local case metadata without treating product hints as verified guides."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        EvaluationCase(
            case_id=row["case_id"],
            image_path=images / row["image"],
            product_hint=row["product_hint"],
            step_id=row["step_id"],
            component=row["component"],
            instruction=row["instruction"],
        )
        for row in rows
    ]


def main() -> int:
    """Run the evaluation."""
    args = create_parser().parse_args()
    if not args.endpoint:
        print("FOUNDRY_ENDPOINT or --endpoint is required.", file=sys.stderr)
        return 2
    gateway = build_foundry_gateway(args.endpoint, args.deployment)
    report = evaluate_cases(
        load_cases(args.cases, args.images),
        gateway=gateway,
        output=args.output,
        repeats=args.repeats,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
