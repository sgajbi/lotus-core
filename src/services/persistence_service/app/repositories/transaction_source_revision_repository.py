"""Source-revision storage uses the consumer-owned CoreDB transaction only."""

from collections.abc import Mapping
from typing import cast

from portfolio_common.config import (
    KAFKA_TRANSACTIONS_SOURCE_CORRECTION_COMMANDS_TOPIC,
    KAFKA_TRANSACTIONS_SOURCE_EVIDENCE_CHANGED_TOPIC,
)
from portfolio_common.database_models import (
    IngestionJob,
    OutboxEvent,
    Portfolio,
    Transaction,
    TransactionSourceRevision,
)
from portfolio_common.event_contracts import (
    TransactionSourceCorrectionRequestedEvent,
    TransactionSourceEvidenceChangedEvent,
)
from portfolio_common.events import TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository
from pydantic import ValidationError
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..ports.transaction_source_facts import (
    RawSourceSnapshot,
    RetainedSourceRows,
    RetainedTransactionSnapshot,
    SourceInputRejected,
    SourceOperationIntent,
    SourceRevisionFact,
)

_TECHNICAL_FIELDS = frozenset({"id", "updated_at", "payload_fingerprint", "calculation_lineage"})


def source_revision_fact(row: TransactionSourceRevision) -> SourceRevisionFact:
    # Reflect every mapped column. A future column must expand the explicit fact
    # schema and its projection test; never silently omit new financial authority.
    return SourceRevisionFact.from_material(
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
    )


def retained_source_facts(
    transaction: Transaction, raw: OutboxEvent, head: TransactionSourceRevision | None
) -> RetainedSourceRows:
    return RetainedSourceRows(
        RetainedTransactionSnapshot(
            portfolio_id=cast(str, transaction.portfolio_id),
            transaction_id=cast(str, transaction.transaction_id),
            ledger_output={
                column.name: getattr(transaction, column.name)
                for column in Transaction.__table__.columns
                if column.name not in _TECHNICAL_FIELDS
            },
            stored_fingerprint=cast(str | None, transaction.payload_fingerprint),
            original_receipt=transaction.calculation_lineage,
        ),
        RawSourceSnapshot(cast(int, raw.id), raw.payload),
        source_revision_fact(head) if head is not None else None,
    )


class SourceRevisionStorageRejected(ValueError):
    """Bounded storage refusal without source identifiers or payload values."""


class TransactionSourceRevisionRepository:
    def __init__(self, db: AsyncSession) -> None:
        # Injected CoreDB UOW is owned by GenericPersistenceConsumer. Never
        # create, commit, rollback or close another session here.
        self._db = db

    @staticmethod
    def normalize_command(
        command: TransactionSourceCorrectionRequestedEvent,
    ) -> TransactionSourceCorrectionRequestedEvent:
        try:
            return TransactionSourceCorrectionRequestedEvent.model_validate(
                command.model_dump(mode="python", exclude_unset=True)
            )
        except ValidationError:
            raise SourceInputRejected("SOURCE_COMMAND_INVALID") from None

    @staticmethod
    def decode_admitted_intent(payload: object) -> TransactionSourceCorrectionRequestedEvent:
        try:
            return TransactionSourceCorrectionRequestedEvent.model_validate(payload)
        except ValidationError:
            raise SourceInputRejected("SOURCE_COMMAND_OPERATION_UNAVAILABLE") from None

    @staticmethod
    def validate_retained_input(payload: Mapping[str, object]) -> None:
        try:
            TransactionEvent.model_validate(payload)
        except ValidationError:
            raise SourceInputRejected("SOURCE_REVISION_EVIDENCE_REJECTED") from None

    def _require_uow(self) -> None:
        if not self._db.in_transaction():
            raise SourceRevisionStorageRejected("SOURCE_REVISION_UOW_REQUIRED")

    async def committed_command(
        self, *, tenant_id: str, command_id: str
    ) -> SourceRevisionFact | None:
        self._require_uow()
        result = await self._db.execute(
            select(TransactionSourceRevision).where(
                TransactionSourceRevision.tenant_id == tenant_id,
                TransactionSourceRevision.command_id == command_id,
            )
        )
        row = result.scalar_one_or_none()
        return source_revision_fact(row) if row is not None else None

    async def read_committed_source(self, revision: SourceRevisionFact) -> RetainedSourceRows:
        """Read linked immutable fact and tenant-owned source in one statement snapshot.

        No lock is acquired on the no-effect retry path. The application must
        independently qualify the complete fact and retained source/receipt.
        """
        self._require_uow()
        result = await self._db.execute(
            select(Transaction, OutboxEvent, TransactionSourceRevision)
            .select_from(TransactionSourceRevision)
            .join(
                Transaction, Transaction.transaction_id == TransactionSourceRevision.transaction_id
            )
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .join(OutboxEvent, OutboxEvent.id == TransactionSourceRevision.root_raw_event_id)
            .where(
                TransactionSourceRevision.revision_id == revision.revision_id,
                TransactionSourceRevision.revision_sha256 == revision.revision_sha256,
                Portfolio.tenant_id == revision.tenant_id,
                Transaction.portfolio_id == revision.portfolio_id,
                OutboxEvent.aggregate_type == "RawTransaction",
                OutboxEvent.event_type == "RawTransactionPersisted",
            )
        )
        row = result.one_or_none()
        if row is None:
            raise SourceRevisionStorageRejected("SOURCE_REVISION_COMMITTED_SOURCE_UNAVAILABLE")
        transaction, raw, fact = row
        return retained_source_facts(transaction, raw, fact)

    async def _lock_owned_transaction(self, *, tenant_id: str, transaction_id: str) -> Transaction:
        scope_result = await self._db.execute(
            select(Transaction.portfolio_id)
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(Transaction.transaction_id == transaction_id, Portfolio.tenant_id == tenant_id)
        )
        portfolio_id = scope_result.scalar_one_or_none()
        if portfolio_id is None:
            raise SourceRevisionStorageRejected("SOURCE_REVISION_TARGET_UNAVAILABLE")
        owner_result = await self._db.execute(
            select(Portfolio.portfolio_id)
            .where(Portfolio.portfolio_id == portfolio_id, Portfolio.tenant_id == tenant_id)
            .with_for_update(of=Portfolio, read=True, key_share=True)
        )
        if owner_result.scalar_one_or_none() != portfolio_id:
            raise SourceRevisionStorageRejected("SOURCE_REVISION_TARGET_UNAVAILABLE")
        result = await self._db.execute(
            select(Transaction)
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(Transaction.transaction_id == transaction_id, Portfolio.tenant_id == tenant_id)
            .with_for_update(of=Transaction)
        )
        transaction = result.scalar_one_or_none()
        if transaction is None:
            raise SourceRevisionStorageRejected("SOURCE_REVISION_TARGET_UNAVAILABLE")
        if transaction.portfolio_id != portfolio_id:
            # Never follow a changed scope by acquiring another portfolio after
            # the target lock; abort this UOW and retain the global lock order.
            raise SourceRevisionStorageRejected("SOURCE_REVISION_OWNER_CHANGED")
        return transaction

    async def lock_admitted_operation(
        self, *, tenant_id: str, operation_id: str, command_id: str
    ) -> SourceOperationIntent:
        """Operation SHARE precedes every canonical lock, with no later upgrade.

        KEY SHARE alone does not fence status/tenant updates. SHARE prevents both
        non-key and key updates throughout this borrowed UOW. Exact committed
        retries are authenticated before admission and acquire no new effects.
        """
        self._require_uow()
        result = await self._db.execute(
            select(IngestionJob)
            .where(IngestionJob.tenant_id == tenant_id, IngestionJob.job_id == operation_id)
            .with_for_update(of=IngestionJob, read=True)
        )
        job = result.scalar_one_or_none()
        if (
            job is None
            or job.entity_type != "transaction_source_correction"
            or job.endpoint != "/ingest/transactions/{transaction_id}/source-evidence"
            or job.status not in {"accepted", "queued"}
            or job.accepted_count != 1
        ):
            raise SourceRevisionStorageRejected("SOURCE_COMMAND_OPERATION_UNAVAILABLE")
        events = (
            (
                await self._db.execute(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.ingestion_job_id == operation_id,
                        OutboxEvent.aggregate_id == operation_id,
                        OutboxEvent.aggregate_type == "TransactionSourceCorrectionCommand",
                        OutboxEvent.event_type == "TransactionSourceCorrectionRequested",
                        OutboxEvent.topic == KAFKA_TRANSACTIONS_SOURCE_CORRECTION_COMMANDS_TOPIC,
                        OutboxEvent.payload["authorization"]["claims"]["command_id"].as_string()
                        == command_id,
                    )
                    .limit(2)
                )
            )
            .scalars()
            .all()
        )
        if len(events) != 1:
            raise SourceRevisionStorageRejected("SOURCE_COMMAND_OPERATION_UNAVAILABLE")
        return SourceOperationIntent(events[0].payload)

    async def lock_retained_source(
        self, *, tenant_id: str, transaction_id: str
    ) -> RetainedSourceRows:
        """Lock Portfolio -> Transaction -> raw root -> predecessor/head.

        Explicit KEY SHARE covers the FK references later checked by flush.
        This source order is not proof of PostgreSQL deadlock or CAS behavior.
        """
        self._require_uow()
        transaction = await self._lock_owned_transaction(
            tenant_id=tenant_id, transaction_id=transaction_id
        )
        raw_result = await self._db.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_type == "RawTransaction",
                OutboxEvent.aggregate_id == transaction.portfolio_id,
                OutboxEvent.event_type == "RawTransactionPersisted",
                OutboxEvent.payload["portfolio_id"].as_string() == transaction.portfolio_id,
                OutboxEvent.payload["transaction_id"].as_string() == transaction_id,
            )
            .limit(2)
            .with_for_update(of=OutboxEvent, read=True, key_share=True)
        )
        roots = raw_result.scalars().all()
        if len(roots) != 1:
            raise SourceRevisionStorageRejected("SOURCE_REVISION_RAW_AUTHORITY_UNAVAILABLE")
        child = aliased(TransactionSourceRevision)
        head_result = await self._db.execute(
            select(TransactionSourceRevision)
            .where(
                TransactionSourceRevision.tenant_id == tenant_id,
                TransactionSourceRevision.transaction_id == transaction_id,
                ~exists().where(
                    child.predecessor_revision_id == TransactionSourceRevision.revision_id
                ),
            )
            .with_for_update(of=TransactionSourceRevision, read=True, key_share=True)
        )
        heads = head_result.scalars().all()
        if len(heads) > 1 or (heads and heads[0].root_raw_event_id != roots[0].id):
            raise SourceRevisionStorageRejected("SOURCE_REVISION_CHAIN_UNAVAILABLE")
        return retained_source_facts(transaction, roots[0], heads[0] if heads else None)

    async def stage_revision_and_notification(self, revision: SourceRevisionFact) -> None:
        """Stage only the new fact and notification, never economics or completion.

        The application must verify attestation, receipt, source policy and CAS
        before calling this method. Flush is not commit or HTTP success proof.
        """
        self._require_uow()
        self._db.add(TransactionSourceRevision(**revision.material()))
        await self._db.flush()
        await OutboxRepository(self._db).create_outbox_event(
            aggregate_type="TransactionSourceRevision",
            aggregate_id=cast(str, revision.revision_id),
            partition_key=cast(str, revision.transaction_id),
            event_type="TransactionSourceEvidenceChanged",
            topic=KAFKA_TRANSACTIONS_SOURCE_EVIDENCE_CHANGED_TOPIC,
            correlation_id=cast(str, revision.correlation_id),
            payload=TransactionSourceEvidenceChangedEvent.model_validate(
                {
                    "event_type": "TransactionSourceEvidenceChanged",
                    "schema_version": "1.0.0",
                    "source_system": "persistence_service",
                    "idempotency_key": revision.revision_id,
                    "revision_id": revision.revision_id,
                    "revision_sha256": revision.revision_sha256,
                    "transaction_id": revision.transaction_id,
                    "portfolio_id": revision.portfolio_id,
                    "tenant_id": revision.tenant_id,
                    "operation_id": revision.operation_id,
                    "root_raw_event_id": revision.root_raw_event_id,
                    "correlation_id": revision.correlation_id,
                    "trace_id": revision.trace_id,
                }
            ).model_dump(mode="json", exclude_none=True),
        )
