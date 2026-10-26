"""Managed-identity application-data setup inside the private Container Apps network.

Run with ``python -m guide_api.bootstrap`` in the curated API image. This creates no
Azure resources and never enables public data endpoints or accepts plaintext phone codes.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import os
import re
import sys
import time
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from guide_api.azure_adapters import CosmosDocuments, Settings
from guide_api.cloud import Conflict, NotFound
from guide_api.operator_errors import SERVICE_FAILURES, log_operator_failure

LOGGER = logging.getLogger(__name__)
MAX_INVITE_SECONDS = 168 * 3600


def _invite_ttl(digest: str, expires_at: float, now: float) -> int:
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("A lowercase SHA-256 hexadecimal invitation hash is required.")
    if not math.isfinite(expires_at) or not now < expires_at <= now + MAX_INVITE_SECONDS:
        raise ValueError("Invitation expiry must be in the future and at most 168 hours away.")
    return math.ceil(expires_at - now)


@dataclass(frozen=True)
class BootstrapConfig:
    operation: str
    api_url: str | None = None
    invite_hash: str | None = None
    invite_expires_at: float | None = None

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None):
        environ = os.environ if environ is None else environ
        operation = environ.get("BOOTSTRAP_OPERATION")
        if operation not in {"prepare", "activate", "invite"}:
            raise ValueError("BOOTSTRAP_OPERATION must be prepare, activate or invite.")
        digest = environ.get("BOOTSTRAP_DEVICE_INVITE_HASH")
        expiry = environ.get("BOOTSTRAP_INVITE_EXPIRES_AT")
        if (digest is None) != (expiry is None):
            raise ValueError("Invitation hash and expiry must be supplied together.")
        return cls(
            operation=operation,
            api_url=environ.get("BOOTSTRAP_API_URL"),
            invite_hash=digest,
            invite_expires_at=float(expiry) if expiry is not None else None,
        )

    def validate(self, now: float) -> None:
        if self.operation not in {"prepare", "activate", "invite"}:
            raise ValueError("Unsupported bootstrap operation.")
        if (self.invite_hash is None) != (self.invite_expires_at is None):
            raise ValueError("Invitation hash and expiry must be supplied together.")
        if self.operation == "prepare" and self.invite_hash is not None:
            raise ValueError("Preparation never accepts device invitation data.")
        if self.operation == "invite" and self.invite_hash is None:
            raise ValueError("Invite operation requires a hash and expiry.")
        if self.invite_hash is not None:
            _invite_ttl(self.invite_hash, self.invite_expires_at, now)
        if self.operation == "activate" and not self.api_url:
            raise ValueError("Activation requires BOOTSTRAP_API_URL.")
        if self.api_url:
            origin = urlparse(self.api_url)
            if (
                origin.scheme != "https"
                or not origin.netloc
                or origin.path not in {"", "/"}
                or origin.username
                or origin.password
                or origin.query
                or origin.fragment
            ):
                raise ValueError("BOOTSTRAP_API_URL must be an HTTPS origin without credentials.")


def load_owner_helpers(path: Path | None = None):
    path = path or Path("/app") / "pipeline" / "provision_cloud.py"
    spec = importlib.util.spec_from_file_location("visual_guide_bootstrap_owner", path)
    if spec is None or spec.loader is None:
        raise ValueError("Curated owner helpers are not packaged.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def issue_device_invite(documents, digest: str, expires_at: float, *, now: float) -> bool:
    """Create the canonical invitation without resurrecting a consumed one on job retry."""
    ttl = _invite_ttl(digest, expires_at, now)
    invitation = {
        "id": digest,
        "kind": "invite",
        "scope": "device",
        "expires_at": expires_at,
        "ttl": ttl,
    }
    # Pairing deletes invitations atomically. A separate hash-only claim must survive that
    # deletion, otherwise retrying the same job could turn a consumed code into a fresh one.
    claim = {
        "id": f"bootstrap-invite:{digest}",
        "kind": "bootstrap_invite",
        "invite_id": digest,
        "expires_at": expires_at,
    }
    claimed = False
    try:
        documents.create("catalog", claim)
        claimed = True
    except Conflict:
        existing = documents.read("catalog", claim["id"])
        if any(existing.get(key) != value for key, value in claim.items()):
            raise ValueError("Invitation claim differs; generate a fresh local code.") from None
    if claimed:
        try:
            documents.create("invites", invitation)
            return True
        except Conflict:
            pass
    try:
        existing = documents.read("invites", digest)
    except NotFound as error:
        # Fail closed after consumption or a crash between claiming and creating. A new
        # local code is cheap; silently reminting a consumed one would break one-time auth.
        raise ValueError(
            "Invitation already used or reserved; generate a fresh local code."
        ) from error
    if any(
        existing.get(key) != invitation[key]
        for key in (
            "id",
            "kind",
            "scope",
            "expires_at",
        )
    ):
        raise ValueError("Invitation differs; generate a fresh local code.")
    return False


def run_bootstrap(
    config: BootstrapConfig,
    *,
    settings: Settings | None = None,
    helpers=None,
    credential_factory=None,
    documents_factory=CosmosDocuments,
    clock=time.time,
) -> dict:
    config.validate(clock())
    settings = settings or Settings.from_environment()
    if not settings.client_id:
        raise ValueError("AZURE_CLIENT_ID must identify the dedicated setup managed identity.")
    if credential_factory is None:
        from azure.identity import ManagedIdentityCredential

        credential_factory = ManagedIdentityCredential
    helpers = helpers or load_owner_helpers()
    with ExitStack() as cleanup:
        credential = credential_factory(client_id=settings.client_id)
        cleanup.callback(credential.close)
        documents = documents_factory(settings.cosmos_endpoint, settings.database, credential)
        cleanup.callback(documents.close)
        result = {"operation": config.operation, "status": "completed"}
        if config.operation == "prepare":
            helpers.register(SimpleNamespace(seed_demo=True), settings, credential, documents)
            result["prepared_targets"] = 1
        elif config.operation == "activate":
            indexed = helpers.activate(config.api_url.rstrip("/"), documents)
            if not isinstance(indexed.get("indexed"), int) or indexed["indexed"] <= 0:
                raise ValueError("Activation must index a positive number of registered targets.")
            result["indexed"] = indexed["indexed"]
        else:
            helpers.require_indexed(settings, credential)
        if config.invite_hash is not None:
            result["device_invite_created"] = issue_device_invite(
                documents,
                config.invite_hash,
                config.invite_expires_at,
                now=clock(),
            )
    LOGGER.info(
        "bootstrap operation=%s status=completed prepared_targets=%d indexed=%d invite_created=%s",
        config.operation,
        result.get("prepared_targets", 0),
        result.get("indexed", 0),
        result.get("device_invite_created", False),
    )
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    for name in ("azure", "httpx", "httpcore", "openai"):
        logging.getLogger(name).setLevel(logging.ERROR)
    try:
        run_bootstrap(BootstrapConfig.from_environment())
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError) as error:
        log_operator_failure(LOGGER, "bootstrap", error)
        return 2
    except SERVICE_FAILURES as error:
        log_operator_failure(LOGGER, "bootstrap", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
