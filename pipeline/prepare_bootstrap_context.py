#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
"""Package curated bootstrap inputs or issue a local private phone invitation.

No Azure calls, model downloads or dependency installation occur here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CURATED = (
    Path("assets") / "demo-target.png",
    Path("assets") / "panel_map.json",
    Path("pipeline") / "provision_cloud.py",
)


def prepare_context(root: Path = ROOT) -> list[Path]:
    """Copy only the canonical owned files into the ignored server build context."""
    root = root.resolve()
    context = root / "server" / "runtime_bootstrap"
    if not context.resolve().is_relative_to(root):
        raise ValueError("Bootstrap context cannot redirect outside the project.")
    for relative in CURATED:
        source = root / relative
        if (
            not source.is_file()
            or source.is_symlink()
            or not source.resolve().is_relative_to(root)
        ):
            raise ValueError("A canonical bootstrap source is missing or redirected.")
        target = context / relative
        if target.is_symlink() or not target.resolve().is_relative_to(
            context.resolve()
        ):
            raise ValueError(
                "Bootstrap destination cannot redirect outside its context."
            )
    destinations = []
    for relative in CURATED:
        destination = context / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
        destinations.append(destination)
    return destinations


def issue_local_invite(
    output: Path,
    *,
    api_url: str = "",
    valid_hours: int = 24,
    now: float | None = None,
) -> dict:
    """Write plaintext only to a new ignored private file; return only hash and expiry."""
    if type(valid_hours) is not int or not 1 <= valid_hours <= 168:
        raise ValueError("Code validity must be between 1 and 168 hours.")
    if api_url:
        origin = urlparse(api_url)
        if (
            origin.scheme != "https"
            or not origin.netloc
            or origin.path not in {"", "/"}
            or origin.username
            or origin.password
            or origin.query
            or origin.fragment
        ):
            raise ValueError(
                "API URL must be an HTTPS origin or omitted until it is known."
            )
    output = output.absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("Output requires a new file in an existing private directory.")
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if ignored.returncode != 0:
        raise ValueError("Pairing output must be git-ignored.")
    now = time.time() if now is None else now
    if not math.isfinite(now) or now <= 0:
        raise ValueError("A valid current timestamp is required.")
    code = secrets.token_urlsafe(32)
    expires_at = now + valid_hours * 3600
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as private:
        json.dump(
            {
                "api_url": api_url.rstrip("/"),
                "code": code,
                "scope": "device",
                "expires_at": expires_at,
            },
            private,
            indent=2,
        )
        private.write("\n")
    return {
        "BOOTSTRAP_DEVICE_INVITE_HASH": hashlib.sha256(
            code.encode("utf-8")
        ).hexdigest(),
        "BOOTSTRAP_INVITE_EXPIRES_AT": expires_at,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue-device-code", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--api-url", default="")
    parser.add_argument(
        "--code-valid-hours",
        type=int,
        choices=range(1, 169),
        default=24,
        metavar="1..168",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.issue_device_code:
            if args.output is None:
                raise ValueError("Device-code generation requires --output.")
            print(
                json.dumps(
                    issue_local_invite(
                        args.output,
                        api_url=args.api_url,
                        valid_hours=args.code_valid_hours,
                    )
                )
            )
        else:
            if args.output is not None or args.api_url:
                raise ValueError("Output/API arguments require --issue-device-code.")
            files = prepare_context()
            print(json.dumps({"status": "context_prepared", "files": len(files)}))
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError) as error:
        print(f"Bootstrap utility failed: {type(error).__name__}.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
