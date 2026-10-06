"""Authorize one immutable evidence revision within the consumer's CoreDB UOW."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from portfolio_common.command_authorization import (
    CommandAuthorizationPolicy,
    CommittedCommandVerification,
    authenticate_command_authorization,
    verify_command_authorization,
)
from portfolio_common.database_models import Transaction, TransactionSourceRevision
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.transaction.source_evidence_revision import (
    FxSourceEvidenceConfirmation,
    confirm_missing_fx_source,
    source_confirmation_material,
    verify_confirmed_fx_revision,
    verify_retained_fx_source,
)
from portfolio_common.event_contracts import TransactionSourceCorrectionRequestedEvent
from portfolio_common.events import TransactionEvent
from pydantic import ValidationError

from ..ports.transaction_source_corrections import (
    RetainedSourceRows,
    TransactionSourceRevisionPort,
)

_TECHNICAL_FIELDS = frozenset({"id", "updated_at", "payload_fingerprint", "calculation_lineage"})


class SourceCorrectionRejected(ValueError):
    """Bounded command refusal, never raw financial/source/auth payload text."""


@dataclass(frozen=True, slots=True)
class SourceCommandAdmission:
    command: TransactionSourceCorrectionRequestedEvent
    request_sha256: str
    committed: TransactionSourceRevision | None


class TransactionSourceCorrectionApplication:
    def __init__(
        self,
        repository: TransactionSourceRevisionPort,
        *,
        policy: CommandAuthorizationPolicy,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._clock = clock

    async def admit(
        self, command: TransactionSourceCorrectionRequestedEvent
    ) -> SourceCommandAdmission:
        """Authenticate before the consumer claims idempotency; stage no effects."""
        try:
            command = TransactionSourceCorrectionRequestedEvent.model_validate(
                command.model_dump(mode="python", exclude_unset=True)
            )
        except ValidationError:
            raise SourceCorrectionRejected("SOURCE_COMMAND_INVALID") from None
        claims = command.authorization.claims
        request_hash = command.body.canonical_request_sha256(
            target_transaction_id=claims.target_transaction_id
        )
        # Crypto/schema/digest precede any lookup of purported replay authority.
        authenticate_command_authorization(
            command.authorization, expected_request_sha256=request_hash, policy=self._policy
        )
        committed = await self._committed(command, request_hash=request_hash)
        if committed is not None:
            return SourceCommandAdmission(command, request_hash, committed)
        verify_command_authorization(
            command.authorization,
            expected_request_sha256=request_hash,
            policy=self._policy,
            now=int(self._clock().timestamp()),
        )
        return SourceCommandAdmission(command, request_hash, None)

    async def execute(
        self, command: TransactionSourceCorrectionRequestedEvent
    ) -> TransactionSourceRevision:
        admission = await self.admit(command)
        command = admission.command
        claims, request_hash = command.authorization.claims, admission.request_sha256
        if admission.committed is not None:
            return admission.committed
        await self._require_operation(command)
        retained = await self._repository.lock_retained_source(
            tenant_id=claims.tenant_id, transaction_id=claims.target_transaction_id
        )
        # A pre-lock miss cannot authorize another effect after a concurrent commit.
        committed = await self._committed(command, request_hash=request_hash)
        if committed is not None:
            return committed
        verified = verify_command_authorization(
            command.authorization,
            expected_request_sha256=request_hash,
            policy=self._policy,
            now=int(self._clock().timestamp()),
        )
        revision = self._revision(command, retained, attestation_hash=verified.attestation_sha256)
        await self._repository.stage_revision_and_notification(revision)
        return revision

    async def _require_operation(self, command: TransactionSourceCorrectionRequestedEvent) -> None:
        claims = command.authorization.claims
        intent = await self._repository.lock_admitted_operation(
            tenant_id=claims.tenant_id,
            operation_id=claims.operation_id,
            command_id=claims.command_id,
        )
        try:
            original = TransactionSourceCorrectionRequestedEvent.model_validate(intent.payload)
            same_input = (
                original.body.canonical_request_sha256(
                    target_transaction_id=claims.target_transaction_id
                )
                == claims.canonical_request_sha256
            )
        except (ValueError, TypeError, ArithmeticError):
            raise SourceCorrectionRejected("SOURCE_COMMAND_OPERATION_UNAVAILABLE") from None
        if (
            not same_input
            or original.authorization != command.authorization
            or original.portfolio_id != command.portfolio_id
            or original.tenant_id != command.tenant_id
        ):
            raise SourceCorrectionRejected("SOURCE_COMMAND_OPERATION_UNAVAILABLE")

    async def _committed(
        self, command: TransactionSourceCorrectionRequestedEvent, *, request_hash: str
    ) -> TransactionSourceRevision | None:
        claims = command.authorization.claims
        row = await self._repository.committed_command(
            tenant_id=claims.tenant_id, command_id=claims.command_id
        )
        if row is not None:
            if (
                row.transaction_id != claims.target_transaction_id
                or row.operation_id != claims.operation_id
                or row.portfolio_id != command.portfolio_id
                or str(row.root_raw_event_id) != claims.root_raw_id
            ):
                raise SourceCorrectionRejected("SOURCE_REVISION_DURABLE_REPLAY_CONFLICT")
            verify_command_authorization(
                command.authorization,
                expected_request_sha256=request_hash,
                policy=self._policy,
                now=int(self._clock().timestamp()),
                committed=CommittedCommandVerification(
                    cast(str, row.tenant_id),
                    cast(str, row.command_id),
                    cast(str, row.canonical_request_sha256),
                    cast(str, row.attestation_sha256),
                ),
            )
            retained = await self._repository.read_committed_source(row)
            row = retained.head
            if row is None:
                raise SourceCorrectionRejected("SOURCE_REVISION_FACT_UNVERIFIED")
            self._qualify_committed(command, row, retained)
        return row

    @staticmethod
    def _qualify_committed(
        command: TransactionSourceCorrectionRequestedEvent,
        row: TransactionSourceRevision,
        retained: RetainedSourceRows,
    ) -> None:
        raw_payload: object = retained.raw_event.payload
        if not isinstance(raw_payload, Mapping):
            raise SourceCorrectionRejected("SOURCE_REVISION_FACT_UNVERIFIED")
        try:
            TransactionEvent.model_validate(raw_payload)
            output = {
                column.name: getattr(retained.transaction, column.name)
                for column in Transaction.__table__.columns
                if column.name not in _TECHNICAL_FIELDS
            } | {"tenant_id": command.tenant_id}
            verify_confirmed_fx_revision(
                revision={
                    column.name: getattr(row, column.name) for column in row.__table__.columns
                },
                authenticated_claims=command.authorization.claims.model_dump(mode="json"),
                reason=command.body.reason,
                portfolio_id=command.portfolio_id,
                raw_id=cast(int, retained.raw_event.id),
                raw_source=raw_payload,
                ledger_output=output,
                stored_fingerprint=cast(str, retained.transaction.payload_fingerprint),
                original_receipt=retained.transaction.calculation_lineage,
                supplied_bases=command.body.supplied_bases,
                local=command.body.realized_pnl_local,
                base=command.body.realized_pnl_base,
            )
        except (ValueError, TypeError, KeyError, ArithmeticError):
            raise SourceCorrectionRejected("SOURCE_REVISION_FACT_UNVERIFIED") from None

    def _revision(
        self,
        command: TransactionSourceCorrectionRequestedEvent,
        retained: RetainedSourceRows,
        *,
        attestation_hash: str,
    ) -> TransactionSourceRevision:
        raw_payload, raw_hash = self._require_current_root(command, retained)
        output, original, confirmed = self._confirm_retained_source(command, retained, raw_payload)
        presence = {
            "local": original.local.source is not None,
            "base": original.base.source is not None,
        }
        original_hash, source_values, receipt = self._qualification_material(
            command,
            retained,
            raw_hash,
            output,
            {"local": confirmed.local.source, "base": confirmed.base.source},
            presence,
        )
        return self._new_revision(
            command,
            retained,
            attestation_hash,
            raw_hash,
            original_hash,
            source_values,
            presence,
            receipt,
        )

    @staticmethod
    def _require_current_root(
        command: TransactionSourceCorrectionRequestedEvent, retained: RetainedSourceRows
    ) -> tuple[Mapping[str, object], str]:
        claims = command.authorization.claims
        transaction, raw, head = retained.transaction, retained.raw_event, retained.head
        if transaction.portfolio_id != command.portfolio_id:
            raise SourceCorrectionRejected("SOURCE_REVISION_OWNER_MISMATCH")
        raw_payload: object = raw.payload
        if not isinstance(raw_payload, Mapping):
            raise SourceCorrectionRejected("SOURCE_REVISION_RAW_AUTHORITY_UNAVAILABLE")
        try:
            raw_hash = canonical_content_hash(raw_payload)
        except (TypeError, ValueError, ArithmeticError):
            raise SourceCorrectionRejected("SOURCE_REVISION_RAW_AUTHORITY_UNAVAILABLE") from None
        if claims.root_raw_id != str(raw.id) or claims.root_raw_sha256 != raw_hash:
            raise SourceCorrectionRejected("SOURCE_REVISION_ROOT_MISMATCH")
        actual_id = str(raw.id) if head is None else head.revision_id
        actual_hash = raw_hash if head is None else head.revision_sha256
        if (claims.expected_head_id, claims.expected_head_sha256) != (actual_id, actual_hash):
            raise SourceCorrectionRejected("SOURCE_REVISION_CAS_CONFLICT")
        if head is not None:
            raise SourceCorrectionRejected("SOURCE_REVISION_ALREADY_CONFIRMED")
        return raw_payload, raw_hash

    @staticmethod
    def _confirm_retained_source(
        command: TransactionSourceCorrectionRequestedEvent,
        retained: RetainedSourceRows,
        raw_payload: Mapping[str, object],
    ) -> tuple[dict[str, object], FxSourceEvidenceConfirmation, FxSourceEvidenceConfirmation]:
        transaction = retained.transaction
        claims = command.authorization.claims
        try:
            TransactionEvent.model_validate(raw_payload)
            output = {
                column.name: getattr(transaction, column.name)
                for column in Transaction.__table__.columns
                if column.name not in _TECHNICAL_FIELDS
            } | {"tenant_id": claims.tenant_id}
            original = verify_retained_fx_source(
                raw_source=raw_payload,
                ledger_output=output,
                stored_fingerprint=cast(str, transaction.payload_fingerprint),
                receipt_payload=transaction.calculation_lineage,
                tenant_id=claims.tenant_id,
            )
            confirmed = confirm_missing_fx_source(
                original,
                local=command.body.realized_pnl_local
                if "local" in command.body.supplied_bases
                else original.local.source,
                base=command.body.realized_pnl_base
                if "base" in command.body.supplied_bases
                else original.base.source,
            )
        except (TypeError, ValueError, ArithmeticError):
            raise SourceCorrectionRejected("SOURCE_REVISION_EVIDENCE_REJECTED") from None
        return output, original, confirmed

    @staticmethod
    def _qualification_material(
        command: TransactionSourceCorrectionRequestedEvent,
        retained: RetainedSourceRows,
        raw_hash: str,
        original_output: dict[str, object],
        source_values: dict[str, object],
        presence: dict[str, bool],
    ) -> tuple[str, dict[str, object], dict[str, object]]:
        return source_confirmation_material(
            raw_id=str(retained.raw_event.id),
            raw_sha256=raw_hash,
            original_receipt=retained.transaction.calculation_lineage,
            original_presence=presence,
            request_sha256=command.authorization.claims.canonical_request_sha256,
            original_output=original_output,
            confirmed_source=source_values,
        )

    def _new_revision(
        self,
        command: TransactionSourceCorrectionRequestedEvent,
        retained: RetainedSourceRows,
        attestation_hash: str,
        raw_hash: str,
        original_hash: str,
        source_values: dict[str, object],
        presence: dict[str, bool],
        receipt: dict,
    ) -> TransactionSourceRevision:
        claims = command.authorization.claims
        identity = {
            "revision_id": str(uuid4()),
            "tenant_id": claims.tenant_id,
            "command_id": claims.command_id,
            "operation_id": claims.operation_id,
            "attestation_sha256": attestation_hash,
            "confirmed_at": self._clock(),
            "qualification_receipt": receipt,
        }
        fields = dict(
            **identity,
            portfolio_id=command.portfolio_id,
            transaction_id=claims.target_transaction_id,
            root_raw_event_id=retained.raw_event.id,
            root_raw_sha256=raw_hash,
            predecessor_revision_id=None,
            expected_head_id=claims.expected_head_id,
            expected_head_sha256=claims.expected_head_sha256,
            canonical_request_sha256=claims.canonical_request_sha256,
            original_output_sha256=original_hash,
            source_local=source_values["local"],
            source_base=source_values["base"],
            original_local_present=presence["local"],
            original_base_present=presence["base"],
            authorization_claims=claims.model_dump(mode="json"),
            reason=command.body.reason,
            correlation_id=claims.correlation_id,
            trace_id=claims.trace_id,
        )
        # Bind the complete appended fact, not only its random/time identity.
        return TransactionSourceRevision(**fields, revision_sha256=canonical_content_hash(fields))
