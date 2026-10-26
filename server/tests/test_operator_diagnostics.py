"""Operator failures expose bounded metadata, never exception messages or HTTP bodies."""

from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError
from fastapi import HTTPException
from test_owner_cli import CLI

from guide_api import bootstrap
from guide_api.operator_errors import OperatorFailure, log_operator_failure

SECRET = "phone-code-token-image-body-must-not-be-logged"
ACTIVITY = "2c052f5b-65f7-4adc-8b02-37bc49d34419"


def configure_cli(monkeypatch, error):
    monkeypatch.setattr(
        CLI,
        "create_parser",
        lambda: SimpleNamespace(parse_args=lambda: None),
    )
    monkeypatch.setattr(CLI, "run", Mock(side_effect=error))


def cosmos_failure():
    error = CosmosHttpResponseError(status_code=403, message=SECRET)
    error.headers = {
        "x-ms-activity-id": ACTIVITY,
        "x-ms-error-code": "Forbidden",
        "x-ms-substatus": "5300",
        "Authorization": "Bearer " + SECRET,
    }
    return error


def test_owner_logs_actual_cosmos_firewall_status_and_activity_not_message(monkeypatch, caplog):
    configure_cli(monkeypatch, cosmos_failure())
    assert CLI.main() == 1
    assert "status_code=403" in caplog.text
    assert "error_code=Forbidden" in caplog.text and ACTIVITY in caplog.text
    assert "sub_status=5300" in caplog.text and SECRET not in caplog.text


def test_wrapped_azure_error_preserves_upstream_metadata(monkeypatch, caplog):
    wrapped = HTTPException(503, SECRET)
    wrapped.__cause__ = cosmos_failure()
    configure_cli(monkeypatch, wrapped)
    assert CLI.main() == 1
    assert "status_code=403" in caplog.text and ACTIVITY in caplog.text
    assert SECRET not in caplog.text


def test_http_status_failure_does_not_log_request_or_response_body(monkeypatch, caplog):
    response = httpx.Response(
        503,
        headers={"x-ms-request-id": ACTIVITY, "x-ms-error-code": "ServiceUnavailable"},
        text=SECRET,
        request=httpx.Request(
            "POST",
            "https://api.example.org/v1/pair",
            headers={"Authorization": "Bearer " + SECRET},
            json={"code": SECRET},
        ),
    )
    configure_cli(
        monkeypatch, httpx.HTTPStatusError(SECRET, request=response.request, response=response)
    )
    assert CLI.main() == 1
    assert "status_code=503" in caplog.text and ACTIVITY in caplog.text
    assert SECRET not in caplog.text


def test_configuration_error_is_also_redacted(monkeypatch, caplog):
    configure_cli(monkeypatch, ValueError(SECRET))
    assert CLI.main() == 2
    assert "ValueError" in caplog.text and SECRET not in caplog.text


def test_expected_domain_error_is_safe_and_unsuccessful(monkeypatch, caplog):
    configure_cli(monkeypatch, OperatorFailure(SECRET, status_code=409, error_code="Conflict"))
    assert CLI.main() == 1
    assert "status_code=409" in caplog.text and SECRET not in caplog.text


def test_unexpected_owner_programming_error_surfaces(monkeypatch):
    configure_cli(monkeypatch, TypeError("unexpected operator bug"))
    with pytest.raises(TypeError, match="unexpected operator bug"):
        CLI.main()


def test_private_bootstrap_logs_safe_service_metadata_and_propagates_bugs(monkeypatch, caplog):
    monkeypatch.setenv("BOOTSTRAP_OPERATION", "prepare")
    monkeypatch.setattr(bootstrap, "run_bootstrap", Mock(side_effect=cosmos_failure()))
    assert bootstrap.main() == 1
    assert "status_code=403" in caplog.text and ACTIVITY in caplog.text
    assert SECRET not in caplog.text
    monkeypatch.setattr(bootstrap, "run_bootstrap", Mock(side_effect=TypeError("bootstrap bug")))
    with pytest.raises(TypeError, match="bootstrap bug"):
        bootstrap.main()


def test_malformed_diagnostic_fields_cannot_inject_log_payload(caplog):
    error = OperatorFailure(
        SECRET, status_code=403, error_code="Forbidden\n" + SECRET, activity_id=SECRET
    )
    log_operator_failure(CLI.LOGGER, "owner_cli", error)
    assert "status_code=403" in caplog.text and SECRET not in caplog.text
