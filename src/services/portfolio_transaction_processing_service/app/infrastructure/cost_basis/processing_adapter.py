"""Adapt cost-basis processing to the unified transaction-processing application port."""

from __future__ import annotations

from dataclasses import replace

from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from ...application import (
    TransactionProcessingError,
    TransactionProcessingRejected,
    build_settlement_cash_rejection,
)
from ...application.cost_basis_processing import (
    FxRateNotFoundError,
    InstrumentReferenceUnavailableError,
    PreparedCostProcessingUseCase,
    prepare_cost_transaction,
)
from ...application.settlement_processing import UpstreamCashLegUnavailableError
from ...domain import BookedTransaction
from ...domain.transaction import (
    CashAccountRequiredValidationError,
    CashAccountRequiredValidationReasonCode,
    SettlementCashValidationError,
    build_transaction_semantic_identity,
)
from ...domain.transaction.fx import FX_BUSINESS_TRANSACTION_TYPES
from ...domain.transaction.fx.persisted_return import (
    FxBookingContext,
    FxCanonicalSourceLoad,
    FxPersistenceWitness,
)
from ...domain.transaction.redemption import requires_linked_redemption_interest_history
from ...ports import (
    AccruedIncomeOffsetStatePort,
    CorporateActionReconciliationRepository,
    CostBasisAverageCostPoolPort,
    CostBasisFxRatePort,
    CostBasisLotBasisTransferPort,
    CostBasisLotDisposalPort,
    CostBasisLotStatePort,
    CostBasisProcessingStatePort,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
    InitialOpeningCostStatePort,
    LotAmortizedCostProfilePort,
)
from ...ports.transaction_processing import FirstPublicationSourceAuthority, FxSourceAdmission


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
        lot_disposals: CostBasisLotDisposalPort,
        lot_basis_transfers: CostBasisLotBasisTransferPort,
        lot_states: CostBasisLotStatePort,
        amortized_cost_profiles: LotAmortizedCostProfilePort,
        income_offsets: AccruedIncomeOffsetStatePort,
        initial_opening_state: InitialOpeningCostStatePort,
        reference_data: CostBasisReferenceDataPort,
        fx_rates: CostBasisFxRatePort,
        processing_state: CostBasisProcessingStatePort,
        reconciliation_repository: CorporateActionReconciliationRepository,
        effect_stager: CostProcessingEffectStagingPort,
    ) -> None:
        self._processor = processor
        self._repository = repository
        self._average_cost_pools = average_cost_pools
        self._lot_disposals = lot_disposals
        self._lot_basis_transfers = lot_basis_transfers
        self._lot_states = lot_states
        self._amortized_cost_profiles = amortized_cost_profiles
        self._income_offsets = income_offsets
        self._initial_opening_state = initial_opening_state
        self._reference_data = reference_data
        self._fx_rates = fx_rates
        self._processing_state = processing_state
        self._reconciliation_repository = reconciliation_repository
        self._effect_stager = effect_stager

    async def validate_unversioned_repair_source(
        self, transaction: BookedTransaction
    ) -> FxPersistenceWitness | None:
        """Match canonical material authority while retaining the owning write locks."""
        source = await self._load_locked_canonical_source(transaction)
        witness = None
        if isinstance(source, FxCanonicalSourceLoad):
            witness = source.retention_witness
            source = source.transaction
        if not self._matches_canonical_source(source, transaction):
            raise TransactionProcessingRejected(
                reason_code="repair_source_authority_mismatch",
                detail={
                    "portfolio_id": transaction.portfolio_id,
                    "transaction_id": transaction.transaction_id,
                },
                retryable=False,
            )
        return witness

    async def load_first_publication_source(
        self, transaction: BookedTransaction
    ) -> FirstPublicationSourceAuthority | FxSourceAdmission | None:
        """Retain optional exact source proof without admitting a repair route."""
        if transaction.epoch is not None or not transaction.tenant_id:
            return None
        try:
            source = await self._load_locked_canonical_source(transaction)
        except TransactionProcessingRejected as exc:
            if exc.reason_code not in {
                "repair_source_owner_mismatch",
                "repair_source_authority_mismatch",
                "repair_original_source_unavailable",
            }:
                raise
            return None
        witness = None
        fx_load = False
        if isinstance(source, FxCanonicalSourceLoad):
            fx_load = True
            witness = source.retention_witness
            source = source.transaction
        if (
            source is None
            or source.epoch is not None
            or not self._matches_canonical_source(source, transaction)
        ):
            return FxSourceAdmission(None, witness) if fx_load else None
        authority = FirstPublicationSourceAuthority(
            tenant_id=transaction.tenant_id,
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            transaction_id=transaction.transaction_id,
            payload_fingerprint=build_transaction_semantic_identity(
                transaction
            ).payload_fingerprint,
        )
        return FxSourceAdmission(authority, witness) if fx_load else authority

    @staticmethod
    def _matches_canonical_source(
        source: BookedTransaction | None, transaction: BookedTransaction
    ) -> bool:
        return source is not None and (
            source.tenant_id,
            source.portfolio_id,
            source.security_id,
            source.transaction_id,
            build_transaction_semantic_identity(source).payload_fingerprint,
        ) == (
            transaction.tenant_id,
            transaction.portfolio_id,
            transaction.security_id,
            transaction.transaction_id,
            build_transaction_semantic_identity(transaction).payload_fingerprint,
        )

    async def _load_locked_canonical_source(
        self, transaction: BookedTransaction
    ) -> BookedTransaction | FxCanonicalSourceLoad | None:
        await self._processing_state.acquire_cost_basis_processing_lock(
            transaction.portfolio_id, transaction.security_id
        )
        if requires_linked_redemption_interest_history(transaction):
            await self._processing_state.acquire_linked_redemption_group_lock(
                transaction.portfolio_id, transaction.linked_transaction_group_id or ""
            )

        if (
            normalize_transaction_control_code(transaction.transaction_type)
            in FX_BUSINESS_TRANSACTION_TYPES
        ):
            return await self._repository.load_booked_transaction_with_fx_witness(transaction)
        return await self._repository.get_booked_transaction(
            transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            repair_tenant_id=transaction.tenant_id or "",
            repair_security_id=transaction.security_id,
        )

    async def load_derived_financial_transaction(
        self, transaction: BookedTransaction
    ) -> BookedTransaction | None:
        """Read exact canonical financial facts while this UOW retains cost serialization."""
        return await self._repository.get_derived_financial_transaction(transaction)

    async def _process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str,
        reconcile_superseded_derived: bool,
        fx_booking_context: FxBookingContext | None = None,
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
            instrument_product_type=(instrument.product_type if instrument is not None else None),
            instrument_asset_class=(instrument.asset_class if instrument is not None else None),
        )
        correction_removes_generated_cash = (
            reconcile_superseded_derived
            and transaction.cash_entry_mode is None
            and not str(transaction.settlement_cash_account_id or "").strip()
            and not str(transaction.settlement_cash_instrument_id or "").strip()
        )
        if correction_removes_generated_cash:
            prepared = replace(
                prepared,
                transaction=replace(prepared.transaction, cash_entry_mode=None),
            )
        return await self._processor.execute(
            prepared=prepared,
            portfolio=portfolio,
            instrument=instrument,
            reference_data=self._reference_data,
            transaction_state=self._repository,
            average_cost_pools=self._average_cost_pools,
            lot_disposals=self._lot_disposals,
            lot_basis_transfers=self._lot_basis_transfers,
            lot_states=self._lot_states,
            amortized_cost_profiles=self._amortized_cost_profiles,
            income_offsets=self._income_offsets,
            initial_opening_state=self._initial_opening_state,
            fx_rates=self._fx_rates,
            processing_state=self._processing_state,
            reconciliation_repository=self._reconciliation_repository,
            effect_stager=self._effect_stager,
            correlation_id=correlation_id,
            reconcile_superseded_derived=reconcile_superseded_derived,
            fx_booking_context=fx_booking_context,
        )

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
        reconcile_superseded_derived: bool = False,
        fx_booking_context: FxBookingContext | None = None,
    ) -> CostProcessingResult:
        try:
            return await self._process(
                transaction,
                correlation_id=correlation_id or "",
                reconcile_superseded_derived=reconcile_superseded_derived,
                fx_booking_context=fx_booking_context,
            )
        except SettlementCashValidationError as exc:
            raise build_settlement_cash_rejection(transaction, exc) from exc
        except CashAccountRequiredValidationError as exc:
            detail = {
                "portfolio_id": transaction.portfolio_id,
                "transaction_id": transaction.transaction_id,
                "transaction_type": exc.transaction_type,
                "field": exc.field,
            }
            if exc.reason_code is (
                CashAccountRequiredValidationReasonCode.INSTRUMENT_AUTHORITY_UNAVAILABLE
            ):
                raise TransactionProcessingError(
                    reason_code=exc.reason_code.value,
                    detail=detail,
                    retryable=True,
                ) from exc
            raise TransactionProcessingRejected(
                reason_code=exc.reason_code.value,
                detail=detail,
                retryable=False,
            ) from exc
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
