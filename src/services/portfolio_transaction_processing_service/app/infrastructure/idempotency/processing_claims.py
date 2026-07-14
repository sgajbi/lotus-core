"""Persist and classify transaction-processing idempotency claims."""

from __future__ import annotations

from portfolio_common.idempotency_repository import (
    IdempotencyRepository,
    SemanticEventClaimOutcome,
)

from ...ports import TransactionIdempotencyOutcome

TRANSACTION_PROCESSING_SERVICE_NAME = "portfolio-transaction-processing"


class SqlAlchemyTransactionIdempotencyAdapter:
    """Adapt shared SQL claim persistence to transaction-processing outcomes."""

    def __init__(self, repository: IdempotencyRepository) -> None:
        self._repository = repository

    async def claim(
        self,
        *,
        event_id: str,
        portfolio_id: str,
        semantic_key: str,
        payload_fingerprint: str,
        correlation_id: str | None,
    ) -> TransactionIdempotencyOutcome:
        outcome = await self._repository.claim_semantic_event_processing(
            event_id=event_id,
            portfolio_id=portfolio_id,
            service_name=TRANSACTION_PROCESSING_SERVICE_NAME,
            semantic_key=semantic_key,
            payload_fingerprint=payload_fingerprint,
            correlation_id=correlation_id,
        )
        return semantic_claim_outcome(outcome)

    async def claim_repair_delivery(
        self,
        *,
        event_id: str,
        portfolio_id: str,
        correlation_id: str | None,
    ) -> bool:
        return bool(
            await self._repository.claim_event_processing(
                event_id=event_id,
                portfolio_id=portfolio_id,
                service_name=TRANSACTION_PROCESSING_SERVICE_NAME,
                correlation_id=correlation_id,
            )
        )


def semantic_claim_outcome(
    outcome: SemanticEventClaimOutcome,
) -> TransactionIdempotencyOutcome:
    """Translate a persisted semantic claim outcome to the application contract."""

    return TransactionIdempotencyOutcome(outcome.value)
