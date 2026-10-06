"""Independent read-only proof projection for the existing operation owner."""

from collections.abc import Mapping
from typing import cast

from portfolio_common.api_contract.async_commands import AsyncCommandStatus
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
from portfolio_common.domain.transaction.source_evidence_revision import (
    verify_confirmed_fx_revision,
)
from portfolio_common.event_contracts import TransactionSourceCorrectionRequestedEvent
from portfolio_common.events import TransactionEvent
from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased


class SourceCorrectionOperationNotFound(ValueError):
    pass


def verified_revision_identity(
    revision: TransactionSourceRevision,
    command_event: OutboxEvent,
    raw: OutboxEvent,
    transaction: Transaction,
    policy: CommandAuthorizationPolicy,
    *,
    now: int,
) -> tuple[str, str]:
    """Share committed-fact qualification with no-effect retry admission."""
    command = TransactionSourceCorrectionRequestedEvent.model_validate(command_event.payload)
    claims = command.authorization.claims
    verify_command_authorization(
        command.authorization,
        expected_request_sha256=command.body.canonical_request_sha256(
            target_transaction_id=cast(str, transaction.transaction_id)
        ),
        policy=policy,
        now=now,
        committed=CommittedCommandVerification(
            cast(str, revision.tenant_id),
            cast(str, revision.command_id),
            cast(str, revision.canonical_request_sha256),
            cast(str, revision.attestation_sha256),
        ),
    )
    raw_payload: object = raw.payload
    if not isinstance(raw_payload, Mapping):
        raise ValueError("SOURCE_REVISION_FACT_UNVERIFIED")
    TransactionEvent.model_validate(raw_payload)
    output = {
        column.name: getattr(transaction, column.name)
        for column in Transaction.__table__.columns
        if column.name not in {"id", "updated_at", "payload_fingerprint", "calculation_lineage"}
    } | {"tenant_id": claims.tenant_id}
    verify_confirmed_fx_revision(
        revision={
            column.name: getattr(revision, column.name) for column in revision.__table__.columns
        },
        authenticated_claims=claims.model_dump(mode="json"),
        reason=command.body.reason,
        portfolio_id=command.portfolio_id,
        raw_id=cast(int, raw.id),
        raw_source=raw_payload,
        ledger_output=output,
        stored_fingerprint=cast(str, transaction.payload_fingerprint),
        original_receipt=transaction.calculation_lineage,
        supplied_bases=command.body.supplied_bases,
        local=command.body.realized_pnl_local,
        base=command.body.realized_pnl_base,
    )
    return cast(str, revision.revision_id), cast(str, revision.revision_sha256)


class SqlAlchemySourceCorrectionOperationStatus:
    def __init__(self, db: AsyncSession, policy: CommandAuthorizationPolicy | None = None) -> None:
        self._db, self._policy = db, policy

    async def read(self, *, tenant_id: str, operation_id: str, now: int) -> AsyncCommandStatus:
        policy = self._policy if self._policy is not None else load_command_authorization_policy()
        try:
            return await self._read(
                tenant_id=tenant_id, operation_id=operation_id, now=now, policy=policy
            )
        except SQLAlchemyError:
            raise RuntimeError("SOURCE_COMMAND_OPERATION_UNAVAILABLE") from None

    async def _read(
        self, *, tenant_id: str, operation_id: str, now: int, policy: CommandAuthorizationPolicy
    ) -> AsyncCommandStatus:
        command, raw = aliased(OutboxEvent), aliased(OutboxEvent)
        # One statement snapshot; never mix stale operation/result/owner reads.
        query = select(
            IngestionJob, TransactionSourceRevision, command, raw, Transaction, Portfolio.tenant_id
        )
        query = (
            query.outerjoin(
                TransactionSourceRevision,
                and_(
                    TransactionSourceRevision.tenant_id == IngestionJob.tenant_id,
                    TransactionSourceRevision.operation_id == IngestionJob.job_id,
                ),
            )
            .outerjoin(
                command,
                and_(
                    command.ingestion_job_id == IngestionJob.job_id,
                    command.aggregate_type == "TransactionSourceCorrectionCommand",
                    command.event_type == "TransactionSourceCorrectionRequested",
                    command.aggregate_id == IngestionJob.job_id,
                    command.topic == KAFKA_TRANSACTIONS_SOURCE_CORRECTION_COMMANDS_TOPIC,
                ),
            )
            .outerjoin(raw, raw.id == TransactionSourceRevision.root_raw_event_id)
            .outerjoin(
                Transaction, Transaction.transaction_id == TransactionSourceRevision.transaction_id
            )
            .where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.job_id == operation_id,
                IngestionJob.entity_type == "transaction_source_correction",
            )
        )
        query = query.outerjoin(
            Portfolio,
            and_(
                Portfolio.portfolio_id == Transaction.portfolio_id,
                Portfolio.tenant_id == IngestionJob.tenant_id,
            ),
        )
        rows = (await self._db.execute(query)).all()
        if not rows:
            raise SourceCorrectionOperationNotFound("SOURCE_COMMAND_OPERATION_NOT_FOUND")
        unavailable = AsyncCommandStatus(
            operation_id=operation_id,
            status="UNAVAILABLE",
            reason_code="SOURCE_COMMAND_AUTHORITY_UNAVAILABLE",
        )
        if len(rows) != 1:
            return unavailable
        job, revision, command_event, raw_event, transaction, owner = rows[0]
        if (
            command_event is None
            or job.endpoint != "/ingest/transactions/{transaction_id}/source-evidence"
            or job.accepted_count != 1
        ):
            return unavailable
        if revision is not None:
            if (
                owner != tenant_id
                or raw_event is None
                or transaction is None
                or job.status not in {"accepted", "queued"}
            ):
                return unavailable
            try:
                revision_id, digest = verified_revision_identity(
                    revision, command_event, raw_event, transaction, policy, now=now
                )
            except (ValueError, TypeError, ArithmeticError):
                return unavailable
            return AsyncCommandStatus(
                operation_id=operation_id,
                status="SUCCEEDED",
                revision_id=revision_id,
                revision_sha256=digest,
            )
        if job.status == "failed":
            return AsyncCommandStatus(
                operation_id=operation_id, status="FAILED", reason_code="SOURCE_COMMAND_FAILED"
            )
        if job.status in {"accepted", "queued"}:
            return AsyncCommandStatus(operation_id=operation_id, status="QUEUED")
        return unavailable
