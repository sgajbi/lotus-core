"""Verify transaction-processing claim persistence and outcome mapping."""

from unittest.mock import AsyncMock

import pytest
from portfolio_common.idempotency_repository import (
    IdempotencyRepository,
    SemanticEventClaimOutcome,
)

from src.services.portfolio_transaction_processing_service.app.infrastructure.idempotency import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
    SqlAlchemyTransactionIdempotencyAdapter,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    TransactionIdempotencyOutcome,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repository_outcome", "application_outcome"),
    [
        (SemanticEventClaimOutcome.CLAIMED, TransactionIdempotencyOutcome.CLAIMED),
        (
            SemanticEventClaimOutcome.PHYSICAL_DUPLICATE,
            TransactionIdempotencyOutcome.PHYSICAL_DUPLICATE,
        ),
        (
            SemanticEventClaimOutcome.SEMANTIC_DUPLICATE,
            TransactionIdempotencyOutcome.SEMANTIC_DUPLICATE,
        ),
        (
            SemanticEventClaimOutcome.SEMANTIC_CONFLICT,
            TransactionIdempotencyOutcome.SEMANTIC_CONFLICT,
        ),
    ],
)
async def test_semantic_claim_preserves_repository_outcome(
    repository_outcome: SemanticEventClaimOutcome,
    application_outcome: TransactionIdempotencyOutcome,
) -> None:
    repository = AsyncMock(spec=IdempotencyRepository)
    repository.claim_semantic_event_processing.return_value = repository_outcome
    adapter = SqlAlchemyTransactionIdempotencyAdapter(repository)

    claimed = await adapter.claim(
        event_id="transactions.persisted-0-42",
        portfolio_id="PB-001",
        semantic_key="transaction-processing:v1:PB-001:TX-001:0",
        payload_fingerprint="sha256:abc123",
        correlation_id="corr-001",
    )

    assert claimed is application_outcome
    repository.claim_semantic_event_processing.assert_awaited_once_with(
        event_id="transactions.persisted-0-42",
        portfolio_id="PB-001",
        service_name=TRANSACTION_PROCESSING_SERVICE_NAME,
        semantic_key="transaction-processing:v1:PB-001:TX-001:0",
        payload_fingerprint="sha256:abc123",
        correlation_id="corr-001",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("repository_claimed", "expected"), [(True, True), (False, False)])
async def test_repair_claim_preserves_physical_claim_result(
    repository_claimed: bool,
    expected: bool,
) -> None:
    repository = AsyncMock(spec=IdempotencyRepository)
    repository.claim_event_processing.return_value = repository_claimed
    adapter = SqlAlchemyTransactionIdempotencyAdapter(repository)

    claimed = await adapter.claim_repair_delivery(
        event_id="transactions.persisted-0-42",
        portfolio_id="PB-001",
        correlation_id="corr-001",
    )

    assert claimed is expected
    repository.claim_event_processing.assert_awaited_once_with(
        event_id="transactions.persisted-0-42",
        portfolio_id="PB-001",
        service_name=TRANSACTION_PROCESSING_SERVICE_NAME,
        correlation_id="corr-001",
    )
