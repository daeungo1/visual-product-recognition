#!/usr/bin/env python3
"""Run reviewed WD80H25BHS multi-target grounding evaluation."""

import argparse
import json
import os
import sys
from pathlib import Path

from visual_guide.evaluation import (
    HybridEvaluationCase,
    evaluate_guide_cases,
    evaluate_hybrid_cases,
    load_guide_evaluation_cases,
)
from visual_guide.issue_contracts import (
    IssueResolutionRequest,
    ProductStatus,
    SupportMode,
)
from visual_guide.issue_planner import FoundryIssuePlanner
from visual_guide.issue_service import IssueResolutionService, ResolutionSigner
from visual_guide.model_gateway import build_foundry_gateway
from visual_guide.orchestrator import GuideGroundingService
from visual_guide.registry import load_reviewed_registry


def create_parser() -> argparse.ArgumentParser:
    """Create the evaluation CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("reviewed", "hybrid"),
        default="reviewed",
    )
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


def load_hybrid_cases(path: Path, images: Path) -> list[HybridEvaluationCase]:
    """Load free-form issue cases with separate expected layers."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        HybridEvaluationCase(
            case_id=row["case_id"],
            request=IssueResolutionRequest(
                product_hint=row["product_hint"],
                model_code=row["model_code"],
                user_issue=row["user_issue"],
                current_state=row["current_state"],
            ),
            image_path=images / row["image"] if row["image"] else None,
            expected_product_status=ProductStatus(row["expected_product_status"]),
            expected_product_id=row["expected_product_id"],
            expected_issue_intent=row["expected_issue_intent"],
            expected_targets=frozenset(row["expected_targets"]),
            expected_support_mode=SupportMode(row["expected_support_mode"]),
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
    registry = load_reviewed_registry(args.references)
    if args.mode == "hybrid":
        report = evaluate_hybrid_cases(
            load_hybrid_cases(args.cases, args.images),
            service=IssueResolutionService(
                planner=FoundryIssuePlanner(
                    client=gateway.client,
                    deployment=args.deployment,
                ),
                registry=registry,
                signer=ResolutionSigner("local-evaluation-resolution-secret"),
            ),
            output=args.output,
            deployment=args.deployment,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    service = GuideGroundingService(
        registry=registry,
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
