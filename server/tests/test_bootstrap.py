"""Private-network bootstrap tests with injected credentials and persistence."""

import hashlib
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_cloud import MemoryDocuments

from guide_api import bootstrap
from guide_api.azure_adapters import Settings
from guide_api.cloud import NotFound
from guide_api.operator_errors import OperatorFailure

NOW = 1_790_000_000.0
PHONE_CODE = "phone-code-that-must-never-reach-job-logs"
DIGEST = hashlib.sha256(PHONE_CODE.encode()).hexdigest()


def settings():
    return Settings(
        "https://cosmos.example.org",
        "https://storage.example.org",
        "https://search.example.org",
        "https://openai.example.org",
        "setup-uami-client-id",
    )


def dependencies():
    documents = MemoryDocuments()
    documents.close = Mock()
    credential = Mock()
    helpers = SimpleNamespace(
        register=Mock(return_value={"status": "prepared_not_indexed"}),
        activate=Mock(return_value={"indexed": 1, "dimensions": 768}),
        require_indexed=Mock(),
    )
    return documents, credential, helpers


def run(config, dependencies):
    documents, credential, helpers = dependencies
    credential_factory = Mock(return_value=credential)
    result = bootstrap.run_bootstrap(
        config,
        settings=settings(),
        helpers=helpers,
        credential_factory=credential_factory,
        documents_factory=Mock(return_value=documents),
        clock=lambda: NOW,
    )
    credential_factory.assert_called_once_with(client_id="setup-uami-client-id")
    documents.close.assert_called_once()
    credential.close.assert_called_once()
    return result


def test_prepare_uses_setup_managed_identity_and_existing_registration_helper():
    deps = dependencies()
    result = run(bootstrap.BootstrapConfig(operation="prepare"), deps)
    documents, credential, helpers = deps
    args, actual_settings, actual_credential, actual_documents = helpers.register.call_args.args
    assert args.seed_demo is True
    assert actual_settings == settings()
    assert actual_credential is credential and actual_documents is documents
    helpers.activate.assert_not_called()
    assert result["prepared_targets"] == 1
    assert not any(container == "invites" for container, _ in documents.items)


def test_activate_issues_only_the_supplied_hash_after_successful_indexing(caplog):
    deps = dependencies()
    with caplog.at_level(logging.INFO):
        result = run(
            bootstrap.BootstrapConfig(
                operation="activate",
                api_url="https://api.example.org",
                invite_hash=DIGEST,
                invite_expires_at=NOW + 3600,
            ),
            deps,
        )
    documents, _, helpers = deps
    helpers.activate.assert_called_once_with("https://api.example.org", documents)
    invitation = documents.read("invites", DIGEST)
    assert {key: value for key, value in invitation.items() if not key.startswith("_")} == {
        "id": DIGEST,
        "kind": "invite",
        "scope": "device",
        "expires_at": NOW + 3600,
        "ttl": 3600,
    }
    assert result["indexed"] == 1 and result["device_invite_created"] is True
    assert PHONE_CODE not in caplog.text and DIGEST not in caplog.text


def test_activate_failure_never_creates_device_invite():
    deps = dependencies()
    deps[2].activate.side_effect = RuntimeError("Indexing failed")
    with pytest.raises(RuntimeError):
        run(
            bootstrap.BootstrapConfig(
                operation="activate",
                api_url="https://api.example.org",
                invite_hash=DIGEST,
                invite_expires_at=NOW + 3600,
            ),
            deps,
        )
    assert not deps[0].items


def test_invite_mode_checks_existing_index_and_never_reindexes():
    deps = dependencies()
    run(
        bootstrap.BootstrapConfig(
            operation="invite",
            invite_hash=DIGEST,
            invite_expires_at=NOW + 3600,
        ),
        deps,
    )
    deps[2].require_indexed.assert_called_once()
    deps[2].activate.assert_not_called()
    assert deps[0].read("invites", DIGEST)["scope"] == "device"


def test_invitation_retry_is_idempotent_but_consumed_code_is_never_resurrected():
    documents = MemoryDocuments()
    assert bootstrap.issue_device_invite(documents, DIGEST, NOW + 3600, now=NOW)
    assert not bootstrap.issue_device_invite(documents, DIGEST, NOW + 3600, now=NOW + 1)
    invitation = documents.read("invites", DIGEST)
    documents.delete("invites", DIGEST, invitation["_etag"])
    with pytest.raises(ValueError, match="fresh"):
        bootstrap.issue_device_invite(documents, DIGEST, NOW + 3600, now=NOW + 2)
    with pytest.raises(NotFound):
        documents.read("invites", DIGEST)


@pytest.mark.parametrize(
    "digest,expiry",
    [
        (PHONE_CODE, NOW + 3600),
        ("a" * 63, NOW + 3600),
        (DIGEST, NOW),
        (DIGEST, NOW + 168 * 3600 + 1),
        (DIGEST, float("nan")),
    ],
)
def test_bad_hash_or_expiry_is_rejected_before_network(digest, expiry):
    deps = dependencies()
    with pytest.raises(ValueError):
        run(
            bootstrap.BootstrapConfig(
                operation="invite",
                invite_hash=digest,
                invite_expires_at=expiry,
            ),
            deps,
        )
    assert not deps[0].items


def test_environment_contract_requires_explicit_operation_and_hash_pair():
    config = bootstrap.BootstrapConfig.from_environment(
        {
            "BOOTSTRAP_OPERATION": "activate",
            "BOOTSTRAP_API_URL": "https://api.example.org",
            "BOOTSTRAP_DEVICE_INVITE_HASH": DIGEST,
            "BOOTSTRAP_INVITE_EXPIRES_AT": str(NOW + 3600),
        }
    )
    assert config.invite_hash == DIGEST and config.invite_expires_at == NOW + 3600
    with pytest.raises(ValueError):
        bootstrap.BootstrapConfig.from_environment({})
    with pytest.raises(ValueError):
        bootstrap.BootstrapConfig.from_environment(
            {
                "BOOTSTRAP_OPERATION": "invite",
                "BOOTSTRAP_DEVICE_INVITE_HASH": DIGEST,
            }
        )


def test_entrypoint_errors_log_type_not_exception_payload(monkeypatch, caplog):
    monkeypatch.setenv("BOOTSTRAP_OPERATION", "prepare")
    monkeypatch.setattr(
        bootstrap,
        "run_bootstrap",
        Mock(side_effect=OperatorFailure(PHONE_CODE)),
    )
    assert bootstrap.main() == 1
    assert PHONE_CODE not in caplog.text and "OperatorFailure" in caplog.text


def test_curated_helper_uses_the_same_canonical_registration_code():
    root = Path(__file__).resolve().parents[2]
    helpers = bootstrap.load_owner_helpers(root / "pipeline" / "provision_cloud.py")
    assert helpers.ROOT == root
    assert callable(helpers.register) and callable(helpers.activate)
