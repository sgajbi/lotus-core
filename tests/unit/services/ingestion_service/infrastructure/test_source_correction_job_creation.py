"""Existing job UOW creation hook; explicit session/response substitutes, not PG."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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
