"""Registered HTTP security/queued contract with explicit application substitute."""

import json
from pathlib import Path
from time import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from portfolio_common.api_contract.async_commands import (
    AsyncCommandAccepted,
    AsyncCommandIdempotency,
)
from portfolio_common.command_authorization import SOURCE_CORRECTION_CAPABILITY
from portfolio_common.enterprise_readiness import (
    _enterprise_auth_context_signature,
    _normalize_headers,
)

from src.services.ingestion_service.app import main
from src.services.ingestion_service.app.application.transaction_source_corrections import (
    SOURCE_CORRECTION_ENDPOINT,
    SourceCorrectionSubmissionRejected,
)
from src.services.ingestion_service.app.dependencies import (
    get_transaction_source_correction_submitter,
)
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    IngestionIdempotencyConflictError,
)


def headers(capability=SOURCE_CORRECTION_CAPABILITY, correlation="qualified-correlation"):
    values = {
        "X-Tenant-Id": "tenant-test",
        "X-Actor-Id": "qualified-actor",
        "X-Role": "operations",
        "X-Correlation-Id": correlation,
        "X-Service-Identity": "qualified-service",
        "X-Capabilities": capability,
        "X-Enterprise-Auth-Key-Id": "qualified-key",
        "X-Enterprise-Auth-Timestamp": str(int(time())),
        "X-Idempotency-Key": "source-confirmation-unit-key",
    }
    values["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(values), "synthetic-http-proof-secret-not-production"
    )
    return values


def body():
    return {
        "expected_head_id": "7",
        "expected_head_sha256": "1" * 64,
        "reason": "Qualified missing-source confirmation",
        "realized_pnl_local": "0",
    }


@pytest.fixture
def registered_http(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "qualified-key")
    monkeypatch.setenv(
        "ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "synthetic-http-proof-secret-not-production"
    )
    producer = MagicMock()
    producer.flush.return_value = 0
    monkeypatch.setattr(main, "get_kafka_producer", lambda: producer)
    submitter = MagicMock()
    submitter.submit = AsyncMock(
        return_value=AsyncCommandAccepted(
            correlation_id="original-operation-correlation",
            operation_id="qualified-operation",
            status_url="/ingestion/jobs/qualified-operation/source-correction",
            idempotency=AsyncCommandIdempotency(
                key="opaque-purpose-reference",
                scope="tenant-and-resource:transaction-source-evidence",
            ),
        )
    )
    monkeypatch.setitem(
        main.app.dependency_overrides,
        get_transaction_source_correction_submitter,
        lambda: submitter,
    )
    with TestClient(main.app) as client:
        yield client, submitter


@pytest.mark.parametrize(
    "fault",
    ["missing", "signature", "ordinary-capability", "bearer", "foreign-tenant", "missing-actor"],
)
def test_local_auth_disabled_never_admits_unverified_or_ordinary_correction(registered_http, fault):
    client, submitter = registered_http
    values = headers(
        "ingestion.transactions.write"
        if fault == "ordinary-capability"
        else SOURCE_CORRECTION_CAPABILITY
    )
    if fault == "missing":
        values = {"X-Tenant-Id": "tenant-test"}
    elif fault == "signature":
        values["X-Enterprise-Auth-Signature"] = "0" * 64
    elif fault == "bearer":
        values["Authorization"] = "Bearer unverified-static-value"
    elif fault == "foreign-tenant":
        values["X-Tenant-Id"] = "foreign"
    elif fault == "missing-actor":
        del values["X-Actor-Id"]
    response = client.post(
        "/ingest/transactions/FX-CLOSE/source-evidence", headers=values, json=body()
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SOURCE_CORRECTION_GRANT_REQUIRED"
    assert set(response.json()) == {"code", "message", "correlation_id", "details"}
    assert response.json()["correlation_id"]
    submitter.submit.assert_not_awaited()


def test_registered_route_queued_response_and_trusted_resource_scope(registered_http):
    client, submitter = registered_http
    response = client.post(
        "/ingest/transactions/FX-CLOSE/source-evidence", headers=headers(), json=body()
    )
    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"
    assert response.json()["correlation_id"] == "qualified-correlation"
    assert submitter.submit.return_value.correlation_id == "original-operation-correlation"
    assert response.headers["location"] == response.json()["status_url"]
    assert response.headers["retry-after"] == "2"
    submission = submitter.submit.await_args.args[0]
    assert submission.target_transaction_id == "FX-CLOSE"
    assert submission.tenant_context.identity_verified is True
    assert submission.tenant_context.tenant_id_text == "tenant-test"
    assert submission.body.supplied_bases == ("local",)


@pytest.mark.parametrize(
    "extra", ["tenant_id", "portfolio_id", "actor_id", "authorizedScope", "authorization"]
)
def test_caller_scope_and_delegation_are_not_public_fields(registered_http, extra):
    client, submitter = registered_http
    response = client.post(
        "/ingest/transactions/FX-CLOSE/source-evidence",
        headers=headers(),
        json=body() | {extra: "caller-override"},
    )
    assert response.status_code == 422
    submitter.submit.assert_not_awaited()


def test_idempotency_is_mandatory_before_submission(registered_http):
    client, submitter = registered_http
    values = headers()
    del values["X-Idempotency-Key"]
    response = client.post(
        "/ingest/transactions/FX-CLOSE/source-evidence", headers=values, json=body()
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SOURCE_CORRECTION_IDEMPOTENCY_REQUIRED"
    assert response.json()["correlation_id"] == "qualified-correlation"
    submitter.submit.assert_not_awaited()


def test_literal_route_preserves_submission_and_rate_limit_endpoint_identity(registered_http):
    client, _ = registered_http
    operation = client.get("/openapi.json").json()["paths"][SOURCE_CORRECTION_ENDPOINT]
    assert "post" in operation
    assert SOURCE_CORRECTION_ENDPOINT == "/ingest/transactions/{transaction_id}/source-evidence"


def test_retry_response_uses_current_request_without_mutating_original_lineage(registered_http):
    client, submitter = registered_http
    responses = [
        client.post(
            "/ingest/transactions/FX-CLOSE/source-evidence",
            headers=headers(correlation=correlation),
            json=body(),
        )
        for correlation in ("first-request", "retry-request")
    ]
    assert [response.status_code for response in responses] == [202, 202]
    assert [response.json()["correlation_id"] for response in responses] == [
        "first-request",
        "retry-request",
    ]
    assert responses[0].json() | {"correlation_id": "retry-request"} == responses[1].json()
    assert submitter.submit.return_value.correlation_id == "original-operation-correlation"


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (
            IngestionIdempotencyConflictError(
                endpoint=SOURCE_CORRECTION_ENDPOINT, idempotency_key="secret-key"
            ),
            409,
            "SOURCE_COMMAND_IDEMPOTENCY_CONFLICT",
        ),
        (
            SourceCorrectionSubmissionRejected("SOURCE_COMMAND_RAW_UNAVAILABLE"),
            404,
            "SOURCE_COMMAND_RAW_UNAVAILABLE",
        ),
        (
            SourceCorrectionSubmissionRejected("secret unexpected reason"),
            409,
            "SOURCE_COMMAND_OPERATION_UNAVAILABLE",
        ),
        (RuntimeError("secret storage details"), 503, "SOURCE_COMMAND_OPERATION_UNAVAILABLE"),
    ],
)
def test_problem_contract_retains_status_and_safe_idempotency_metadata(
    registered_http, failure, status, code
):
    client, submitter = registered_http
    submitter.submit.side_effect = failure
    response = client.post(
        "/ingest/transactions/FX-CLOSE/source-evidence", headers=headers(), json=body()
    )
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["correlation_id"] == "qualified-correlation"
    fields = {"code", "message", "correlation_id", "details"}
    if code == "SOURCE_COMMAND_IDEMPOTENCY_CONFLICT":
        fields.add("idempotency_key")
        assert response.json()["idempotency_key"] == "source-confirmation-unit-key"
    else:
        assert "source-confirmation-unit-key" not in response.text
    assert set(response.json()) == fields
    assert "secret" not in response.text
    assert response.json()["details"] == (
        {
            "idempotency_scope": "tenant-and-resource:transaction-source-evidence",
            "conflict_reason": "payload_fingerprint_mismatch",
        }
        if status == 409 and code == "SOURCE_COMMAND_IDEMPOTENCY_CONFLICT"
        else {}
    )


@pytest.mark.parametrize(
    "example_id",
    [
        "source-confirmation-missing-idempotency",
        "source-confirmation-queued",
        "source-confirmation-idempotency-conflict",
    ],
)
def test_source_confirmation_examples_match_actual_registered_wire(registered_http, example_id):
    client, submitter = registered_http
    values = headers()
    if example_id == "source-confirmation-missing-idempotency":
        del values["X-Idempotency-Key"]
    elif example_id == "source-confirmation-idempotency-conflict":
        submitter.submit.side_effect = IngestionIdempotencyConflictError(
            endpoint="secret tenant-scoped endpoint", idempotency_key="secret store key"
        )
    response = client.post(
        "/ingest/transactions/FX-CLOSE/source-evidence", headers=values, json=body()
    )
    catalog = json.loads(Path("docs/standards/verified-api-examples.v1.json").read_text())
    example = next(item for item in catalog["examples"] if item["id"] == example_id)
    assert response.status_code == example["response"]["status"]
    assert response.json() == example["response"]["body"]
    assert "secret" not in response.text
