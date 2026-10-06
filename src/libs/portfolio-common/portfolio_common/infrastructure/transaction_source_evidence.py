"""Batched tenant-owned source qualification using a borrowed read snapshot."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TypedDict, cast

from sqlalchemy import and_, exists, false, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from portfolio_common.api_contract.transaction_source_evidence import (
    SourceEvidenceConsumer,
    SourceEvidenceSelection,
    TransactionSourceEvidence,
)
from portfolio_common.command_authorization import (
    CommandAuthorizationPolicy,
    CommittedCommandVerification,
    load_command_authorization_policy,
    verify_command_authorization,
)
from portfolio_common.config import KAFKA_TRANSACTIONS_SOURCE_CORRECTION_COMMANDS_TOPIC
from portfolio_common.database_models import (
    IngestionJob,
    OutboxEvent,
    Portfolio,
    Transaction,
    TransactionSourceRevision,
)
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.transaction.source_evidence_revision import (
    verify_confirmed_fx_revision,
    verify_retained_fx_source,
)
from portfolio_common.event_contracts import TransactionSourceCorrectionRequestedEvent

_TECHNICAL_FIELDS = frozenset({"id", "updated_at", "payload_fingerprint", "calculation_lineage"})


class _SourceIdentity(TypedDict):
    tenant_id: str
    portfolio_id: str
    transaction_id: str
    consumer: SourceEvidenceConsumer
    selection: SourceEvidenceSelection


def _material_source_row(row: tuple, tenant_id: str) -> dict[str, object]:
    transaction, root, revision, intent, operation = row
    return {
        "booked_output": transaction_receipt_output(transaction, tenant_id),
        "original_receipt": transaction.calculation_lineage,
        "original_fingerprint": transaction.payload_fingerprint,
        "root": {"id": root.id, "payload": root.payload} if root is not None else None,
        "revision": {
            column.name: getattr(revision, column.name)
            for column in TransactionSourceRevision.__table__.columns
        }
        if revision is not None
        else None,
        "intent": intent.payload if intent is not None else None,
        "operation": {
            "tenant_id": operation.tenant_id,
            "job_id": operation.job_id,
            "entity_type": operation.entity_type,
            "endpoint": operation.endpoint,
            "status": operation.status,
            "accepted_count": operation.accepted_count,
        }
        if operation is not None
        else None,
    }


def transaction_receipt_output(transaction: Transaction, tenant_id: str) -> dict[str, object]:
    return {
        column.name: getattr(transaction, column.name)
        for column in Transaction.__table__.columns
        if column.name not in _TECHNICAL_FIELDS
    } | {"tenant_id": tenant_id}


class SqlAlchemyTransactionSourceEvidence:
    """No new session, locks, writes, commit or arbitrary latest-time selection."""

    def __init__(self, session: AsyncSession, policy: CommandAuthorizationPolicy | None = None):
        self._session, self._policy = session, policy

    async def read(
        self,
        *,
        tenant_id: str,
        portfolio_id: str,
        transaction_ids: Sequence[str],
        consumer: SourceEvidenceConsumer,
        selection: SourceEvidenceSelection = "current",
        revision_id: str | None = None,
    ) -> dict[str, TransactionSourceEvidence]:
        if not transaction_ids:
            return {}
        if (selection == "revision") != (revision_id is not None):
            raise ValueError("SOURCE_EVIDENCE_SELECTION_INVALID")
        raw, command, child = (
            aliased(OutboxEvent),
            aliased(OutboxEvent),
            aliased(TransactionSourceRevision),
        )
        revision_match = [
            TransactionSourceRevision.tenant_id == tenant_id,
            TransactionSourceRevision.portfolio_id == portfolio_id,
            TransactionSourceRevision.transaction_id == Transaction.transaction_id,
            TransactionSourceRevision.root_raw_event_id == raw.id,
        ]
        if selection == "original":
            # Unselected correction metadata must not enter the immutable original cut.
            revision_match.append(false())
        elif selection == "revision":
            revision_match.append(TransactionSourceRevision.revision_id == revision_id)
        else:
            revision_match.append(
                ~exists().where(
                    child.tenant_id == tenant_id,
                    child.transaction_id == Transaction.transaction_id,
                    child.predecessor_revision_id == TransactionSourceRevision.revision_id,
                )
            )
        statement = (
            select(Transaction, raw, TransactionSourceRevision, command, IngestionJob)
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .outerjoin(
                raw,
                and_(
                    raw.aggregate_type == "RawTransaction",
                    raw.event_type == "RawTransactionPersisted",
                    raw.aggregate_id == portfolio_id,
                    raw.payload["portfolio_id"].as_string() == portfolio_id,
                    raw.payload["transaction_id"].as_string() == Transaction.transaction_id,
                ),
            )
            .outerjoin(TransactionSourceRevision, and_(*revision_match))
            .outerjoin(
                command,
                and_(
                    command.ingestion_job_id == TransactionSourceRevision.operation_id,
                    command.aggregate_id == TransactionSourceRevision.operation_id,
                    command.aggregate_type == "TransactionSourceCorrectionCommand",
                    command.event_type == "TransactionSourceCorrectionRequested",
                    command.topic == KAFKA_TRANSACTIONS_SOURCE_CORRECTION_COMMANDS_TOPIC,
                ),
            )
            .outerjoin(
                IngestionJob,
                and_(
                    IngestionJob.tenant_id == tenant_id,
                    IngestionJob.job_id == TransactionSourceRevision.operation_id,
                ),
            )
            .where(
                Portfolio.tenant_id == tenant_id,
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_id.in_(transaction_ids),
            )
        )
        rows = (await self._session.execute(statement)).all()
        grouped: dict[str, list] = defaultdict(list)
        for row in rows:
            grouped[row[0].transaction_id].append(row)
        results = {}
        for transaction_id in transaction_ids:
            identity = _SourceIdentity(
                tenant_id=tenant_id,
                portfolio_id=portfolio_id,
                transaction_id=transaction_id,
                consumer=consumer,
                selection=selection,
            )
            candidates = grouped[transaction_id]
            # Cut includes all material candidates, even when qualification fails.
            material = sorted(
                [_material_source_row(row, tenant_id) for row in candidates],
                key=canonical_content_hash,
            )
            digest = canonical_content_hash({"scope": identity, "source_candidates": material})
            unavailable = TransactionSourceEvidence(
                **identity, status="UNAVAILABLE", source_cut_sha256=digest
            )
            if len(candidates) != 1:
                results[transaction_id] = unavailable
                continue
            transaction, root, revision, intent, operation = candidates[0]
            try:
                results[transaction_id] = self._qualify(
                    identity=identity,
                    transaction=transaction,
                    root=root,
                    revision=None if selection == "original" else revision,
                    intent=intent,
                    operation=operation,
                    digest=digest,
                )
                if selection == "revision" and revision is None:
                    results[transaction_id] = unavailable
            except (TypeError, ValueError, ArithmeticError):
                results[transaction_id] = unavailable
        return results

    def _qualify(
        self,
        *,
        identity: _SourceIdentity,
        transaction: Transaction,
        root: OutboxEvent | None,
        revision: TransactionSourceRevision | None,
        intent: OutboxEvent | None,
        operation: IngestionJob | None,
        digest: str,
    ) -> TransactionSourceEvidence:
        if root is None or not isinstance(root.payload, Mapping):
            raise ValueError("SOURCE_EVIDENCE_ROOT_UNAVAILABLE")
        output = transaction_receipt_output(transaction, identity["tenant_id"])
        original = verify_retained_fx_source(
            raw_source=root.payload,
            ledger_output=output,
            stored_fingerprint=transaction.payload_fingerprint,
            receipt_payload=transaction.calculation_lineage,
            tenant_id=identity["tenant_id"],
        )
        local, base = original.local.source, original.base.source
        if revision is not None:
            if (
                intent is None
                or operation is None
                or operation.status not in {"accepted", "queued"}
                or operation.entity_type != "transaction_source_correction"
                or operation.endpoint != "/ingest/transactions/{transaction_id}/source-evidence"
                or operation.accepted_count != 1
            ):
                raise ValueError("SOURCE_EVIDENCE_INTENT_UNAVAILABLE")
            command = TransactionSourceCorrectionRequestedEvent.model_validate(intent.payload)
            policy = (
                self._policy if self._policy is not None else load_command_authorization_policy()
            )
            claims = verify_command_authorization(
                command.authorization,
                expected_request_sha256=command.body.canonical_request_sha256(
                    target_transaction_id=transaction.transaction_id
                ),
                policy=policy,
                now=int(datetime.now(UTC).timestamp()),
                committed=CommittedCommandVerification(
                    revision.tenant_id,
                    revision.command_id,
                    revision.canonical_request_sha256,
                    revision.attestation_sha256,
                ),
            ).claims
            verify_confirmed_fx_revision(
                revision={
                    column.name: getattr(revision, column.name)
                    for column in revision.__table__.columns
                },
                authenticated_claims=claims.model_dump(mode="json"),
                reason=command.body.reason,
                portfolio_id=command.portfolio_id,
                raw_id=cast(int, root.id),
                raw_source=root.payload,
                ledger_output=output,
                stored_fingerprint=transaction.payload_fingerprint,
                original_receipt=transaction.calculation_lineage,
                supplied_bases=command.body.supplied_bases,
                local=command.body.realized_pnl_local,
                base=command.body.realized_pnl_base,
            )
            local, base = revision.source_local, revision.source_base
        return TransactionSourceEvidence(
            **identity,
            root_raw_id=str(root.id),
            root_raw_sha256=canonical_content_hash(root.payload),
            original_local_present=original.local.source is not None,
            original_base_present=original.base.source is not None,
            producer_algorithm_version=transaction.calculation_lineage["algorithm_version"],
            status=(
                "CONFIRMED"
                if revision is not None
                else "QUALIFIED"
                if local is not None and base is not None
                else "INCOMPLETE"
            ),
            revision_id=revision.revision_id if revision is not None else None,
            revision_sha256=revision.revision_sha256 if revision is not None else None,
            confirmed_at=revision.confirmed_at if revision is not None else None,
            realized_fx_pnl_local=local,
            realized_fx_pnl_base=base,
            source_cut_sha256=digest,
        )
