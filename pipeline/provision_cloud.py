#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
"""Register owner-reviewed assets and privately issue one-time pairing codes.

Run using the server environment, for example:
    uv run --project server python pipeline\\provision_cloud.py --help

This manages application data and the Search index only, never Azure resources or RBAC.
It requires an existing Azure CLI login and uses AzureCliCredential explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from guide_api.azure_adapters import (
    CosmosDocuments,
    Settings,
    azure_errors,
    search_index,
)
from guide_api.catalog import DEMO_GUIDE
from guide_api.cloud import token_hash
from guide_api.operator_errors import (
    SERVICE_FAILURES,
    OperatorFailure,
    log_operator_failure,
)
from guide_api.registration import (
    check_registration,
    registration_documents,
    store_registration,
)

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--seed-demo", action="store_true")
    modes.add_argument("--register-real", action="store_true")
    modes.add_argument("--issue-device-code", action="store_true")
    modes.add_argument("--activate-only", action="store_true")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Register assets and create Search schema without calling an API or issuing any code",
    )
    parser.add_argument(
        "--api-url",
        help="Deployed HTTPS API origin, no /v1 suffix; not needed for prepare-only",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="New file in an explicitly supplied git-ignored private directory",
    )
    parser.add_argument(
        "--code-valid-hours",
        type=int,
        default=24,
        choices=range(1, 169),
        metavar="1..168",
    )
    parser.add_argument("--guide", type=Path)
    parser.add_argument("--panel-map", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--product-id")
    parser.add_argument("--model")
    parser.add_argument("--category", choices=("aircon", "tv", "airdresser"))
    parser.add_argument("--target-kind", choices=("body", "remote", "screen"))
    parser.add_argument("--source-url")
    parser.add_argument(
        "--reviewed",
        action="store_true",
        help="Confirm human review of the source, applicable model and coordinates",
    )
    return parser


def validate_output(path: Path) -> Path:
    path = path.absolute()
    if path.exists() or path.is_symlink():
        raise ValueError(
            "Output must be a new private file, never an existing file or symlink."
        )
    if not path.parent.is_dir():
        raise ValueError("Create the private output directory before issuing a code.")
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(path)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            "Pair-code output must be git-ignored; never write it into source."
        )
    return path


def private_write(path: Path, value: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def invite(documents, scope: str, lifetime: int) -> tuple[str, float]:
    code = secrets.token_urlsafe(32)
    expires_at = time.time() + lifetime
    documents.create(
        "invites",
        {
            "id": token_hash(code),
            "kind": "invite",
            "scope": scope,
            "expires_at": expires_at,
            "ttl": lifetime,
        },
    )
    return code, expires_at


def versioned_demo_assets(reference: bytes, panel: dict) -> tuple[dict, dict]:
    """Publish revised demo pixels under new IDs, preserving immutable existing assets."""
    version = hashlib.sha256(reference).hexdigest()[:12]
    guide = DEMO_GUIDE.model_dump()
    guide["id"] += f"-{version}"
    guide["target_id"] += f"-{version}"
    guide["title"] += f" (reference {version})"
    return guide, {**panel, "target_id": guide["target_id"]}


def reindex(api_url: str, documents) -> dict:
    import httpx

    code, _ = invite(documents, "admin", 300)
    with httpx.Client(timeout=120, follow_redirects=False) as client:
        response = client.post(api_url + "/v1/pair", json={"code": code})
        if response.status_code != 200:
            raise OperatorFailure.from_response(response)
        paired = response.json()
        try:
            response = client.post(
                api_url + "/v1/admin/reindex",
                headers={
                    "Authorization": "Bearer " + paired["access_token"],
                },
            )
            if response.status_code != 200:
                raise OperatorFailure.from_response(response)
            return response.json()
        finally:
            # The owner helper needs admin scope only for this one operation.
            from guide_api.cloud import NotFound

            key = token_hash(paired["access_token"])
            try:
                device = documents.read("devices", key)
                documents.delete("devices", key, device["_etag"])
            except NotFound:
                pass


def register(args, settings, credential, documents) -> dict:
    from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
    from azure.search.documents.indexes import SearchIndexClient
    from azure.storage.blob import BlobServiceClient, ContentSettings

    if args.seed_demo:
        panel = json.loads(
            (ROOT / "assets" / "panel_map.json").read_text(encoding="utf-8")
        )
        reference = (ROOT / "assets" / "demo-target.png").read_bytes()
        guide, panel = versioned_demo_assets(reference, panel)
        metadata = {
            "product_id": "demo-aircon",
            "model": "Original synthetic demo",
            "category": "aircon",
            "target_kind": "remote",
            "source_url": None,
            "reviewed": True,
        }
    else:
        required = (
            "guide",
            "panel_map",
            "reference",
            "product_id",
            "model",
            "category",
            "target_kind",
            "source_url",
        )
        if not args.reviewed or any(getattr(args, name) is None for name in required):
            raise ValueError(
                "Real registration needs all asset/metadata flags and --reviewed."
            )
        guide = json.loads(args.guide.read_text(encoding="utf-8"))
        if guide.get("demo") is not False:
            raise ValueError("--register-real requires guide.demo=false.")
        panel = json.loads(args.panel_map.read_text(encoding="utf-8"))
        reference = args.reference.read_bytes()
        metadata = {
            name: getattr(args, name)
            for name in (
                "product_id",
                "model",
                "category",
                "target_kind",
                "source_url",
                "reviewed",
            )
        }
    target, guide_document, image = registration_documents(
        guide=guide,
        panel=panel,
        reference=reference,
        **metadata,
    )
    check_registration(documents, target, guide_document)
    with BlobServiceClient(
        settings.storage_url,
        credential=credential,
        connection_timeout=10,
        read_timeout=30,
    ) as blobs:
        blob = blobs.get_blob_client(settings.blob_container, target["reference_blob"])
        with azure_errors("blob"):
            try:
                blob.upload_blob(
                    reference,
                    overwrite=False,
                    content_settings=ContentSettings(content_type=image.mime),
                    metadata={"sha256": target["reference_sha256"]},
                )
            except ResourceExistsError:
                existing = blob.get_blob_properties()
                if existing.metadata.get("sha256") != target[
                    "reference_sha256"
                ] or existing.size != len(reference):
                    raise ValueError(
                        "Existing reference blob differs; refusing overwrite."
                    ) from None
    store_registration(documents, target, guide_document)
    with SearchIndexClient(
        settings.search_endpoint,
        credential,
        connection_timeout=10,
        read_timeout=30,
    ) as indexes:
        with azure_errors("search"):
            try:
                existing = indexes.get_index(settings.search_index)
            except ResourceNotFoundError:
                indexes.create_index(search_index(settings.search_index))
            else:
                expected = search_index(settings.search_index)
                existing_fields = {field.name: field for field in existing.fields}
                for field in expected.fields:
                    found = existing_fields.get(field.name)
                    if (
                        not found
                        or found.type != field.type
                        or found.vector_search_dimensions
                        != field.vector_search_dimensions
                        or found.vector_search_profile_name
                        != field.vector_search_profile_name
                        or bool(found.key) != bool(field.key)
                        or bool(found.filterable) != bool(field.filterable)
                        or bool(found.searchable) != bool(field.searchable)
                    ):
                        raise ValueError(
                            "Existing Search schema differs; refusing destructive update."
                        )
                vector_search = existing.vector_search
                if (
                    not vector_search
                    or not any(
                        profile.name == "siglip2-cosine"
                        and profile.algorithm_configuration_name == "siglip2-hnsw"
                        for profile in vector_search.profiles
                    )
                    or not any(
                        algorithm.name == "siglip2-hnsw"
                        and algorithm.parameters.metric == "cosine"
                        for algorithm in vector_search.algorithms
                    )
                ):
                    raise ValueError("Existing Search HNSW/cosine schema differs.")
    return {
        "prepared_target": target["target_id"],
        "search_index": settings.search_index,
        "status": "prepared_not_indexed",
    }


def activate(api_url: str, documents) -> dict:
    result = reindex(api_url.rstrip("/"), documents)
    if result.get("indexed", 0) <= 0:
        raise ValueError(
            "Activation indexed no targets. A device invite will not be issued."
        )
    return result


def require_indexed(settings, credential) -> None:
    from azure.search.documents import SearchClient

    with SearchClient(
        settings.search_endpoint, settings.search_index, credential
    ) as search:
        with azure_errors("search"):
            if search.get_document_count() <= 0:
                raise ValueError(
                    "Activate/reindex successfully before issuing device invitations."
                )


def run(args) -> int:
    from azure.identity import AzureCliCredential

    if args.prepare_only and not (args.seed_demo or args.register_real):
        raise ValueError("--prepare-only requires --seed-demo or --register-real.")
    output = None
    if not args.prepare_only:
        if not args.api_url or not args.output:
            raise ValueError(
                "Activation/code issuance requires --api-url and --output."
            )
        origin = urlparse(args.api_url)
        if (
            origin.scheme != "https"
            or not origin.netloc
            or origin.path not in {"", "/"}
        ):
            raise ValueError("--api-url must be an HTTPS origin without a path.")
        if origin.username or origin.password or origin.query or origin.fragment:
            raise ValueError(
                "--api-url cannot contain credentials, query strings or fragments."
            )
        output = validate_output(args.output)
    settings = Settings.from_environment()
    with AzureCliCredential(process_timeout=120) as credential:
        documents = CosmosDocuments(
            settings.cosmos_endpoint, settings.database, credential
        )
        try:
            if args.seed_demo or args.register_real:
                summary = register(args, settings, credential, documents)
                print(json.dumps(summary, ensure_ascii=False))
            if args.prepare_only:
                return 0
            if args.issue_device_code:
                require_indexed(settings, credential)
            else:
                summary = activate(args.api_url, documents)
                print(json.dumps(summary, ensure_ascii=False))
            code, expires_at = invite(documents, "device", args.code_valid_hours * 3600)
            private_write(
                output,
                {
                    "api_url": args.api_url.rstrip("/"),
                    "code": code,
                    "scope": "device",
                    "expires_at": expires_at,
                },
            )
        finally:
            documents.close()
    print(
        "Device pairing invitation written to the explicitly supplied private output file."
    )
    return 0


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    # SDK debug logging can expose bearer tokens or image request bodies.
    logging.getLogger("azure").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        return run(create_parser().parse_args())
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError) as error:
        log_operator_failure(LOGGER, "owner_cli", error)
        return 2
    except SERVICE_FAILURES as error:
        log_operator_failure(LOGGER, "owner_cli", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
