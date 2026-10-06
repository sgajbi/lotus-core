"""Async outcome compatibility, not independent completion flags."""

import pytest
from portfolio_common.api_contract.async_commands import AsyncCommandStatus
from pydantic import ValidationError


@pytest.mark.parametrize("status", ["QUEUED", "SUCCEEDED", "FAILED", "UNAVAILABLE"])
@pytest.mark.parametrize("identity", ["none", "id", "hash", "both"])
@pytest.mark.parametrize("reason", [None, "SOURCE_AUTHORITY_UNAVAILABLE"])
def test_complete_status_matrix(status, identity, reason):
    payload = {"operation_id": "qualified-operation", "status": status, "reason_code": reason}
    if identity in {"id", "both"}:
        payload["revision_id"] = "qualified-revision"
    if identity in {"hash", "both"}:
        payload["revision_sha256"] = "1" * 64
    valid = (
        status == "SUCCEEDED"
        and identity == "both"
        and reason is None
        or status == "QUEUED"
        and identity == "none"
        and reason is None
        or status in {"FAILED", "UNAVAILABLE"}
        and identity == "none"
        and reason is not None
    )
    if valid:
        assert AsyncCommandStatus.model_validate(payload).model_dump() == {
            "correlation_id": None,
            "operation_id": "qualified-operation",
            "status": status,
            "revision_id": payload.get("revision_id"),
            "revision_sha256": payload.get("revision_sha256"),
            "reason_code": reason,
        }
    else:
        with pytest.raises(ValidationError):
            AsyncCommandStatus.model_validate(payload)
