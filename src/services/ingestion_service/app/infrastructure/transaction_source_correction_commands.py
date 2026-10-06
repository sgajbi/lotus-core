"""Stage a signed source command inside the existing operation-creation UOW."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import cast

from portfolio_common.command_authorization import (
    SOURCE_CORRECTION_CAPABILITY,
    CommandAuthorizationClaims,
    CommandAuthorizationPolicy,
    CommandAuthorizationRejected,
    sign_command_authorization,
)
from portfolio_common.config import KAFKA_TRANSACTIONS_SOURCE_CORRECTION_COMMANDS_TOPIC
from portfolio_common.database_models import IngestionJob, OutboxEvent, Portfolio, Transaction
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.event_contracts import TransactionSourceCorrectionRequestedEvent
from portfolio_common.ingestion_lineage import ingestion_job_scope
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.transaction_source_corrections import (
    SourceCorrectionSubmission,
    SourceCorrectionSubmissionRejected,
)


class SqlAlchemySourceCorrectionCommandStager:
    def __init__(
        self,
        submission: SourceCorrectionSubmission,
        policy: CommandAuthorizationPolicy,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._submission, self._policy, self._clock = submission, policy, clock
        # Fail before operation creation, including when local HTTP auth is off.
        context, principal = submission.tenant_context, submission.principal
        signers = [
            item
            for item in policy.enrollments
            if item.principal == principal.service_identity
            and item.signing_enabled
            and item.capability == SOURCE_CORRECTION_CAPABILITY
        ]
        if (
            not context.identity_verified
            or context.service_identity != principal.service_identity
            or SOURCE_CORRECTION_CAPABILITY not in principal.capabilities
            or len(signers) != 1
        ):
            raise CommandAuthorizationRejected("COMMAND_CORRECTION_GRANT_REQUIRED")
        self._signer = signers[0]

    async def stage(self, db: AsyncSession, job: IngestionJob) -> None:
        if not db.in_transaction():
            raise SourceCorrectionSubmissionRejected("SOURCE_COMMAND_UOW_REQUIRED")
        submission = self._submission
        tenant = submission.tenant_context.tenant_id_text
        if job.tenant_id != tenant:
            raise SourceCorrectionSubmissionRejected("SOURCE_COMMAND_OWNER_MISMATCH")
        portfolio = await db.scalar(
            select(Transaction.portfolio_id)
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(
                Transaction.transaction_id == submission.target_transaction_id,
                Portfolio.tenant_id == tenant,
            )
        )
        if portfolio is None:
            raise SourceCorrectionSubmissionRejected("SOURCE_COMMAND_TARGET_UNAVAILABLE")
        result = await db.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_type == "RawTransaction",
                OutboxEvent.aggregate_id == portfolio,
                OutboxEvent.event_type == "RawTransactionPersisted",
                OutboxEvent.payload["portfolio_id"].as_string() == portfolio,
                OutboxEvent.payload["transaction_id"].as_string()
                == submission.target_transaction_id,
            )
            .limit(2)
        )
        roots = result.scalars().all()
        if len(roots) != 1:
            raise SourceCorrectionSubmissionRejected("SOURCE_COMMAND_RAW_UNAVAILABLE")
        root = roots[0]
        raw_payload: object = root.payload
        if not isinstance(raw_payload, Mapping):
            raise SourceCorrectionSubmissionRejected("SOURCE_COMMAND_RAW_UNAVAILABLE")
        try:
            raw_hash = canonical_content_hash(raw_payload)
        except (TypeError, ValueError, ArithmeticError):
            raise SourceCorrectionSubmissionRejected("SOURCE_COMMAND_RAW_UNAVAILABLE") from None
        now = int(self._clock().timestamp())
        operation_id = cast(str, job.job_id)
        claims = CommandAuthorizationClaims(
            issuer=self._signer.issuer,
            key_id=self._signer.key_id,
            principal=submission.principal.service_identity,
            actor_id=submission.tenant_context.actor_id or submission.principal.service_identity,
            tenant_id=tenant,
            command_id=operation_id,
            operation_id=operation_id,
            target_transaction_id=submission.target_transaction_id,
            root_raw_id=str(root.id),
            root_raw_sha256=raw_hash,
            expected_head_id=submission.body.expected_head_id,
            expected_head_sha256=submission.body.expected_head_sha256,
            canonical_request_sha256=submission.body.canonical_request_sha256(
                target_transaction_id=submission.target_transaction_id
            ),
            issued_at=now,
            expires_at=now + self._policy.max_ttl_seconds,
            nonce=operation_id,
            correlation_id=submission.correlation_id,
            trace_id=submission.trace_id,
        )
        command = TransactionSourceCorrectionRequestedEvent(
            event_type="TransactionSourceCorrectionRequested",
            schema_version="1.0.0",
            source_system="ingestion_service",
            trace_id=submission.trace_id,
            idempotency_key=operation_id,
            authorization=sign_command_authorization(
                claims,
                principal=submission.principal,
                tenant_context=submission.tenant_context,
                policy=self._policy,
                now=now,
            ),
            body=submission.body,
            tenant_id=tenant,
            portfolio_id=portfolio,
            correlation_id=submission.correlation_id,
        )
        with ingestion_job_scope(operation_id):
            await OutboxRepository(db).create_outbox_event(
                aggregate_type="TransactionSourceCorrectionCommand",
                aggregate_id=operation_id,
                partition_key=submission.target_transaction_id,
                event_type="TransactionSourceCorrectionRequested",
                topic=KAFKA_TRANSACTIONS_SOURCE_CORRECTION_COMMANDS_TOPIC,
                correlation_id=submission.correlation_id,
                payload=command.model_dump(mode="json", exclude_unset=True),
            )
