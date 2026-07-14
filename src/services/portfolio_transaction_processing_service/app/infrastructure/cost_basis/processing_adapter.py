"""Adapt cost-basis processing to the unified transaction-processing application port."""

from __future__ import annotations

from typing import Protocol

from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.events import TransactionEvent

from ...application import TransactionProcessingError, build_settlement_cash_rejection
from ...application.cost_basis_processing import (
    CostProcessingRoute,
    FxRateNotFoundError,
    InstrumentReferenceUnavailableError,
    prepare_cost_transaction,
)
from ...application.settlement_processing import UpstreamCashLegUnavailableError
from ...domain import BookedTransaction
from ...domain.transaction import SettlementCashValidationError
from ...ports import (
    AccruedIncomeOffsetStatePort,
    CorporateActionReconciliationRepository,
    CostBasisAverageCostPoolPort,
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisLotStatePort,
    CostBasisPortfolioReference,
    CostBasisProcessingStatePort,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
)
from ..booked_transaction_event_mapper import (
    to_booked_transaction,
    to_transaction_event,
    with_booked_transaction_fields,
)
from .staged_effects import StagedCostEffects


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
        repo: CostBasisTransactionStatePort,
        average_cost_pools: CostBasisAverageCostPoolPort,
        lot_states: CostBasisLotStatePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        reconciliation_repository: CorporateActionReconciliationRepository,
        cost_basis_method: CostBasisMethod,
        effect_stager: CostProcessingEffectStagingPort,
        correlation_id: str,
    ) -> StagedCostEffects: ...


class CostBasisProcessingAdapter:
    """Run cost-basis processing inside the combined caller-owned unit of work."""

    def __init__(
        self,
        *,
        workflow: CostEffectsStager,
        repository: CostBasisTransactionStatePort,
        average_cost_pools: CostBasisAverageCostPoolPort,
        lot_states: CostBasisLotStatePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        reference_data: CostBasisReferenceDataPort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        reconciliation_repository: CorporateActionReconciliationRepository,
        effect_stager: CostProcessingEffectStagingPort,
    ) -> None:
        self._workflow = workflow
        self._repository = repository
        self._average_cost_pools = average_cost_pools
        self._lot_states = lot_states
        self._income_offsets = income_offsets
        self._reference_data = reference_data
        self._fx_rates = fx_rates
        self._processing_state = processing_state
        self._reconciliation_repository = reconciliation_repository
        self._effect_stager = effect_stager

    async def stage_event(
        self,
        *,
        event: TransactionEvent,
        correlation_id: str,
    ) -> StagedCostEffects:
        """Stage cost-basis and outbox writes in the caller-owned transaction."""
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
            average_cost_pools=self._average_cost_pools,
            lot_states=self._lot_states,
            income_offsets=self._income_offsets,
            fx_rates=self._fx_rates,
            processing_state=self._processing_state,
            reconciliation_repository=self._reconciliation_repository,
            cost_basis_method=prepared.cost_basis_method,
            effect_stager=self._effect_stager,
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
