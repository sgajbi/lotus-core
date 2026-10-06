"""Existing job UOW creation hook; explicit session/response substitutes, not PG."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.api_contract.async_commands import SourceEvidenceConfirmationInput
from portfolio_common.command_authorization import (
    SOURCE_CORRECTION_CAPABILITY,
    CommandAuthorizationPolicy,
    CommandAuthorizationRejected,
    CommandProducerEnrollment,
    verify_command_authorization,
)
from portfolio_common.config import KAFKA_TRANSACTIONS_SOURCE_CORRECTION_COMMANDS_TOPIC
from portfolio_common.database_models import IngestionJob
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal
from portfolio_common.event_contracts import TransactionSourceCorrectionRequestedEvent
from portfolio_common.ingestion_lineage import ingestion_job_id_var
from sqlalchemy.dialects import postgresql

from src.services.ingestion_service.app.infrastructure import (
    transaction_source_correction_commands as commands,
)
from src.services.ingestion_service.app.services import ingestion_job_lifecycle as lifecycle


@pytest.mark.asyncio
@pytest.mark.parametrize("created", [False, True])
async def test_native_operation_owner_projects_only_job_authority_and_preserves_replay(created):
    native = MagicMock()
    native.assert_ingestion_writable = AsyncMock()
    native.create_or_get_job = AsyncMock(
        return_value=SimpleNamespace(
            job=SimpleNamespace(
                job_id="operation", status="queued", idempotency_key_reference="key-ref"
            ),
            created=created,
        )
    )
    owner = commands.NativeSourceCorrectionOperationOwner(native)
    await owner.assert_ingestion_writable()
    args = dict(
        job_id="operation",
        endpoint="/ingest/transactions/{transaction_id}/source-evidence",
        entity_type="transaction_source_correction",
        accepted_count=1,
        idempotency_key="qualified-key",
        correlation_id="correlation",
        request_id="request",
        trace_id="trace",
        tenant_context=SimpleNamespace(tenant_id="tenant"),
        request_payload={"canonical_request_sha256": "1" * 64},
    )
    projected = await owner.create_or_get_job(**args)
    native.assert_ingestion_writable.assert_awaited_once()
    native.create_or_get_job.assert_awaited_once_with(**args)
    assert projected.created is created
    assert projected.job.job_id == "operation" and projected.job.status == "queued"
    assert projected.job.idempotency_key_reference == "key-ref"
    native.commit.assert_not_called()
    native.rollback.assert_not_called()
    native.close.assert_not_called()


def context(monkeypatch):
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    begin = MagicMock()
    begin.__aenter__ = AsyncMock()
    begin.__aexit__ = AsyncMock(return_value=False)
    db.begin.return_value = begin

    async def factory():
        yield db

    # Server defaults / DTO mapping are outside this mocked-session assertion.
    monkeypatch.setattr(
        lifecycle, "to_job_response", lambda row, **kwargs: SimpleNamespace(job_id=row.job_id)
    )
    return db, begin, factory


def arguments(factory):
    return dict(
        job_id="qualified-operation",
        tenant_id="tenant-test",
        endpoint="/ingest/transactions/{transaction_id}/source-evidence",
        entity_type="transaction_source_correction",
        accepted_count=1,
        idempotency_key="qualified-idempotency",
        correlation_id="qualified-correlation",
        request_id="qualified-request",
        trace_id="qualified-trace",
        request_payload={"canonical_request_sha256": "1" * 64},
        fingerprint_key_id="qualified-evidence-key",
        fingerprint_hmac_secret="synthetic-evidence-secret-not-purpose-signing",
        fingerprint_previous_keys={},
        session_factory=factory,
    )


@pytest.mark.asyncio
async def test_creation_effect_after_flush_inside_begin_and_exact_replay_never_repeats(monkeypatch):
    db, begin, factory = context(monkeypatch)
    seen = []

    async def effect(session, job):
        assert session is db and db.flush.await_count == 1
        assert begin.__aexit__.await_count == 0
        seen.append(job)

    result = await lifecycle.create_or_get_job_result(**arguments(factory), on_created=effect)
    assert result.created is True and len(seen) == 1
    row = seen[0]
    assert row.request_payload is None and row.request_payload_classification == "restricted"
    assert row.request_payload_representation == "fingerprint_only"
    assert row.request_payload_replay_eligible is False
    db.scalar.return_value = row
    replay = await lifecycle.create_or_get_job_result(**arguments(factory), on_created=effect)
    assert replay.created is False and replay.job.job_id == result.job.job_id
    assert len(seen) == 1 and db.flush.await_count == 1


@pytest.mark.asyncio
async def test_changed_target_body_digest_cannot_replay_the_existing_job(monkeypatch):
    db, _, factory = context(monkeypatch)
    await lifecycle.create_or_get_job_result(**arguments(factory))
    db.scalar.return_value = db.add.call_args.args[0]
    changed = arguments(factory) | {"request_payload": {"canonical_request_sha256": "2" * 64}}
    effect = AsyncMock()
    with pytest.raises(lifecycle.IngestionIdempotencyConflictError):
        await lifecycle.create_or_get_job_result(**changed, on_created=effect)
    effect.assert_not_awaited()


@pytest.mark.asyncio
async def test_effect_failure_reaches_owning_transaction_exit_as_exception(monkeypatch):
    db, begin, factory = context(monkeypatch)
    effect = AsyncMock(side_effect=RuntimeError("synthetic-outbox-refusal"))
    with pytest.raises(RuntimeError, match="synthetic-outbox-refusal"):
        await lifecycle.create_or_get_job_result(**arguments(factory), on_created=effect)
    assert begin.__aexit__.await_args.args[0] is RuntimeError
    assert db.flush.await_count == 1
    # Mocked context exit is NOT a claim that PostgreSQL rolled anything back.


def staging_authority(actor="qualified-actor"):
    request = commands.SourceCorrectionSubmission(
        target_transaction_id="qualified-transaction",
        body=SourceEvidenceConfirmationInput(
            expected_head_id="qualified-head",
            expected_head_sha256="1" * 64,
            reason="Confirm original source zero",
            realized_pnl_local="0",
        ),
        tenant_context=TenantContext(
            TenantId("tenant-test"),
            actor_id=actor,
            service_identity="qualified-producer",
            identity_verified=True,
        ),
        principal=VerifiedServicePrincipal("qualified-producer", {SOURCE_CORRECTION_CAPABILITY}),
        idempotency_key="qualified-key",
        correlation_id="qualified-correlation",
        request_id="qualified-request",
        trace_id="qualified-trace",
    )
    signer = CommandProducerEnrollment(
        "qualified-issuer",
        "qualified-signing-key",
        "qualified-producer",
        secret="synthetic-test-signing-material-not-production",
        signing_enabled=True,
    )
    return request, CommandAuthorizationPolicy((signer,), max_ttl_seconds=120)


def assert_session_ownership(db):
    for name in ("begin", "commit", "rollback", "close", "flush", "add"):
        getattr(db, name).assert_not_called()


def sql_text(statement):
    return " ".join(
        str(
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        ).split()
    )


def staging_session(monkeypatch, *, transaction=True, portfolio="portfolio-test", roots=None):
    db = MagicMock()
    db.in_transaction.return_value = transaction
    raw = {
        "portfolio_id": "portfolio-test",
        "transaction_id": "qualified-transaction",
        "realized_pnl_local": "0",
    }
    rows = [SimpleNamespace(id=71, payload=raw)] if roots is None else roots

    async def scalar(statement):
        sql = sql_text(statement)
        assert "JOIN portfolios ON portfolios.portfolio_id = transactions.portfolio_id" in sql
        assert "transactions.transaction_id = 'qualified-transaction'" in sql
        assert "portfolios.tenant_id = 'tenant-test'" in sql
        return portfolio

    async def execute(statement):
        sql = sql_text(statement)
        assert "outbox_events.aggregate_type = 'RawTransaction'" in sql
        assert "outbox_events.aggregate_id = 'portfolio-test'" in sql
        assert "outbox_events.event_type = 'RawTransactionPersisted'" in sql
        assert (
            "CAST((outbox_events.payload ->> 'portfolio_id') AS VARCHAR) = 'portfolio-test'" in sql
        )
        assert (
            "CAST((outbox_events.payload ->> 'transaction_id') AS VARCHAR) "
            "= 'qualified-transaction'" in sql
        )
        assert sql.endswith("LIMIT 2")
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    db.scalar = AsyncMock(side_effect=scalar)
    db.execute = AsyncMock(side_effect=execute)
    outbox = MagicMock()
    outbox.create_outbox_event = AsyncMock()
    constructor = MagicMock(return_value=outbox)
    monkeypatch.setattr(commands, "OutboxRepository", constructor)
    return db, outbox, constructor, raw


@pytest.mark.parametrize(
    "fault",
    [
        "unverified",
        "foreign-identity",
        "capability",
        "missing-signer",
        "disabled-signer",
        "foreign-signer",
        "wrong-signer-capability",
        "duplicate-signers",
    ],
)
def test_actual_stager_denies_invalid_authority_before_any_session_or_outbox(monkeypatch, fault):
    request, policy = staging_authority()
    signer = policy.enrollments[0]
    if fault == "unverified":
        request = replace(
            request, tenant_context=replace(request.tenant_context, identity_verified=False)
        )
    elif fault == "foreign-identity":
        request = replace(
            request, tenant_context=replace(request.tenant_context, service_identity="foreign")
        )
    elif fault == "capability":
        request = replace(request, principal=VerifiedServicePrincipal("qualified-producer", set()))
    elif fault == "missing-signer":
        policy = replace(policy, enrollments=())
    elif fault == "duplicate-signers":
        policy = replace(policy, enrollments=(signer, replace(signer, key_id="another-key")))
    else:
        changes = {
            "disabled-signer": {"signing_enabled": False},
            "foreign-signer": {"principal": "foreign"},
            "wrong-signer-capability": {"capability": "ordinary.write"},
        }[fault]
        policy = replace(policy, enrollments=(replace(signer, **changes),))
    db, outbox, constructor, _ = staging_session(monkeypatch)
    with pytest.raises(CommandAuthorizationRejected, match="^COMMAND_CORRECTION_GRANT_REQUIRED$"):
        commands.SqlAlchemySourceCorrectionCommandStager(request, policy)
    constructor.assert_not_called()
    outbox.create_outbox_event.assert_not_awaited()
    db.scalar.assert_not_awaited()
    db.execute.assert_not_awaited()
    assert_session_ownership(db)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault,code",
    [
        ("no-uow", "SOURCE_COMMAND_UOW_REQUIRED"),
        ("foreign-job", "SOURCE_COMMAND_OWNER_MISMATCH"),
        ("no-target", "SOURCE_COMMAND_TARGET_UNAVAILABLE"),
        ("no-roots", "SOURCE_COMMAND_RAW_UNAVAILABLE"),
        ("many-roots", "SOURCE_COMMAND_RAW_UNAVAILABLE"),
        ("nonmapping", "SOURCE_COMMAND_RAW_UNAVAILABLE"),
        ("noncanonical", "SOURCE_COMMAND_RAW_UNAVAILABLE"),
    ],
)
async def test_actual_stager_refuses_unowned_or_unusable_source_without_outbox(
    monkeypatch, fault, code
):
    request, policy = staging_authority()
    roots = {
        "no-roots": [],
        "many-roots": [SimpleNamespace(id=1), SimpleNamespace(id=2)],
        "nonmapping": [SimpleNamespace(id=1, payload=[])],
        "noncanonical": [SimpleNamespace(id=1, payload={"unsupported": object()})],
    }.get(fault)
    db, outbox, constructor, _ = staging_session(
        monkeypatch,
        transaction=fault != "no-uow",
        portfolio=None if fault == "no-target" else "portfolio-test",
        roots=roots,
    )
    job = IngestionJob(
        job_id="operation-test", tenant_id="foreign" if fault == "foreign-job" else "tenant-test"
    )
    with pytest.raises(commands.SourceCorrectionSubmissionRejected, match=f"^{code}$"):
        await commands.SqlAlchemySourceCorrectionCommandStager(request, policy).stage(db, job)
    assert db.scalar.await_count == (0 if fault in {"no-uow", "foreign-job"} else 1)
    assert db.execute.await_count == (0 if fault in {"no-uow", "foreign-job", "no-target"} else 1)
    constructor.assert_not_called()
    outbox.create_outbox_event.assert_not_awaited()
    assert_session_ownership(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["qualified-actor", None])
async def test_actual_stager_signs_exact_claims_and_awaits_outbox_in_original_uow(
    monkeypatch, actor
):
    request, policy = staging_authority(actor)
    db, outbox, constructor, raw = staging_session(monkeypatch)
    now = 1700000000
    prior_scope = ingestion_job_id_var.get()

    async def publish(**kwargs):
        assert ingestion_job_id_var.get() == "operation-test"
        assert_session_ownership(db)
        event = TransactionSourceCorrectionRequestedEvent.model_validate(kwargs["payload"])
        expected_hash = request.body.canonical_request_sha256(
            target_transaction_id=request.target_transaction_id
        )
        verified = verify_command_authorization(
            event.authorization, expected_request_sha256=expected_hash, policy=policy, now=now
        )
        assert verified.durable_replay is False
        assert verified.claims.model_dump() == {
            "contract_version": "lotus.command-authorization.v1",
            "purpose": "lotus-core.transaction-source-evidence-confirmation",
            "audience": "lotus-core.persistence-service",
            "capability": SOURCE_CORRECTION_CAPABILITY,
            "issuer": "qualified-issuer",
            "key_id": "qualified-signing-key",
            "principal": "qualified-producer",
            "actor_id": actor or "qualified-producer",
            "tenant_id": "tenant-test",
            "command_id": "operation-test",
            "operation_id": "operation-test",
            "target_transaction_id": "qualified-transaction",
            "root_raw_id": "71",
            "root_raw_sha256": canonical_content_hash(raw),
            "expected_head_id": "qualified-head",
            "expected_head_sha256": "1" * 64,
            "canonical_request_sha256": expected_hash,
            "issued_at": now,
            "expires_at": now + 120,
            "nonce": "operation-test",
            "correlation_id": "qualified-correlation",
            "trace_id": "qualified-trace",
        }
        assert event.body == request.body
        assert (event.event_type, event.schema_version, event.source_system) == (
            "TransactionSourceCorrectionRequested",
            "1.0.0",
            "ingestion_service",
        )
        assert (
            event.tenant_id,
            event.portfolio_id,
            event.trace_id,
            event.correlation_id,
            event.idempotency_key,
        ) == (
            "tenant-test",
            "portfolio-test",
            "qualified-trace",
            "qualified-correlation",
            "operation-test",
        )
        assert kwargs == {
            "aggregate_type": "TransactionSourceCorrectionCommand",
            "aggregate_id": "operation-test",
            "partition_key": "qualified-transaction",
            "event_type": "TransactionSourceCorrectionRequested",
            "topic": KAFKA_TRANSACTIONS_SOURCE_CORRECTION_COMMANDS_TOPIC,
            "correlation_id": "qualified-correlation",
            "payload": event.model_dump(mode="json", exclude_unset=True),
        }

    outbox.create_outbox_event.side_effect = publish
    stager = commands.SqlAlchemySourceCorrectionCommandStager(
        request, policy, clock=lambda: datetime.fromtimestamp(now, UTC)
    )
    await stager.stage(db, IngestionJob(job_id="operation-test", tenant_id="tenant-test"))
    constructor.assert_called_once_with(db)
    outbox.create_outbox_event.assert_awaited_once()
    db.scalar.assert_awaited_once()
    db.execute.assert_awaited_once()
    assert ingestion_job_id_var.get() == prior_scope
    assert_session_ownership(db)
