"""Compatibility composition for transaction-readiness application coordination."""

from __future__ import annotations

from portfolio_common.outbox_repository import OutboxRepository

from ..application.transaction_readiness import RegisterTransactionReadinessUseCase
from .transaction_readiness import TransactionalTransactionReadinessEventStager
from .transaction_stage_repository import SqlAlchemyTransactionStageRepository


class PipelineStageProcessingAdapter(RegisterTransactionReadinessUseCase):
    """Compose readiness ports while callers migrate to the application use case."""

    def __init__(
        self,
        repository: SqlAlchemyTransactionStageRepository,
        outbox_repository: OutboxRepository,
    ) -> None:
        super().__init__(
            repository=repository,
            events=TransactionalTransactionReadinessEventStager(outbox_repository),
        )
