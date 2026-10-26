"""Safe operator diagnostics: metadata only, never exception messages or HTTP payloads."""

import logging
import re
from collections.abc import Mapping
from uuid import UUID

from azure.core.exceptions import AzureError
from fastapi import HTTPException
from httpx import HTTPError

from guide_api.cloud import Conflict, NotFound


class OperatorFailure(RuntimeError):
    """Expected unsuccessful operator operation, with optional upstream metadata."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        activity_id: str | None = None,
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.activity_id = activity_id
        self.request_id = request_id

    @classmethod
    def from_response(cls, response):
        return cls(
            "Operator HTTP operation failed.",
            status_code=response.status_code,
            error_code=response.headers.get("x-ms-error-code"),
            activity_id=response.headers.get("x-ms-activity-id"),
            request_id=response.headers.get("x-ms-request-id"),
        )


SERVICE_FAILURES = (AzureError, HTTPError, HTTPException, OperatorFailure, Conflict, NotFound)


def _safe_code(value) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", value):
        return value
    return None


def _safe_id(value) -> str | None:
    if not isinstance(value, str) or len(value) > 80:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        if re.fullmatch(r"req_[a-fA-F0-9]{1,64}", value):
            return value
    return None


def log_operator_failure(logger: logging.Logger, operation: str, error: Exception) -> None:
    """Follow explicit causes so a mapped HTTP 503 still exposes upstream Cosmos 403."""
    status_code = error_code = activity_id = request_id = sub_status = None
    current = error
    seen = set()
    for _ in range(6):
        if id(current) in seen:
            break
        seen.add(id(current))
        response = getattr(current, "response", None)
        status = getattr(current, "status_code", None)
        if status is None and response is not None:
            status = getattr(response, "status_code", None)
        if type(status) is int and 100 <= status <= 599:
            status_code = status
        headers = getattr(current, "headers", None)
        if not isinstance(headers, Mapping) and response is not None:
            headers = getattr(response, "headers", None)
        headers = headers if isinstance(headers, Mapping) else {}
        parsed_error = getattr(current, "error", None)
        parsed_code = (
            parsed_error.get("code")
            if isinstance(parsed_error, Mapping)
            else getattr(parsed_error, "code", None)
        )
        for value in (
            getattr(current, "error_code", None),
            parsed_code,
            headers.get("x-ms-error-code"),
        ):
            safe = _safe_code(value)
            if safe is not None:
                error_code = safe
                break
        activity_id = (
            _safe_id(getattr(current, "activity_id", None))
            or _safe_id(headers.get("x-ms-activity-id"))
            or activity_id
        )
        request_id = (
            _safe_id(getattr(current, "request_id", None))
            or _safe_id(headers.get("x-ms-request-id"))
            or _safe_id(headers.get("apim-request-id"))
            or _safe_id(headers.get("x-request-id"))
            or request_id
        )
        substatus = headers.get("x-ms-substatus")
        if isinstance(substatus, str) and re.fullmatch(r"[0-9]{1,7}", substatus):
            sub_status = substatus
        if current.__cause__ is None:
            break
        current = current.__cause__
    logger.error(
        "operation=%s status=failed error_type=%s status_code=%s error_code=%s "
        "activity_id=%s request_id=%s sub_status=%s",
        operation,
        type(error).__name__,
        status_code or "-",
        error_code or "-",
        activity_id or "-",
        request_id or "-",
        sub_status or "-",
    )
