import logging
from dataclasses import dataclass
from typing import Any, Protocol

from portfolio_common.events import InstrumentEvent, TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from .repository import CostCalculatorRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "cost-calculator"


class PortfolioNotFoundError(Exception):
    """Raised when the portfolio for a transaction is not yet in the database."""

    pass


class CostCalculationWorkflow(Protocol):
    async def _prepare_transaction_event(
        self,
        event: TransactionEvent,
        portfolio: Any,
    ) -> tuple[TransactionEvent, str, Any]: ...

    def _assert_required_instrument_reference_available(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        instrument: Any,
    ) -> None: ...

    async def _build_events_to_publish(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        portfolio: Any,
        instrument: Any,
        repo: CostCalculatorRepository,
        cost_basis_method: Any,
    ) -> tuple[list[TransactionEvent], list[InstrumentEvent]]: ...

    async def _build_emitted_transaction_events(
        self,
        *,
        events_to_publish: list[TransactionEvent],
        repo: CostCalculatorRepository,
        correlation_id: str,
    ) -> list[TransactionEvent]: ...

    async def _publish_transaction_events(
        self,
        *,
        original_event: TransactionEvent,
        emitted_events: list[TransactionEvent],
        outbox_repo: OutboxRepository,
        correlation_id: str,
    ) -> None: ...

    async def _publish_instrument_events(
        self,
        *,
        instrument_events: list[InstrumentEvent],
        outbox_repo: OutboxRepository,
        correlation_id: str,
    ) -> None: ...


@dataclass(frozen=True)
class CostCalculationProcessorDependencies:
    repo: CostCalculatorRepository
    idempotency_repo: IdempotencyRepository
    outbox_repo: OutboxRepository


class CostCalculationProcessorDependencyFactory:
    def from_session(self, db: AsyncSession) -> CostCalculationProcessorDependencies:
        return CostCalculationProcessorDependencies(
            repo=CostCalculatorRepository(db),
            idempotency_repo=IdempotencyRepository(db),
            outbox_repo=OutboxRepository(db),
        )


class CostCalculationEventProcessor:
    def __init__(self, workflow: CostCalculationWorkflow) -> None:
        self._workflow = workflow

    async def process_valid_event(
        self,
        *,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
        dependencies: CostCalculationProcessorDependencies,
    ) -> None:
        if not await dependencies.idempotency_repo.claim_event_processing(
            event_id,
            event.portfolio_id,
            SERVICE_NAME,
            correlation_id,
        ):
            logger.warning("Event already processed. Skipping.")
            return

        portfolio = await dependencies.repo.get_portfolio(event.portfolio_id)
        if not portfolio:
            raise PortfolioNotFoundError(f"Portfolio {event.portfolio_id} not found. Retrying...")

        (
            prepared_event,
            event_transaction_type,
            cost_basis_method,
        ) = await self._workflow._prepare_transaction_event(event, portfolio)
        instrument = await dependencies.repo.get_instrument(prepared_event.security_id)
        self._workflow._assert_required_instrument_reference_available(
            event=prepared_event,
            event_transaction_type=event_transaction_type,
            instrument=instrument,
        )
        (
            events_to_publish,
            instrument_events_to_publish,
        ) = await self._workflow._build_events_to_publish(
            event=prepared_event,
            event_transaction_type=event_transaction_type,
            portfolio=portfolio,
            instrument=instrument,
            repo=dependencies.repo,
            cost_basis_method=cost_basis_method,
        )
        emitted_events = await self._workflow._build_emitted_transaction_events(
            events_to_publish=events_to_publish,
            repo=dependencies.repo,
            correlation_id=correlation_id,
        )
        await self._workflow._publish_transaction_events(
            original_event=prepared_event,
            emitted_events=emitted_events,
            outbox_repo=dependencies.outbox_repo,
            correlation_id=correlation_id,
        )
        await self._workflow._publish_instrument_events(
            instrument_events=instrument_events_to_publish,
            outbox_repo=dependencies.outbox_repo,
            correlation_id=correlation_id,
        )
