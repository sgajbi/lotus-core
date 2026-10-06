"""Actual crypto/receipt/domain/CAS application proof with explicit repository substitute."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.api_contract.async_commands import SourceEvidenceConfirmationInput
from portfolio_common.command_authorization import (
    SOURCE_CORRECTION_CAPABILITY,
    CommandAuthorizationClaims,
    CommandAuthorizationPolicy,
    CommandAuthorizationRejected,
    CommandProducerEnrollment,
    authenticate_command_authorization,
    sign_command_authorization,
)
from portfolio_common.database_models import OutboxEvent, Transaction, TransactionSourceRevision
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.domain.transaction.payload_identity import transaction_payload_fingerprint
from portfolio_common.enterprise_readiness import VerifiedServicePrincipal
from portfolio_common.event_contracts import TransactionSourceCorrectionRequestedEvent
from portfolio_common.event_mapping import transaction_event_v1_payload
from portfolio_common.events import TransactionEvent

from src.services.persistence_service.app.application import (
    transaction_source_correction as application,
)
from src.services.persistence_service.app.repositories import (
    transaction_source_revision_repository as storage,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    build_fx_processed_transaction,
)
from tests.test_support.fx_source_evidence import TENANT, fx_source_fixture

NOW = datetime(2026, 10, 5, tzinfo=UTC)


def case(local=None, base=Decimal("12"), *, changes=None, source_capital=Decimal("0")):
    _, processed, _ = fx_source_fixture(local, base)
    source = replace(
        processed,
        realized_fx_pnl_local=local,
        realized_fx_pnl_base=base,
        realized_capital_pnl_local=source_capital,
        realized_capital_pnl_base=source_capital,
        realized_total_pnl_local=None,
        realized_total_pnl_base=None,
        calculation_lineage=None,
    )
    raw = transaction_event_v1_payload(
        TransactionEvent.model_validate(
            {
                name: value
                for name, value in asdict(source).items()
                if name in TransactionEvent.model_fields
            }
        )
    )
    output = build_fx_processed_transaction(source)
    ledger = Transaction(
        **{
            name: value
            for name, value in asdict(output).items()
            if name in Transaction.__table__.columns and name != "calculation_lineage"
        }
    )
    ledger.calculation_lineage = output.calculation_lineage.lineage_payload()
    ledger.payload_fingerprint = transaction_payload_fingerprint(raw)
    raw_hash = canonical_content_hash(raw)
    body = SourceEvidenceConfirmationInput.model_validate(
        {
            "expected_head_id": "7",
            "expected_head_sha256": raw_hash,
            "reason": "Verified missing FX source confirmation",
            "realized_pnl_local": "0",
        }
        | (changes or {})
    )
    claims = CommandAuthorizationClaims(
        issuer="qualified-test-issuer",
        key_id="qualified-test-key",
        principal="qualified-test-service",
        actor_id="qualified-test-actor",
        tenant_id=TENANT.value,
        command_id="qualified-command",
        operation_id="qualified-operation",
        target_transaction_id=ledger.transaction_id,
        root_raw_id="7",
        root_raw_sha256=raw_hash,
        expected_head_id="7",
        expected_head_sha256=raw_hash,
        canonical_request_sha256=body.canonical_request_sha256(
            target_transaction_id=ledger.transaction_id
        ),
        issued_at=int(NOW.timestamp()),
        expires_at=int(NOW.timestamp()) + 100,
        nonce="qualified-nonce",
        correlation_id="qualified-correlation",
        trace_id="qualified-trace",
    )
    policy = CommandAuthorizationPolicy(
        (
            CommandProducerEnrollment(
                claims.issuer,
                claims.key_id,
                claims.principal,
                secret="synthetic-qualified-test-key-not-production-enrollment",
                signing_enabled=True,
            ),
        )
    )
    principal = VerifiedServicePrincipal(claims.principal, {SOURCE_CORRECTION_CAPABILITY})
    context = TenantContext(
        TENANT, actor_id=claims.actor_id, service_identity=claims.principal, identity_verified=True
    )
    token = sign_command_authorization(
        claims, principal=principal, tenant_context=context, policy=policy, now=int(NOW.timestamp())
    )
    command = TransactionSourceCorrectionRequestedEvent(
        event_type="TransactionSourceCorrectionRequested",
        schema_version="1.0.0",
        source_system="ingestion_service",
        trace_id=claims.trace_id,
        idempotency_key=claims.command_id,
        authorization=token,
        body=body,
        portfolio_id=ledger.portfolio_id,
        tenant_id=TENANT.value,
        correlation_id=claims.correlation_id,
    )
    repo = MagicMock()
    repo.committed_command = AsyncMock(return_value=None)
    repo.lock_admitted_operation = AsyncMock(
        return_value=storage.SourceOperationIntent(
            command.model_dump(mode="json", exclude_unset=True)
        )
    )
    repo.lock_retained_source = AsyncMock(
        side_effect=lambda **kwargs: storage.retained_source_facts(
            ledger, OutboxEvent(id=7, payload=raw), None
        )
    )
    repo.normalize_command = storage.TransactionSourceRevisionRepository.normalize_command
    repo.decode_admitted_intent = storage.TransactionSourceRevisionRepository.decode_admitted_intent
    repo.validate_retained_input = (
        storage.TransactionSourceRevisionRepository.validate_retained_input
    )
    repo.read_committed_source = AsyncMock()
    repo.stage_revision_and_notification = AsyncMock()
    use_case = application.TransactionSourceCorrectionApplication(
        repo, policy=policy, clock=lambda: NOW
    )
    return use_case, repo, command, ledger, raw, policy


@pytest.mark.asyncio
@pytest.mark.parametrize("companion", [Decimal("0"), Decimal("12"), Decimal("-12")])
async def test_missing_zero_confirmation_preserves_every_original_field_and_receipt(companion):
    use_case, repo, command, ledger, raw, _ = case(base=companion)
    original = {
        column.name: deepcopy(getattr(ledger, column.name)) for column in ledger.__table__.columns
    }
    original_raw = deepcopy(raw)
    revision = await use_case.execute(command)
    assert revision.source_local == 0 and revision.source_base == companion
    assert revision.original_local_present is False and revision.original_base_present is True
    assert revision.qualification_receipt["algorithm_id"] == "fx-source-evidence-confirmation"
    assert revision.qualification_receipt != ledger.calculation_lineage
    assert {
        column.name: getattr(ledger, column.name) for column in ledger.__table__.columns
    } == original
    assert raw == original_raw
    repo.stage_revision_and_notification.assert_awaited_once_with(revision)
    assert repo.committed_command.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_basis", ["local", "base"])
@pytest.mark.parametrize("companion", [Decimal("0"), Decimal("12"), Decimal("-12")])
async def test_signed_zero_writer_hash_survives_unsigned_reload_and_real_retry(
    missing_basis, companion
):
    changes = (
        {"realized_pnl_local": "-0"}
        if missing_basis == "local"
        else {"realized_pnl_local": str(companion), "realized_pnl_base": "-0"}
    )
    use_case, repo, command, ledger, raw, _ = case(
        local=None if missing_basis == "local" else companion,
        base=companion if missing_basis == "local" else None,
        changes=changes,
    )
    immutable_raw = deepcopy(raw)
    immutable_output = {
        column.name: deepcopy(getattr(ledger, column.name)) for column in ledger.__table__.columns
    }
    fact = await use_case.execute(command)
    value = getattr(fact, "source_" + missing_basis)
    assert value.is_zero() and not value.is_signed() and value.as_tuple().exponent == -10
    material = fact.material()
    assert (
        canonical_content_hash(
            {key: value for key, value in material.items() if key != "revision_sha256"}
        )
        == fact.revision_sha256
    )
    row = TransactionSourceRevision(**material)
    setattr(row, "source_" + missing_basis, value.copy_abs())
    repo.committed_command.side_effect = lambda **kwargs: storage.source_revision_fact(row)
    repo.read_committed_source.side_effect = lambda revision: storage.retained_source_facts(
        ledger, OutboxEvent(id=7, payload=raw), row
    )
    repo.stage_revision_and_notification.reset_mock()
    retried = await use_case.execute(command)
    assert retried.revision_sha256 == fact.revision_sha256
    repo.stage_revision_and_notification.assert_not_awaited()
    assert raw == immutable_raw
    assert {
        column.name: getattr(ledger, column.name) for column in ledger.__table__.columns
    } == immutable_output


@pytest.mark.asyncio
async def test_invalid_signature_refuses_before_any_repository_lookup():
    use_case, repo, command, *_ = case()
    command = command.model_copy(
        update={"authorization": command.authorization.model_copy(update={"signature": "0" * 64})}
    )
    with pytest.raises(CommandAuthorizationRejected, match="SIGNATURE_INVALID"):
        await use_case.execute(command)
    repo.committed_command.assert_not_awaited()
    repo.lock_retained_source.assert_not_awaited()
    repo.stage_revision_and_notification.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["receipt", "raw", "owner", "head", "output"])
async def test_invalid_retained_authority_or_stale_head_never_stages_revision(fault):
    use_case, repo, command, ledger, raw, _ = case()
    if fault == "receipt":
        ledger.calculation_lineage["output_content_hash"] = "0" * 64
    elif fault == "raw":
        raw["tenant_id"] = "foreign"
    elif fault == "owner":
        ledger.portfolio_id = "foreign"
    elif fault == "head":
        retained = storage.retained_source_facts(ledger, OutboxEvent(id=7, payload=raw), None)
        head = use_case._revision(command, retained, attestation_hash="9" * 64)
        repo.lock_retained_source.side_effect = None
        repo.lock_retained_source.return_value = replace(
            retained, head=replace(head, revision_id="new", revision_sha256="9" * 64)
        )
    else:
        ledger.realized_total_pnl_local = Decimal("999")
    with pytest.raises(application.SourceCorrectionRejected):
        await use_case.execute(command)
    repo.stage_revision_and_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_unused_refuses_before_owner_lock():
    use_case, repo, command, *_ = case()
    use_case._clock = lambda: datetime.fromtimestamp(NOW.timestamp() + 200, UTC)
    with pytest.raises(CommandAuthorizationRejected, match="EXPIRED"):
        await use_case.execute(command)
    repo.lock_retained_source.assert_not_awaited()
    repo.stage_revision_and_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_original_receipt_with_nonzero_capital_is_not_corrected_or_replayed():
    use_case, repo, command, *_ = case(source_capital=Decimal("100"))
    with pytest.raises(application.SourceCorrectionRejected, match="EVIDENCE_REJECTED"):
        await use_case.execute(command)
    repo.stage_revision_and_notification.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("after_wait", [False, True])
async def test_exact_committed_replay_and_concurrent_reread_do_not_create_effect(after_wait):
    use_case, repo, command, ledger, raw, policy = case()
    claims = command.authorization.claims
    authenticated = authenticate_command_authorization(
        command.authorization,
        expected_request_sha256=claims.canonical_request_sha256,
        policy=policy,
    )
    existing = use_case._revision(
        command,
        storage.retained_source_facts(ledger, OutboxEvent(id=7, payload=raw), None),
        attestation_hash=authenticated.attestation_sha256,
    )
    repo.read_committed_source.return_value = replace(
        storage.retained_source_facts(ledger, OutboxEvent(id=7, payload=raw), None), head=existing
    )
    repo.committed_command.side_effect = [None, existing] if after_wait else [existing]
    if not after_wait:
        use_case._clock = lambda: datetime.fromtimestamp(NOW.timestamp() + 200, UTC)
    result = await use_case.execute(command)
    assert result is existing
    assert repo.lock_retained_source.await_count == int(after_wait)
    repo.stage_revision_and_notification.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "partial",
        "hash",
        "source",
        "root",
        "head",
        "receipt",
        "presence",
        "claims",
        "raw",
        "output",
        "retained-receipt",
        "disappeared",
    ],
)
async def test_expired_retry_requires_qualified_complete_fact_even_after_rehash(fault):
    use_case, repo, command, ledger, raw, _ = case()
    existing_fact = await use_case.execute(command)
    existing = TransactionSourceRevision(**existing_fact.material())
    repo.stage_revision_and_notification.reset_mock()
    repo.committed_command.side_effect = None
    repo.committed_command.side_effect = lambda **kwargs: storage.source_revision_fact(existing)
    repo.read_committed_source.side_effect = lambda revision: storage.retained_source_facts(
        ledger, OutboxEvent(id=7, payload=raw), existing
    )
    use_case._clock = lambda: datetime.fromtimestamp(NOW.timestamp() + 200, UTC)
    if fault == "partial":
        existing.qualification_receipt = None
    elif fault == "hash":
        existing.revision_sha256 = "0" * 64
    elif fault == "source":
        existing.source_local = Decimal("1")
    elif fault == "root":
        existing.root_raw_sha256 = "0" * 64
    elif fault == "head":
        existing.expected_head_sha256 = "0" * 64
    elif fault == "receipt":
        existing.qualification_receipt = dict(existing.qualification_receipt) | {
            "algorithm_id": "fake"
        }
    elif fault == "presence":
        existing.original_local_present = True
    elif fault == "claims":
        existing.authorization_claims = dict(existing.authorization_claims) | {
            "actor_id": "foreign"
        }
    elif fault == "raw":
        raw["realized_fx_pnl_base"] = "999"
    elif fault == "output":
        ledger.realized_total_pnl_base = Decimal("999")
    elif fault == "retained-receipt":
        ledger.calculation_lineage = dict(ledger.calculation_lineage) | {
            "output_content_hash": "0" * 64
        }
    else:
        repo.read_committed_source.side_effect = lambda revision: storage.retained_source_facts(
            ledger, OutboxEvent(id=7, payload=raw), None
        )
    if fault != "hash":
        existing.revision_sha256 = canonical_content_hash(
            {
                column.name: getattr(existing, column.name)
                for column in existing.__table__.columns
                if column.name != "revision_sha256"
            }
        )
    with pytest.raises(application.SourceCorrectionRejected, match="FACT_UNVERIFIED"):
        await use_case.execute(command)
    repo.lock_admitted_operation.assert_awaited_once()  # Only the original first effect.
    repo.lock_retained_source.assert_awaited_once()
    repo.stage_revision_and_notification.assert_not_awaited()
