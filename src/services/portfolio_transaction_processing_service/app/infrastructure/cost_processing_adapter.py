"""Adapt the transitional cost workflow to the transaction-processing application port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from portfolio_common.events import InstrumentEvent, TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository

from ..application import TransactionProcessingError, build_settlement_cash_rejection
from ..application.cost_basis_processing import (
    CostProcessingRoute,
    InstrumentReferenceUnavailableError,
    prepare_cost_transaction,
)
from ..domain import BookedTransaction
from ..domain.transaction import SettlementCashValidationError
from ..ports import CostProcessingResult
from .booked_transaction_event_mapper import (
    to_booked_transaction,
    to_transaction_event,
    with_booked_transaction_fields,
)
from .cost_calculation_workflow import (
    FxRateNotFoundError,
    UpstreamCashLegUnavailableError,
)
from .cost_repository import (
    CostCalculatorRepository,
)


class PortfolioNotFoundError(Exception):
    """Report that cost processing cannot yet resolve its portfolio dependency."""


class CostStagingWorkflow(Protocol):
    """Describe the transitional workflow surface isolated by this adapter."""

    async def _build_events_to_publish(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        route: CostProcessingRoute,
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


@dataclass(frozen=True, slots=True)
class CostStagingResult:
    """Describe costed transaction and instrument events staged for commit."""

    emitted_events: tuple[TransactionEvent, ...]
    instrument_event_count: int


class CostProcessingCompatibilityAdapter:
    """Run the current cost policy inside the combined caller-owned unit of work."""

    def __init__(
        self,
        *,
        workflow: CostStagingWorkflow,
        repository: CostCalculatorRepository,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._workflow = workflow
        self._repository = repository
        self._outbox_repository = outbox_repository

    async def stage_event(
        self,
        *,
        event: TransactionEvent,
        correlation_id: str,
    ) -> CostStagingResult:
        """Stage compatibility cost and outbox writes in the caller-owned transaction."""
        portfolio = await self._repository.get_portfolio(event.portfolio_id)
        if not portfolio:
            raise PortfolioNotFoundError(f"Portfolio {event.portfolio_id} not found. Retrying...")

        instrument = await self._repository.get_instrument(event.security_id)
        prepared = prepare_cost_transaction(
            to_booked_transaction(event),
            cost_basis_method=portfolio.cost_basis_method,
            instrument_reference_available=instrument is not None,
        )
        prepared_event = with_booked_transaction_fields(event, prepared.transaction)
        events_to_publish, instrument_events = await self._workflow._build_events_to_publish(
            event=prepared_event,
            event_transaction_type=prepared.transaction_type,
            route=prepared.route,
            portfolio=portfolio,
            instrument=instrument,
            repo=self._repository,
            cost_basis_method=prepared.cost_basis_method,
        )
        emitted_events = await self._workflow._build_emitted_transaction_events(
            events_to_publish=events_to_publish,
            repo=self._repository,
            correlation_id=correlation_id,
        )
        await self._workflow._publish_transaction_events(
            original_event=prepared_event,
            emitted_events=emitted_events,
            outbox_repo=self._outbox_repository,
            correlation_id=correlation_id,
        )
        await self._workflow._publish_instrument_events(
            instrument_events=instrument_events,
            outbox_repo=self._outbox_repository,
            correlation_id=correlation_id,
        )
        return CostStagingResult(
            emitted_events=tuple(emitted_events),
            instrument_event_count=len(instrument_events),
        )

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> CostProcessingResult:
        event = to_transaction_event(
            transaction,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
        try:
            stage_result = await self.stage_event(
                event=event,
                correlation_id=correlation_id or "",
            )
        except SettlementCashValidationError as exc:
            raise build_settlement_cash_rejection(transaction, exc) from exc
        except (
            FxRateNotFoundError,
            InstrumentReferenceUnavailableError,
            PortfolioNotFoundError,
            UpstreamCashLegUnavailableError,
        ) as exc:
            raise TransactionProcessingError(
                reason_code="cost_dependency_unavailable",
                detail={
                    "portfolio_id": transaction.portfolio_id,
                    "transaction_id": transaction.transaction_id,
                    "dependency_error": type(exc).__name__,
                },
                retryable=True,
            ) from exc
        return CostProcessingResult(
            processed_transactions=tuple(
                to_booked_transaction(item) for item in stage_result.emitted_events
            ),
            instrument_update_count=stage_result.instrument_event_count,
        )
