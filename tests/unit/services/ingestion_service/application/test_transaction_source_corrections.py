"""Real submit orchestration with explicit operation-owner substitutes, not PostgreSQL."""

from unittest.mock import AsyncMock

import pytest
from portfolio_common.api_contract.async_commands import SourceEvidenceConfirmationInput
from portfolio_common.command_authorization import SOURCE_CORRECTION_CAPABILITY
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal

from src.services.ingestion_service.app.application import transaction_source_corrections as app
from src.services.ingestion_service.app.ports.transaction_source_operations import (
    SourceOperationCreation,
    SourceOperationJob,
)


def submission():
    return app.SourceCorrectionSubmission(
        target_transaction_id="target-transaction",
        body=SourceEvidenceConfirmationInput(
            expected_head_id="prior-head",
            expected_head_sha256="1" * 64,
            reason="Confirm original zero source",
            realized_pnl_local="0",
        ),
        tenant_context=TenantContext(
            TenantId("tenant-test"),
            actor_id="actor-test",
            service_identity="producer-test",
            identity_verified=True,
        ),
        principal=VerifiedServicePrincipal("producer-test", {SOURCE_CORRECTION_CAPABILITY}),
        idempotency_key="qualified-key",
        correlation_id="correlation-test",
        request_id="request-test",
        trace_id="trace-test",
    )


class OperationOwner:
    def __init__(self, status, reference):
        self.order = []
        self.result = SourceOperationCreation(
            SourceOperationJob("original-operation", status, reference), False
        )
        self.assert_ingestion_writable = AsyncMock(side_effect=self.admit)
        self.create_or_get_job = AsyncMock(side_effect=self.create)

    async def admit(self):
        self.order.append("admitted")

    async def create(self, **kwargs):
        assert self.order == ["admitted"]
        self.order.append("created-or-replayed")
        return self.result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,reference,refusal",
    [
        ("accepted", "opaque-ref", None),
        ("queued", "opaque-ref", None),
        ("failed", "opaque-ref", "SOURCE_COMMAND_PREVIOUSLY_FAILED"),
        ("completed", "opaque-ref", "SOURCE_COMMAND_PREVIOUSLY_FAILED"),
        ("accepted", None, "SOURCE_COMMAND_OPERATION_UNAVAILABLE"),
        ("queued", "", "SOURCE_COMMAND_OPERATION_UNAVAILABLE"),
    ],
)
async def test_real_submit_uses_admitted_owner_and_exact_job_result(
    monkeypatch, status, reference, refusal
):
    request = submission()
    owner = OperationOwner(status, reference)
    selected = []

    def factory(actual):
        assert actual is request
        selected.append(actual)
        return owner

    monkeypatch.setattr(app, "create_ingestion_job_id", lambda: "new-candidate-operation")
    submitter = app.SubmitTransactionSourceCorrection(factory)
    if refusal:
        with pytest.raises(app.SourceCorrectionSubmissionRejected, match=f"^{refusal}$"):
            await submitter.submit(request)
    else:
        result = await submitter.submit(request)
        assert result.operation_id == "original-operation"
        assert result.correlation_id == request.correlation_id
        assert result.status_url == "/ingestion/jobs/original-operation/source-correction"
        assert result.idempotency.key == reference
        assert result.idempotency.scope == "tenant-and-resource:transaction-source-evidence"
    assert selected == [request]
    assert owner.order == ["admitted", "created-or-replayed"]
    owner.assert_ingestion_writable.assert_awaited_once_with()
    owner.create_or_get_job.assert_awaited_once_with(
        job_id="new-candidate-operation",
        endpoint=app.SOURCE_CORRECTION_ENDPOINT,
        entity_type=app.SOURCE_CORRECTION_ENTITY,
        accepted_count=1,
        idempotency_key=request.idempotency_key,
        correlation_id=request.correlation_id,
        request_id=request.request_id,
        trace_id=request.trace_id,
        tenant_context=request.tenant_context,
        request_payload={
            "canonical_request_sha256": request.body.canonical_request_sha256(
                target_transaction_id=request.target_transaction_id
            )
        },
    )


@pytest.mark.asyncio
async def test_real_submit_write_refusal_never_creates_an_operation():
    owner = OperationOwner("accepted", "opaque-ref")
    owner.assert_ingestion_writable.side_effect = app.SourceCorrectionSubmissionRejected(
        "WRITE_REFUSED"
    )
    with pytest.raises(app.SourceCorrectionSubmissionRejected, match="^WRITE_REFUSED$"):
        await app.SubmitTransactionSourceCorrection(lambda request: owner).submit(submission())
    owner.create_or_get_job.assert_not_awaited()
