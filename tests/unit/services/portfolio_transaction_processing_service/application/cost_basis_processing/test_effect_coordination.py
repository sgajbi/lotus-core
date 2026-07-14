"""Verify domain-valued settlement, reconciliation, and effect staging coordination."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    coordinate_cost_processing_effects,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    FxContractInstrument,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CorporateActionReconciliationRepository,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
)


def _transaction(
    *,
    transaction_id: str,
    transaction_type: str,
    net_cost_local: str = "25",
    epoch: int | None = None,
    auto_generate_cash_leg: bool = False,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT-COST-01",
        instrument_id="INSTRUMENT-01",
        security_id="SECURITY-01",
        transaction_date=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=abs(Decimal(net_cost_local)),
        trade_currency="SGD",
        currency="SGD",
        net_cost_local=Decimal(net_cost_local),
        epoch=epoch,
        cash_entry_mode=("AUTO_GENERATE" if auto_generate_cash_leg else None),
        settlement_cash_account_id=("CASH-SGD-01" if auto_generate_cash_leg else None),
        settlement_cash_instrument_id=("CASH-SGD" if auto_generate_cash_leg else None),
    )


@pytest.mark.asyncio
async def test_effect_coordination_links_and_stages_generated_cash_leg() -> None:
    product_leg = _transaction(
        transaction_id="DIV-GENERATED-01",
        transaction_type="DIVIDEND",
        auto_generate_cash_leg=True,
    )
    transaction_state = AsyncMock(spec=CostBasisTransactionStatePort)
    effect_stager = AsyncMock(spec=CostProcessingEffectStagingPort)

    result = await coordinate_cost_processing_effects(
        processed_transactions=[product_leg],
        instrument_updates=[],
        source_epoch=7,
        transaction_state=transaction_state,
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=effect_stager,
        correlation_id="corr-generated-01",
    )

    assert [item.transaction_id for item in result.processed_transactions] == [
        "DIV-GENERATED-01",
        "DIV-GENERATED-01-CASHLEG",
    ]
    linked_product, generated_cash = result.processed_transactions
    assert linked_product.external_cash_transaction_id == "DIV-GENERATED-01-CASHLEG"
    assert generated_cash.transaction_type == "ADJUSTMENT"
    assert generated_cash.gross_transaction_amount == Decimal("25")
    assert generated_cash.movement_direction == "INFLOW"
    assert generated_cash.originating_transaction_id == "DIV-GENERATED-01"
    assert {item.epoch for item in result.processed_transactions} == {7}
    assert [
        call.args[0].transaction_id
        for call in transaction_state.upsert_booked_transaction.await_args_list
    ] == ["DIV-GENERATED-01-CASHLEG", "DIV-GENERATED-01"]
    effect_stager.stage_processed_transactions.assert_awaited_once_with(
        result.processed_transactions,
        correlation_id="corr-generated-01",
    )


@pytest.mark.asyncio
async def test_effect_coordination_reconciles_corporate_action_group_once() -> None:
    source = _transaction(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    target = _transaction(
        transaction_id="CA-IN-01",
        transaction_type="DEMERGER_IN",
        net_cost_local="100",
    )
    source = replace(
        source,
        linked_transaction_group_id="LTG-CA-DEM-01",
        parent_event_reference="CA-PARENT-DEM-01",
    )
    target = replace(
        target,
        linked_transaction_group_id="LTG-CA-DEM-01",
        parent_event_reference="CA-PARENT-DEM-01",
    )
    reconciliation_repository = AsyncMock(spec=CorporateActionReconciliationRepository)
    reconciliation_repository.load_group.return_value = ()
    observer = MagicMock()

    result = await coordinate_cost_processing_effects(
        processed_transactions=[source, target],
        instrument_updates=[],
        source_epoch=None,
        transaction_state=AsyncMock(spec=CostBasisTransactionStatePort),
        reconciliation_repository=reconciliation_repository,
        effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
        correlation_id="corr-ca-01",
        reconciliation_observer=observer,
    )

    assert result.processed_transactions == (source, target)
    reconciliation_repository.load_group.assert_awaited_once()
    reconciliation_repository.save_evidence.assert_awaited_once()
    observer.observe.assert_called_once()


@pytest.mark.asyncio
async def test_effect_coordination_stages_instrument_updates_and_count() -> None:
    instrument = MagicMock(spec=FxContractInstrument)
    effect_stager = AsyncMock(spec=CostProcessingEffectStagingPort)

    result = await coordinate_cost_processing_effects(
        processed_transactions=[],
        instrument_updates=[instrument],
        source_epoch=None,
        transaction_state=AsyncMock(spec=CostBasisTransactionStatePort),
        reconciliation_repository=AsyncMock(spec=CorporateActionReconciliationRepository),
        effect_stager=effect_stager,
        correlation_id="corr-instrument-01",
    )

    assert result.instrument_update_count == 1
    effect_stager.stage_instrument_updates.assert_awaited_once_with(
        (instrument,),
        correlation_id="corr-instrument-01",
    )
