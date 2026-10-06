"""Verify cost-basis processing adapter mapping and error behavior."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingError,
    TransactionProcessingRejected,
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    PreparedCostProcessingUseCase,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    CashAccountRequiredValidationReasonCode,
    SettlementCashRejectionReasonCode,
    SettlementCashValidationError,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    CostBasisProcessingAdapter,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    AccruedIncomeOffsetStatePort,
    CorporateActionReconciliationRepository,
    CostBasisAverageCostPoolPort,
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisLotBasisTransferPort,
    CostBasisLotDisposalPort,
    CostBasisLotStatePort,
    CostBasisPortfolioReference,
    CostBasisProcessingStatePort,
    CostBasisReferenceData,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
    InitialOpeningCostStatePort,
    LotAmortizedCostProfilePort,
    SettlementCashAccountReference,
)
from tests.test_support.tenant import TEST_TENANT_ID


@pytest.mark.asyncio
async def test_cost_adapter_maps_domain_and_returns_every_processed_leg() -> None:
    transaction = BookedTransaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255.00"),
        trade_currency="SGD",
        currency="SGD",
    )
    processed_transaction = replace(transaction, transaction_id="TX-001-COSTED")
    repository = AsyncMock(spec=CostBasisTransactionStatePort)
    reference_data = AsyncMock(spec=CostBasisReferenceDataPort)
    reference_data.get_cost_basis_reference_data.return_value = CostBasisReferenceData(
        portfolio=CostBasisPortfolioReference(
            base_currency="SGD",
            portfolio_id="PB-001",
            cost_basis_method=CostBasisMethod.FIFO,
            tenant_id=TEST_TENANT_ID,
        ),
        instrument=CostBasisInstrumentReference(
            security_id="SEC-001",
            product_type="EQUITY",
            asset_class="EQUITY",
        ),
    )
    effect_stager = AsyncMock(spec=CostProcessingEffectStagingPort)
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_disposals = AsyncMock(spec=CostBasisLotDisposalPort)
    lot_basis_transfers = AsyncMock(spec=CostBasisLotBasisTransferPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    income_offsets = AsyncMock(spec=AccruedIncomeOffsetStatePort)
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    processor = AsyncMock(spec=PreparedCostProcessingUseCase)
    processor.execute.return_value = CostProcessingResult(
        processed_transactions=(processed_transaction,),
        instrument_update_count=1,
    )
    adapter = CostBasisProcessingAdapter(
        processor=processor,
        repository=repository,
        average_cost_pools=average_cost_pools,
        lot_disposals=lot_disposals,
        lot_basis_transfers=lot_basis_transfers,
        lot_states=lot_states,
        amortized_cost_profiles=AsyncMock(spec=LotAmortizedCostProfilePort),
        income_offsets=income_offsets,
        initial_opening_state=AsyncMock(spec=InitialOpeningCostStatePort),
        reference_data=reference_data,
        fx_rates=fx_rates,
        processing_state=processing_state,
        reconciliation_repository=reconciliation_repository,
        effect_stager=effect_stager,
    )

    result = await adapter.process(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert [item.transaction_id for item in result.processed_transactions] == ["TX-001-COSTED"]
    assert result.instrument_update_count == 1
    build_call = processor.execute.await_args.kwargs
    prepared = build_call["prepared"]
    assert prepared.transaction.transaction_id == "TX-001"
    assert prepared.transaction.economic_event_id == "EVT-BUY-PB-001-TX-001"
    assert prepared.transaction_type == "BUY"
    assert prepared.cost_basis_method.value == "FIFO"
    assert prepared.route is cost_basis_processing.CostProcessingRoute.COST_BASIS
    assert build_call["fx_rates"] is fx_rates
    assert build_call["average_cost_pools"] is average_cost_pools
    assert build_call["lot_disposals"] is lot_disposals
    assert build_call["lot_basis_transfers"] is lot_basis_transfers
    assert build_call["lot_states"] is lot_states
    assert build_call["income_offsets"] is income_offsets
    assert build_call["processing_state"] is processing_state
    assert build_call["effect_stager"] is effect_stager


@pytest.mark.asyncio
async def test_cost_adapter_passes_reference_port_after_defaulting_auto_generate() -> None:
    transaction = BookedTransaction(
        transaction_id="DIVIDEND-DEFAULT-CASH-MODE",
        portfolio_id="PB-001",
        instrument_id="EQ-001",
        security_id="EQ-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        settlement_cash_account_id="CASH-EUR",
        settlement_cash_instrument_id=None,
        cash_entry_mode=None,
    )
    portfolio = CostBasisPortfolioReference(
        base_currency="USD",
        portfolio_id="PB-001",
        cost_basis_method=CostBasisMethod.FIFO,
        tenant_id=TEST_TENANT_ID,
    )
    reference_data = AsyncMock(spec=CostBasisReferenceDataPort)
    reference_data.get_cost_basis_reference_data.side_effect = [
        CostBasisReferenceData(
            portfolio=portfolio,
            instrument=CostBasisInstrumentReference(
                security_id="EQ-001",
                product_type="EQUITY",
                asset_class="EQUITY",
                currency="USD",
            ),
        ),
        CostBasisReferenceData(
            portfolio=portfolio,
            instrument=CostBasisInstrumentReference(
                security_id="CASH-EUR",
                product_type="CASH",
                asset_class="Cash",
                currency="EUR",
            ),
        ),
    ]
    reference_data.get_settlement_cash_account_reference.return_value = (
        SettlementCashAccountReference(
            cash_account_id="CASH-EUR",
            security_id="CASH-EUR",
            account_currency="EUR",
            instrument_product_type="CASH",
            instrument_currency="EUR",
        )
    )
    processor = AsyncMock(spec=PreparedCostProcessingUseCase)
    processor.execute.return_value = CostProcessingResult(
        processed_transactions=(transaction,),
        instrument_update_count=0,
    )
    adapter = CostBasisProcessingAdapter(
        processor=processor,
        repository=AsyncMock(spec=CostBasisTransactionStatePort),
        average_cost_pools=AsyncMock(spec=CostBasisAverageCostPoolPort),
        lot_disposals=AsyncMock(spec=CostBasisLotDisposalPort),
        lot_basis_transfers=AsyncMock(spec=CostBasisLotBasisTransferPort),
        lot_states=AsyncMock(spec=CostBasisLotStatePort),
        amortized_cost_profiles=AsyncMock(spec=LotAmortizedCostProfilePort),
        income_offsets=AsyncMock(spec=AccruedIncomeOffsetStatePort),
        initial_opening_state=AsyncMock(spec=InitialOpeningCostStatePort),
        reference_data=reference_data,
        fx_rates=AsyncMock(spec=CostBasisFxRatePort),
        processing_state=AsyncMock(spec=CostBasisProcessingStatePort),
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
    )

    await adapter.process(transaction, correlation_id="corr-default-mode", traceparent=None)

    call = processor.execute.await_args.kwargs
    assert call["prepared"].transaction.cash_entry_mode == "AUTO_GENERATE"
    assert call["prepared"].transaction.settlement_cash_instrument_id is None
    assert call["reference_data"] is reference_data
    assert reference_data.get_cost_basis_reference_data.await_count == 1


@pytest.mark.asyncio
async def test_cost_adapter_maps_missing_reference_data_to_retryable_application_error() -> None:
    transaction = BookedTransaction(
        transaction_id="TX-MISSING-PORTFOLIO",
        portfolio_id="PB-MISSING",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255.00"),
        trade_currency="SGD",
        currency="SGD",
    )
    repository = AsyncMock(spec=CostBasisTransactionStatePort)
    reference_data = AsyncMock(spec=CostBasisReferenceDataPort)
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_disposals = AsyncMock(spec=CostBasisLotDisposalPort)
    lot_basis_transfers = AsyncMock(spec=CostBasisLotBasisTransferPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    income_offsets = AsyncMock(spec=AccruedIncomeOffsetStatePort)
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    reference_data.get_cost_basis_reference_data.return_value = None
    adapter = CostBasisProcessingAdapter(
        processor=AsyncMock(spec=PreparedCostProcessingUseCase),
        repository=repository,
        average_cost_pools=average_cost_pools,
        lot_disposals=lot_disposals,
        lot_basis_transfers=lot_basis_transfers,
        lot_states=lot_states,
        amortized_cost_profiles=AsyncMock(spec=LotAmortizedCostProfilePort),
        income_offsets=income_offsets,
        initial_opening_state=AsyncMock(spec=InitialOpeningCostStatePort),
        reference_data=reference_data,
        fx_rates=fx_rates,
        processing_state=processing_state,
        reconciliation_repository=reconciliation_repository,
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
    )

    with pytest.raises(TransactionProcessingError) as exc_info:
        await adapter.process(transaction, correlation_id="corr-001", traceparent=None)

    assert exc_info.value.reason_code == "cost_dependency_unavailable"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_cost_adapter_maps_settlement_rejection_to_non_retryable_error() -> None:
    transaction = BookedTransaction(
        transaction_id="SELL-FEE-DOMINATED-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity=Decimal("1"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1"),
        trade_fee=Decimal("2"),
        trade_currency="SGD",
        currency="SGD",
    )
    repository = AsyncMock(spec=CostBasisTransactionStatePort)
    reference_data = AsyncMock(spec=CostBasisReferenceDataPort)
    reference_data.get_cost_basis_reference_data.return_value = CostBasisReferenceData(
        portfolio=CostBasisPortfolioReference(
            base_currency="SGD",
            portfolio_id="PB-001",
            cost_basis_method=CostBasisMethod.FIFO,
            tenant_id=TEST_TENANT_ID,
        ),
        instrument=CostBasisInstrumentReference(
            security_id="SEC-001",
            product_type="EQUITY",
            asset_class="EQUITY",
        ),
    )
    processor = AsyncMock(spec=PreparedCostProcessingUseCase)
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_disposals = AsyncMock(spec=CostBasisLotDisposalPort)
    lot_basis_transfers = AsyncMock(spec=CostBasisLotBasisTransferPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    income_offsets = AsyncMock(spec=AccruedIncomeOffsetStatePort)
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    processor.execute.side_effect = SettlementCashValidationError(
        reason_code=(SettlementCashRejectionReasonCode.SELL_NON_POSITIVE_NET_SETTLEMENT),
        field="trade_fee",
        message="SELL settlement cash must remain greater than zero after transaction fees.",
        available_proceeds=Decimal("1"),
        fee_amount=Decimal("2"),
        net_settlement_amount=Decimal("-1"),
    )
    adapter = CostBasisProcessingAdapter(
        processor=processor,
        repository=repository,
        average_cost_pools=average_cost_pools,
        lot_disposals=lot_disposals,
        lot_basis_transfers=lot_basis_transfers,
        lot_states=lot_states,
        amortized_cost_profiles=AsyncMock(spec=LotAmortizedCostProfilePort),
        income_offsets=income_offsets,
        initial_opening_state=AsyncMock(spec=InitialOpeningCostStatePort),
        reference_data=reference_data,
        fx_rates=fx_rates,
        processing_state=processing_state,
        reconciliation_repository=reconciliation_repository,
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
    )

    with pytest.raises(TransactionProcessingRejected) as raised:
        await adapter.process(transaction, correlation_id="corr-001", traceparent=None)

    assert raised.value.reason_code == "SELL_010_NON_POSITIVE_NET_SETTLEMENT"
    assert raised.value.retryable is False
    assert raised.value.detail["available_proceeds"] == "1"
    assert raised.value.detail["fee_amount"] == "2"


@pytest.mark.asyncio
async def test_cost_adapter_rejects_non_cash_fee_before_processor_execution() -> None:
    transaction = _cash_account_booking("FEE")
    processor = AsyncMock(spec=PreparedCostProcessingUseCase)
    adapter = _cash_account_adapter(
        processor=processor,
        instrument=CostBasisInstrumentReference(
            security_id=transaction.security_id,
            product_type="EQUITY",
            asset_class="EQUITY",
        ),
    )

    with pytest.raises(TransactionProcessingRejected) as raised:
        await adapter.process(transaction, correlation_id="corr-001", traceparent=None)

    assert raised.value.reason_code == (
        CashAccountRequiredValidationReasonCode.NON_CASH_INSTRUMENT.value
    )
    assert raised.value.retryable is False
    processor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cost_adapter_retries_cash_booking_without_instrument_authority() -> None:
    transaction = _cash_account_booking("TAX")
    processor = AsyncMock(spec=PreparedCostProcessingUseCase)
    adapter = _cash_account_adapter(processor=processor, instrument=None)

    with pytest.raises(TransactionProcessingError) as raised:
        await adapter.process(transaction, correlation_id="corr-001", traceparent=None)

    assert raised.value.reason_code == (
        CashAccountRequiredValidationReasonCode.INSTRUMENT_AUTHORITY_UNAVAILABLE.value
    )
    assert raised.value.retryable is True
    processor.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "component_type",
    ["FX_CASH_SETTLEMENT_BUY", "FX_CASH_SETTLEMENT_SELL"],
)
async def test_cost_adapter_validates_effective_fx_cash_component_type(
    component_type: str,
) -> None:
    transaction = replace(
        _cash_account_booking("FX_SPOT"),
        component_type=component_type,
    )
    processor = AsyncMock(spec=PreparedCostProcessingUseCase)
    adapter = _cash_account_adapter(
        processor=processor,
        instrument=CostBasisInstrumentReference(
            security_id=transaction.security_id,
            product_type="EQUITY",
            asset_class="EQUITY",
        ),
    )

    with pytest.raises(TransactionProcessingRejected) as raised:
        await adapter.process(transaction, correlation_id="corr-001", traceparent=None)

    assert raised.value.reason_code == (
        CashAccountRequiredValidationReasonCode.NON_CASH_INSTRUMENT.value
    )
    assert raised.value.detail["transaction_type"] == component_type
    assert raised.value.retryable is False
    processor.execute.assert_not_awaited()


def _cash_account_booking(transaction_type: str) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"TX-{transaction_type}-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=Decimal("25"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("25"),
        trade_currency="SGD",
        currency="SGD",
    )


def _cash_account_adapter(
    *,
    processor: PreparedCostProcessingUseCase,
    instrument: CostBasisInstrumentReference | None,
) -> CostBasisProcessingAdapter:
    reference_data = AsyncMock(spec=CostBasisReferenceDataPort)
    reference_data.get_cost_basis_reference_data.return_value = CostBasisReferenceData(
        portfolio=CostBasisPortfolioReference(
            base_currency="SGD",
            portfolio_id="PB-001",
            cost_basis_method=CostBasisMethod.FIFO,
            tenant_id=TEST_TENANT_ID,
        ),
        instrument=instrument,
    )
    return CostBasisProcessingAdapter(
        processor=processor,
        repository=AsyncMock(spec=CostBasisTransactionStatePort),
        average_cost_pools=AsyncMock(spec=CostBasisAverageCostPoolPort),
        lot_disposals=AsyncMock(spec=CostBasisLotDisposalPort),
        lot_basis_transfers=AsyncMock(spec=CostBasisLotBasisTransferPort),
        lot_states=AsyncMock(spec=CostBasisLotStatePort),
        amortized_cost_profiles=AsyncMock(spec=LotAmortizedCostProfilePort),
        income_offsets=AsyncMock(spec=AccruedIncomeOffsetStatePort),
        initial_opening_state=AsyncMock(spec=InitialOpeningCostStatePort),
        reference_data=reference_data,
        fx_rates=AsyncMock(spec=CostBasisFxRatePort),
        processing_state=AsyncMock(spec=CostBasisProcessingStatePort),
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source_matches", [True, False])
async def test_repair_source_validation_locks_before_loading_and_never_costs(source_matches):
    transaction = replace(_cash_account_booking("BUY"), tenant_id=TEST_TENANT_ID)
    processor = AsyncMock(spec=PreparedCostProcessingUseCase)
    adapter = _cash_account_adapter(processor=processor, instrument=None)
    order = []

    async def lock(*args):
        order.append("cost-lock")

    async def load(*args, **kwargs):
        order.append("canonical-source")
        assert kwargs == {
            "portfolio_id": transaction.portfolio_id,
            "repair_tenant_id": TEST_TENANT_ID,
            "repair_security_id": transaction.security_id,
        }
        return transaction if source_matches else replace(transaction, quantity=Decimal("26"))

    adapter._processing_state.acquire_cost_basis_processing_lock.side_effect = lock
    adapter._repository.get_booked_transaction.side_effect = load
    if source_matches:
        await adapter.validate_unversioned_repair_source(transaction)
    else:
        with pytest.raises(TransactionProcessingRejected) as rejected:
            await adapter.validate_unversioned_repair_source(transaction)
        assert rejected.value.reason_code == "repair_source_authority_mismatch"
    assert order == ["cost-lock", "canonical-source"]
    processor.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "tenant_id",
        "portfolio_id",
        "security_id",
        "transaction_id",
        "quantity",
        "missing",
        "unqualified",
        "epoch",
    ],
)
async def test_first_publication_source_requires_locked_exact_original_input(damage):
    transaction = replace(_cash_account_booking("BUY"), tenant_id=TEST_TENANT_ID)
    processor = AsyncMock(spec=PreparedCostProcessingUseCase)
    adapter = _cash_account_adapter(processor=processor, instrument=None)
    order = []

    async def lock(*args):
        order.append("cost-lock")

    async def load(*args, **kwargs):
        assert order == ["cost-lock"]
        order.append("canonical-source")
        assert kwargs["repair_tenant_id"] == transaction.tenant_id
        assert kwargs["repair_security_id"] == transaction.security_id
        if damage == "unqualified":
            raise TransactionProcessingRejected(
                reason_code="repair_original_source_unavailable", detail={}, retryable=False
            )
        if damage == "missing":
            return None
        if damage:
            value = Decimal("26") if damage == "quantity" else 0 if damage == "epoch" else "foreign"
            return replace(transaction, **{damage: value})
        return transaction

    adapter._processing_state.acquire_cost_basis_processing_lock.side_effect = lock
    adapter._repository.get_booked_transaction.side_effect = load
    proof = await adapter.load_first_publication_source(transaction)
    assert order == ["cost-lock", "canonical-source"]
    assert (proof is not None) is (damage is None)
    if proof:
        assert proof.matches(transaction)
        assert not proof.matches(replace(transaction, quantity=Decimal("26")))
    processor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_fx_admission_then_retry_returns_only_fresh_explicit_facts():
    from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx.persisted_return import (  # noqa: E501
        FxCanonicalSourceLoad,
        FxPersistenceWitness,
    )
    from src.services.portfolio_transaction_processing_service.app.ports.transaction_processing import (  # noqa: E501
        FxSourceAdmission,
    )

    transaction = replace(
        _cash_account_booking("BUY"),
        tenant_id=TEST_TENANT_ID,
        transaction_type="FX_SPOT",
        source_system=None,
    )
    before = replace(transaction, source_system="ORIGINAL", fx_realized_pnl_mode="NONE")
    witness = FxPersistenceWitness(before, None, None)
    processor = AsyncMock(spec=PreparedCostProcessingUseCase)
    adapter = _cash_account_adapter(processor=processor, instrument=None)
    adapter._repository.load_booked_transaction_with_fx_witness.side_effect = [
        TransactionProcessingRejected(
            reason_code="repair_original_source_unavailable", detail={}, retryable=False
        ),
        FxCanonicalSourceLoad(before, witness),
    ]
    assert await adapter.load_first_publication_source(transaction) is None
    retry = await adapter.load_first_publication_source(transaction)
    assert retry == FxSourceAdmission(None, witness)
    adapter._repository.get_booked_transaction.assert_not_awaited()
    assert adapter._repository.load_booked_transaction_with_fx_witness.await_count == 2
    processor.execute.assert_not_awaited()
