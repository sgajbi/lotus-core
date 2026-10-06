"""Signed source commands use the native owning idempotency/CoreDB/DLQ consumer."""

from typing import cast

from portfolio_common.command_authorization import (
    load_command_authorization_policy,
)
from portfolio_common.database_models import TransactionSourceRevision
from portfolio_common.domain.transaction import TransactionPayloadIdentity
from portfolio_common.event_contracts import TransactionSourceCorrectionRequestedEvent
from pydantic import BaseModel

from ..application.transaction_source_correction import TransactionSourceCorrectionApplication
from ..repositories.transaction_source_revision_repository import (
    TransactionSourceRevisionRepository,
)
from .base_consumer import GenericPersistenceConsumer


class TransactionSourceCorrectionConsumer(GenericPersistenceConsumer):
    @property
    def event_model(self) -> type[BaseModel]:
        return TransactionSourceCorrectionRequestedEvent

    @property
    def service_name(self) -> str:
        return "persistence_service.source_correction"

    @property
    def tenant_scoped_idempotency(self) -> bool:
        return True

    async def prepare_event(self, db_session, event: BaseModel) -> BaseModel:
        admission = await TransactionSourceCorrectionApplication(
            TransactionSourceRevisionRepository(db_session),
            policy=load_command_authorization_policy(),
        ).admit(cast(TransactionSourceCorrectionRequestedEvent, event))
        return admission.command

    def semantic_idempotency_identity(self, event: BaseModel) -> TransactionPayloadIdentity:
        command = cast(TransactionSourceCorrectionRequestedEvent, event)
        claims = command.authorization.claims
        digest = f"sha256:{claims.canonical_request_sha256}"
        return TransactionPayloadIdentity(
            semantic_key=f"source-correction:{claims.tenant_id}:{claims.command_id}",
            payload_fingerprint=digest,
            legacy_payload_fingerprint=digest,
        )

    async def handle_persistence(self, db_session, event: BaseModel) -> TransactionSourceRevision:
        return await TransactionSourceCorrectionApplication(
            TransactionSourceRevisionRepository(db_session),
            policy=load_command_authorization_policy(),
        ).execute(cast(TransactionSourceCorrectionRequestedEvent, event))

    # The application stages exactly one revision notification itself, including
    # exact-retry refusal/no-effect behavior. Generic get_outbox_event stays None.
