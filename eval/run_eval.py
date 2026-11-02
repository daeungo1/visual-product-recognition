#!/usr/bin/env python3
"""Run reviewed WD80H25BHS multi-target grounding evaluation."""

import argparse
import json
import os
import sys
from pathlib import Path

from visual_guide.evaluation import evaluate_guide_cases, load_guide_evaluation_cases
from visual_guide.model_gateway import build_foundry_gateway
from visual_guide.orchestrator import GuideGroundingService
from visual_guide.registry import load_reviewed_registry


def create_parser() -> argparse.ArgumentParser:
    """Create the evaluation CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("eval/cases.json"))
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("eval/ground-truth/WD80H25BHS.json"),
    )
    parser.add_argument("--images", type=Path, default=Path("images"))
    parser.add_argument(
        "--manual",
        type=Path,
        default=Path("images/WD80H25BHS_OID139796_KO.pdf"),
    )
    parser.add_argument(
        "--references",
        type=Path,
        default=Path("server/src/visual_guide/references"),
    )
    parser.add_argument("--output", type=Path, default=Path(".test-data/live-eval"))
    parser.add_argument("--endpoint", default=os.getenv("FOUNDRY_ENDPOINT"))
    parser.add_argument(
        "--deployment",
        default=os.getenv("FOUNDRY_DEPLOYMENT", "gpt-6-1-terra"),
    )
    parser.add_argument("--repeats", type=int, default=3)
    return parser


def main() -> int:
    """Run the evaluation."""
    args = create_parser().parse_args()
    if not args.endpoint:
        print("FOUNDRY_ENDPOINT or --endpoint is required.", file=sys.stderr)
        return 2
    gateway = build_foundry_gateway(args.endpoint, args.deployment)
    service = GuideGroundingService(
        registry=load_reviewed_registry(args.references),
        gateway=gateway,
        manual_paths={"WD80H25BHS": args.manual},
    )
    report = evaluate_guide_cases(
        load_guide_evaluation_cases(
            cases_path=args.cases,
            ground_truth_path=args.ground_truth,
            images=args.images,
        ),
        service=service,
        output=args.output,
        repeats=args.repeats,
        deployment=args.deployment,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
