"""Verify cost-basis processing adapter mapping and error behavior."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.events import TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingError,
    TransactionProcessingRejected,
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    SettlementCashRejectionReasonCode,
    SettlementCashValidationError,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    CostBasisProcessingAdapter,
    StagedCostEffects,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
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
)


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
    processed_event = TransactionEvent.model_validate(
        {
            **{field.name: getattr(transaction, field.name) for field in fields(transaction)},
            "transaction_id": "TX-001-COSTED",
            "correlation_id": "corr-001",
            "traceparent": "trace-001",
        }
    )
    repository = AsyncMock(spec=CostBasisTransactionStatePort)
    reference_data = AsyncMock(spec=CostBasisReferenceDataPort)
    reference_data.get_cost_basis_portfolio.return_value = CostBasisPortfolioReference(
        base_currency="SGD",
        portfolio_id="PB-001",
        cost_basis_method=CostBasisMethod.FIFO,
    )
    reference_data.get_cost_basis_instrument.return_value = CostBasisInstrumentReference(
        security_id="SEC-001",
        product_type="EQUITY",
        asset_class="EQUITY",
    )
    outbox_repository = AsyncMock(spec=OutboxRepository)
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    income_offsets = AsyncMock(spec=AccruedIncomeOffsetStatePort)
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    workflow = MagicMock()
    workflow.stage_prepared_event = AsyncMock(
        return_value=StagedCostEffects(
            emitted_transactions=(processed_event,),
            instrument_update_count=1,
        )
    )
    adapter = CostBasisProcessingAdapter(
        workflow=workflow,
        repository=repository,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        income_offsets=income_offsets,
        reference_data=reference_data,
        fx_rates=fx_rates,
        processing_state=processing_state,
        reconciliation_repository=reconciliation_repository,
        outbox_repository=outbox_repository,
    )

    result = await adapter.process(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert [item.transaction_id for item in result.processed_transactions] == ["TX-001-COSTED"]
    assert result.instrument_update_count == 1
    build_call = workflow.stage_prepared_event.await_args.kwargs
    input_event = build_call["event"]
    assert input_event.transaction_id == "TX-001"
    assert input_event.correlation_id == "corr-001"
    assert input_event.traceparent == "trace-001"
    assert input_event.economic_event_id == "EVT-BUY-PB-001-TX-001"
    assert build_call["event_transaction_type"] == "BUY"
    assert build_call["cost_basis_method"].value == "FIFO"
    assert build_call["route"] is cost_basis_processing.CostProcessingRoute.COST_BASIS
    assert build_call["fx_rates"] is fx_rates
    assert build_call["average_cost_pools"] is average_cost_pools
    assert build_call["lot_states"] is lot_states
    assert build_call["income_offsets"] is income_offsets
    assert build_call["processing_state"] is processing_state


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
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    income_offsets = AsyncMock(spec=AccruedIncomeOffsetStatePort)
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    reference_data.get_cost_basis_portfolio.return_value = None
    adapter = CostBasisProcessingAdapter(
        workflow=MagicMock(),
        repository=repository,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        income_offsets=income_offsets,
        reference_data=reference_data,
        fx_rates=fx_rates,
        processing_state=processing_state,
        reconciliation_repository=reconciliation_repository,
        outbox_repository=AsyncMock(spec=OutboxRepository),
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
    reference_data.get_cost_basis_portfolio.return_value = CostBasisPortfolioReference(
        base_currency="SGD",
        portfolio_id="PB-001",
        cost_basis_method=CostBasisMethod.FIFO,
    )
    reference_data.get_cost_basis_instrument.return_value = CostBasisInstrumentReference(
        security_id="SEC-001",
        product_type="EQUITY",
        asset_class="EQUITY",
    )
    workflow = MagicMock()
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    processing_state = AsyncMock(spec=CostBasisProcessingStatePort)
    average_cost_pools = AsyncMock(spec=CostBasisAverageCostPoolPort)
    lot_states = AsyncMock(spec=CostBasisLotStatePort)
    income_offsets = AsyncMock(spec=AccruedIncomeOffsetStatePort)
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    workflow.stage_prepared_event = AsyncMock(
        side_effect=SettlementCashValidationError(
            reason_code=(SettlementCashRejectionReasonCode.SELL_NON_POSITIVE_NET_SETTLEMENT),
            field="trade_fee",
            message="SELL settlement cash must remain greater than zero after transaction fees.",
            available_proceeds=Decimal("1"),
            fee_amount=Decimal("2"),
            net_settlement_amount=Decimal("-1"),
        )
    )
    adapter = CostBasisProcessingAdapter(
        workflow=workflow,
        repository=repository,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        income_offsets=income_offsets,
        reference_data=reference_data,
        fx_rates=fx_rates,
        processing_state=processing_state,
        reconciliation_repository=reconciliation_repository,
        outbox_repository=AsyncMock(spec=OutboxRepository),
    )

    with pytest.raises(TransactionProcessingRejected) as raised:
        await adapter.process(transaction, correlation_id="corr-001", traceparent=None)

    assert raised.value.reason_code == "SELL_010_NON_POSITIVE_NET_SETTLEMENT"
    assert raised.value.retryable is False
    assert raised.value.detail["available_proceeds"] == "1"
    assert raised.value.detail["fee_amount"] == "2"
