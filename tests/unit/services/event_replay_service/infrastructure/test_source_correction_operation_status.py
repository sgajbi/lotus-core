"""Independent fact verification with explicit repository substitutes, never PG proof."""

from copy import deepcopy
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from portfolio_common.api_contract.async_commands import AsyncCommandStatus
from portfolio_common.command_authorization import CommandAuthorizationPolicy
from portfolio_common.database_models import IngestionJob, OutboxEvent
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from src.services.event_replay_service.app import dependencies as composition
from src.services.event_replay_service.app.infrastructure import (
    source_correction_operation_status as projection,
)
from src.services.event_replay_service.app.routers import source_correction_operations as transport
from tests.unit.services.persistence_service.application.test_transaction_source_correction import (
    NOW,
    case,
)


async def _committed_case(companion=Decimal("12")):
    use_case, _, command, transaction, raw_payload, policy = case(base=companion)
    revision = await use_case.execute(command)
    raw = OutboxEvent(id=7, payload=raw_payload)
    intent = OutboxEvent(payload=command.model_dump(mode="json", exclude_unset=True))
    return revision, intent, raw, transaction, policy


def _rehash(row):
    # An attacker-provided content hash is not qualification: test all links
    # independently after recomputing this layer of a synthetic mutable row.
    row.revision_sha256 = canonical_content_hash(
        {
            column.name: getattr(row, column.name)
            for column in row.__table__.columns
            if column.name != "revision_sha256"
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("companion", [Decimal("0"), Decimal("12"), Decimal("-12")])
async def test_complete_verified_fact_preserves_signed_basis_and_committed_expiry(companion):
    revision, intent, raw, transaction, policy = await _committed_case(companion)
    assert projection.verified_revision_identity(
        revision, intent, raw, transaction, policy, now=int(NOW.timestamp()) + 200
    ) == (revision.revision_id, revision.revision_sha256)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "reason",
        "source",
        "presence",
        "receipt",
        "root",
        "claims",
        "raw",
        "output",
        "retained-receipt",
        "intent",
        "retired-key",
    ],
)
async def test_recomputed_fact_hash_never_substitutes_linked_authority(fault):
    revision, intent, raw, transaction, policy = await _committed_case()
    if fault == "reason":
        revision.reason = "changed"
    elif fault == "source":
        revision.source_local = Decimal("1")
    elif fault == "presence":
        revision.original_local_present = True
    elif fault == "receipt":
        revision.qualification_receipt = dict(revision.qualification_receipt) | {
            "output_content_hash": "0" * 64
        }
    elif fault == "root":
        revision.root_raw_sha256 = "0" * 64
    elif fault == "claims":
        revision.authorization_claims = dict(revision.authorization_claims) | {
            "actor_id": "foreign"
        }
    elif fault == "raw":
        raw.payload = dict(raw.payload) | {"realized_fx_pnl_base": "999"}
    elif fault == "output":
        transaction.realized_total_pnl_base = Decimal("999")
    elif fault == "retained-receipt":
        transaction.calculation_lineage = dict(transaction.calculation_lineage) | {
            "output_content_hash": "0" * 64
        }
    elif fault == "intent":
        intent.payload = deepcopy(intent.payload) | {"portfolio_id": "foreign"}
    else:
        policy = CommandAuthorizationPolicy(())
    _rehash(revision)
    with pytest.raises(ValueError):
        projection.verified_revision_identity(
            revision, intent, raw, transaction, policy, now=int(NOW.timestamp())
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["endpoint", "count", "missing-intent", "failed-with-revision"])
async def test_projection_refuses_changed_operation_ownership_or_contradictions(fault):
    revision, intent, raw, transaction, policy = await _committed_case()
    job = IngestionJob(
        endpoint="/ingest/transactions/{transaction_id}/source-evidence",
        accepted_count=1,
        status="accepted",
    )
    if fault == "endpoint":
        job.endpoint = "/ingest/transactions"
    elif fault == "count":
        job.accepted_count = 2
    elif fault == "missing-intent":
        intent = None
    else:
        job.status = "failed"
    db = MagicMock()
    result_rows = MagicMock()
    db.execute = AsyncMock(return_value=result_rows)
    result_rows.all.return_value = [(job, revision, intent, raw, transaction, revision.tenant_id)]
    result = await projection.SqlAlchemySourceCorrectionOperationStatus(db, policy).read(
        tenant_id=revision.tenant_id,
        operation_id=revision.operation_id,
        now=int(NOW.timestamp()),
    )
    assert result.status == "UNAVAILABLE" and result.revision_id is None
    query = str(
        db.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "transactions.source_correction.commands" in query
    assert "ingestion_jobs.tenant_id" in query and "ingestion_jobs.job_id" in query


@pytest.mark.asyncio
async def test_missing_owned_operation_is_not_found_not_empty_success():
    db = MagicMock()
    result_rows = MagicMock()
    db.execute = AsyncMock(return_value=result_rows)
    result_rows.all.return_value = []
    with pytest.raises(projection.SourceCorrectionOperationNotFound):
        await projection.SqlAlchemySourceCorrectionOperationStatus(
            db, CommandAuthorizationPolicy(())
        ).read(tenant_id="tenant-test", operation_id="absent", now=int(NOW.timestamp()))


def test_status_composition_borrows_session_and_defers_policy(monkeypatch):
    def premature_policy():
        raise AssertionError("Policy loading must follow transport authorization")

    monkeypatch.setattr(projection, "load_command_authorization_policy", premature_policy)
    db = MagicMock()
    adapter = composition.get_source_correction_operation_status(db)
    assert adapter._db is db and adapter._policy is None
    assert not db.method_calls


@pytest.mark.asyncio
async def test_native_storage_error_is_safe_and_stages_no_effects():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=OperationalError("SELECT secret", {}, Exception("secret")))
    with pytest.raises(RuntimeError, match="^SOURCE_COMMAND_OPERATION_UNAVAILABLE$"):
        await projection.SqlAlchemySourceCorrectionOperationStatus(
            db, CommandAuthorizationPolicy(())
        ).read(tenant_id="tenant-test", operation_id="operation", now=int(NOW.timestamp()))
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,expected",
    [("queued", 200), ("succeeded", 200), ("missing", 404), ("unavailable", 503), ("denied", 403)],
)
async def test_injected_status_router_retains_safe_shapes_and_authority_order(
    monkeypatch, outcome, expected
):
    # Explicit principal substitute proves composition/order only, never auth crypto.
    principal = VerifiedServicePrincipal("owning-service", {transport.SOURCE_CORRECTION_CAPABILITY})
    monkeypatch.setattr(
        transport,
        "verify_service_principal",
        lambda *args: "denied" if outcome == "denied" else principal,
    )
    reader = MagicMock()
    reader.read = AsyncMock(
        return_value=AsyncCommandStatus(operation_id="operation", status="QUEUED")
    )
    if outcome == "succeeded":
        reader.read.return_value = AsyncCommandStatus(
            operation_id="operation",
            status="SUCCEEDED",
            revision_id="immutable-revision",
            revision_sha256="1" * 64,
        )
    if outcome == "missing":
        reader.read.side_effect = projection.SourceCorrectionOperationNotFound()
    elif outcome == "unavailable":
        reader.read.side_effect = RuntimeError("secret storage details")
    app = FastAPI()
    app.include_router(transport.router)
    app.dependency_overrides[composition.get_source_correction_operation_status] = lambda: reader
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/ingestion/jobs/operation/source-correction",
            headers={"x-tenant-id": "tenant-test", "x-correlation-id": "current-read-correlation"},
        )
        retry = await client.get(
            "/ingestion/jobs/operation/source-correction",
            headers={"x-tenant-id": "tenant-test", "x-correlation-id": "retry-read-correlation"},
        )
    assert response.status_code == expected and "secret" not in response.text
    assert response.json()["correlation_id"] == "current-read-correlation"
    assert retry.status_code == expected
    assert retry.json() == response.json() | {"correlation_id": "retry-read-correlation"}
    if outcome == "denied":
        reader.read.assert_not_awaited()
    else:
        assert reader.read.await_args.kwargs["tenant_id"] == "tenant-test"
        assert reader.read.await_args.kwargs["operation_id"] == "operation"
    if outcome in {"queued", "succeeded"}:
        assert response.json()["status"] == outcome.upper()
        assert response.json()["revision_id"] == (
            "immutable-revision" if outcome == "succeeded" else None
        )
        assert response.json()["revision_sha256"] == ("1" * 64 if outcome == "succeeded" else None)
        assert reader.read.return_value.correlation_id is None
    else:
        assert set(response.json()) == {"code", "message", "correlation_id", "details"}
