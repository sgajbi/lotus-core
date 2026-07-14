"""Adapt the transitional cost workflow to the transaction-processing application port."""

from __future__ import annotations

from typing import Protocol

from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.events import TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository

from ..application import TransactionProcessingError, build_settlement_cash_rejection
from ..application.cost_basis_processing import (
    CostProcessingRoute,
    InstrumentReferenceUnavailableError,
    prepare_cost_transaction,
)
from ..domain import BookedTransaction
from ..domain.transaction import SettlementCashValidationError
from ..ports import (
    CorporateActionReconciliationRepository,
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisPortfolioReference,
    CostBasisProcessingStatePort,
    CostBasisReferenceDataPort,
    CostProcessingResult,
)
from .booked_transaction_event_mapper import (
    to_booked_transaction,
    to_transaction_event,
    with_booked_transaction_fields,
)
from .cost_basis import StagedCostEffects
from .cost_calculation_workflow import (
    FxRateNotFoundError,
    UpstreamCashLegUnavailableError,
)
from .cost_repository import (
    CostCalculatorRepository,
)


class PortfolioNotFoundError(Exception):
    """Report that cost processing cannot yet resolve its portfolio dependency."""


class CostEffectsStager(Protocol):
    """Stage prepared cost effects inside the caller-owned database transaction."""

    async def stage_prepared_event(
        self,
        *,
        event: TransactionEvent,
        event_transaction_type: str,
        route: CostProcessingRoute,
        portfolio: CostBasisPortfolioReference,
        instrument: CostBasisInstrumentReference | None,
        repo: CostCalculatorRepository,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        reconciliation_repository: CorporateActionReconciliationRepository,
        cost_basis_method: CostBasisMethod,
        outbox_repo: OutboxRepository,
        correlation_id: str,
    ) -> StagedCostEffects: ...


class CostProcessingCompatibilityAdapter:
    """Run the current cost policy inside the combined caller-owned unit of work."""

    def __init__(
        self,
        *,
        workflow: CostEffectsStager,
        repository: CostCalculatorRepository,
        reference_data: CostBasisReferenceDataPort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        reconciliation_repository: CorporateActionReconciliationRepository,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._workflow = workflow
        self._repository = repository
        self._reference_data = reference_data
        self._fx_rates = fx_rates
        self._processing_state = processing_state
        self._reconciliation_repository = reconciliation_repository
        self._outbox_repository = outbox_repository

    async def stage_event(
        self,
        *,
        event: TransactionEvent,
        correlation_id: str,
    ) -> StagedCostEffects:
        """Stage compatibility cost and outbox writes in the caller-owned transaction."""
        portfolio = await self._reference_data.get_cost_basis_portfolio(event.portfolio_id)
        if not portfolio:
            raise PortfolioNotFoundError(f"Portfolio {event.portfolio_id} not found. Retrying...")

        instrument = await self._reference_data.get_cost_basis_instrument(event.security_id)
        prepared = prepare_cost_transaction(
            to_booked_transaction(event),
            cost_basis_method=portfolio.cost_basis_method,
            instrument_reference_available=instrument is not None,
        )
        prepared_event = with_booked_transaction_fields(event, prepared.transaction)
        return await self._workflow.stage_prepared_event(
            event=prepared_event,
            event_transaction_type=prepared.transaction_type,
            route=prepared.route,
            portfolio=portfolio,
            instrument=instrument,
            repo=self._repository,
            fx_rates=self._fx_rates,
            processing_state=self._processing_state,
            reconciliation_repository=self._reconciliation_repository,
            cost_basis_method=prepared.cost_basis_method,
            outbox_repo=self._outbox_repository,
            correlation_id=correlation_id,
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
                to_booked_transaction(item) for item in stage_result.emitted_transactions
            ),
            instrument_update_count=stage_result.instrument_update_count,
        )
