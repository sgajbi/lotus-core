"""Adapt cost-basis processing to the unified transaction-processing application port."""

from __future__ import annotations

from ...application import TransactionProcessingError, build_settlement_cash_rejection
from ...application.cost_basis_processing import (
    FxRateNotFoundError,
    InstrumentReferenceUnavailableError,
    PreparedCostProcessingUseCase,
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
    CostBasisLotStatePort,
    CostBasisProcessingStatePort,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
)


class PortfolioNotFoundError(Exception):
    """Report that cost processing cannot yet resolve its portfolio dependency."""


class CostBasisProcessingAdapter:
    """Run cost-basis processing inside the combined caller-owned unit of work."""

    def __init__(
        self,
        *,
        processor: PreparedCostProcessingUseCase,
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
        self._processor = processor
        self._repository = repository
        self._average_cost_pools = average_cost_pools
        self._lot_states = lot_states
        self._income_offsets = income_offsets
        self._reference_data = reference_data
        self._fx_rates = fx_rates
        self._processing_state = processing_state
        self._reconciliation_repository = reconciliation_repository
        self._effect_stager = effect_stager

    async def _process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str,
    ) -> CostProcessingResult:
        reference_data = await self._reference_data.get_cost_basis_reference_data(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
        )
        if reference_data is None:
            raise PortfolioNotFoundError(
                f"Portfolio {transaction.portfolio_id} not found. Retrying..."
            )

        portfolio = reference_data.portfolio
        instrument = reference_data.instrument
        prepared = prepare_cost_transaction(
            transaction,
            cost_basis_method=portfolio.cost_basis_method,
            instrument_reference_available=instrument is not None,
        )
        return await self._processor.execute(
            prepared=prepared,
            portfolio=portfolio,
            instrument=instrument,
            transaction_state=self._repository,
            average_cost_pools=self._average_cost_pools,
            lot_states=self._lot_states,
            income_offsets=self._income_offsets,
            fx_rates=self._fx_rates,
            processing_state=self._processing_state,
            reconciliation_repository=self._reconciliation_repository,
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
        try:
            return await self._process(
                transaction,
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
